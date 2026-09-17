#!/usr/bin/env python3

"""Scrive i capitoli dentro un M4B già prodotto, senza ricodificare l'audio.

Pandrator marca un capitolo solo quando il segmento in ingresso arriva con
`chapter: yes`, e un testo estratto da PDF non porta quell'informazione: le
intestazioni di capitolo sono header di pagina, che la pulizia toglie come
rumore. Risultato: audiolibri di dieci ore senza navigazione.

Qui i capitoli sono **dati del libro**, come i marcatori di narrazione e le
correzioni del QC. In book.json:

    "chapters": [
      {"title": "Gli albori", "start_marker": "Durante gli anni '10, la"},
      {"title": "Anni '20",   "start_marker": "Negli anni '20, Hollywood era"}
    ]

Ogni `start_marker` è l'inizio del primo segmento del capitolo. Lo script lo
cerca fra i segmenti della sessione Pandrator, somma le durate di quelli che
lo precedono — durate reali, prese dal manifest dell'assembly — e riscrive il
contenitore con `ffmpeg -c copy`: nessuna riconversione, nessuna perdita, una
manciata di secondi invece di un'ora.
"""

from pathlib import Path
import json
import subprocess
import sys
import tempfile
import urllib.request

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pandrator_state import save_json, sha256_file


ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8097/api/v1"
TOKEN_FILE = ROOT / ".secrets" / "pandrator-token"


def api(path):
    request = urllib.request.Request(
        API + path,
        headers={
            "Authorization": f"Bearer {TOKEN_FILE.read_text().strip()}",
        },
    )

    with urllib.request.urlopen(request, timeout=120) as response:
        return json.loads(response.read())


def all_segments(session_id):
    """Segmenti in ordine di ordinal. L'endpoint pagina a 250."""

    collected = []
    cursor = 0

    while True:
        page = api(
            f"/sessions/{session_id}/generation-segments"
            f"?limit=250&cursor={cursor}"
        )

        items = page.get("items") or []
        collected.extend(items)

        total = page.get("total") or 0
        cursor = page.get("next_cursor")

        if not items or not cursor or len(collected) >= total:
            break

    collected.sort(key=lambda item: item.get("ordinal") or 0)

    return collected


def check_provenance(state, target):
    """I capitoli vanno scritti sull'M4B che quell'assembly ha prodotto.

    `output-assemblies/latest` e' l'unico modo di leggere il manifest: se nel
    frattempo e' stato montato un altro assembly, i suoi tempi non descrivono
    piu' il file sul disco. Lo stato dell'export dice quale era il suo.
    """

    expected_sha = state.get("export_sha256")
    expected_assembly = state.get("export_assembly_id")

    if not expected_sha or not expected_assembly:
        print(
            "○ Export precedente alla tracciatura della provenienza: "
            "i tempi non sono verificabili.\n"
            "  Per averla, rifare ./audiobook export."
        )
        return None

    if sha256_file(target) != expected_sha:
        raise SystemExit(
            f"{target.name} non e' il file prodotto dall'ultimo export "
            "(hash diverso).\n"
            "Rifare l'export prima di scrivere i capitoli."
        )

    return expected_assembly


def take_durations(session_id, expected_assembly=None):
    """segment_id → (durata, silenzio) dal manifest dell'assembly.

    Sono le durate vere dei file montati: sommarle ricostruisce esattamente
    la timeline, mentre stimarle dal testo no.
    """

    latest = api(f"/sessions/{session_id}/output-assemblies/latest")
    item = latest.get("item") or {}

    if expected_assembly and str(item.get("id")) != str(expected_assembly):
        raise SystemExit(
            "L'ultimo assembly non e' quello da cui viene l'M4B sul disco.\n"
            f"  sul disco: {expected_assembly}\n"
            f"  ultimo:    {item.get('id')}\n"
            "I tempi apparterrebbero a un altro montaggio: rifare l'export."
        )

    if str(item.get("status")) != "completed":
        raise SystemExit(
            "L'ultimo assembly non è completato: "
            f"stato '{item.get('status')}'."
        )

    artifact_id = item.get("artifact_id")

    if not artifact_id:
        raise SystemExit("L'assembly non ha un artefatto associato.")

    context = api(f"/artifacts/{artifact_id}/context")
    metadata = (context.get("artifact") or {}).get("metadata_json") or {}
    takes = metadata.get("takes") or []

    if not takes:
        raise SystemExit(
            "Il manifest dell'assembly non elenca i take: "
            "impossibile calcolare i tempi."
        )

    durations = {}

    for take in takes:
        segment_id = str(take.get("segment_id") or "")

        if segment_id:
            durations[segment_id] = (
                int(take.get("duration_ms") or 0),
                int(take.get("silence_after_ms") or 0),
            )

    return durations, int(metadata.get("duration_ms") or 0)


# Lo stage clean_source di Pandrator normalizza la punteggiatura: le
# virgolette basse del testo italiano diventano virgolette dritte nei
# segmenti. Un marcatore copiato dalla narrazione non combacerebbe mai.
QUOTES = str.maketrans({
    "«": '"', "»": '"',
    "\u201c": '"', "\u201d": '"', "\u201e": '"', "\u201f": '"',
    "\u2039": "'", "\u203a": "'",
    "\u2018": "'", "\u2019": "'", "\u201a": "'", "\u201b": "'",
    "\u2013": "-", "\u2014": "-",
    "\u2026": "...",
})


def normalise(text):
    """Forma confrontabile: spazi collassati, minuscole, virgolette piatte."""

    return " ".join(str(text or "").translate(QUOTES).split()).lower()


def locate(chapters, segments, durations):
    """Per ogni capitolo: (titolo, millisecondo di inizio)."""

    starts_ms = {}
    elapsed = 0

    missing = []

    for segment in segments:
        segment_id = str(segment.get("id"))
        starts_ms[segment_id] = elapsed

        # Una durata mancante trattata come zero sposta indietro tutti i
        # capitoli successivi, in silenzio: meglio non scrivere niente.
        if segment_id not in durations:
            missing.append(segment.get("ordinal"))
            continue

        duration, silence = durations[segment_id]
        elapsed += duration + silence

    if missing:
        raise SystemExit(
            f"Il manifest dell'assembly non ha la durata di {len(missing)} "
            f"segmenti (primo: ordinal {missing[0]}).\n"
            "I tempi dei capitoli sarebbero sbagliati: nessun capitolo scritto."
        )

    located = []
    problems = []

    for chapter in chapters:
        title = str(chapter.get("title") or "").strip()
        marker = normalise(chapter.get("start_marker"))

        if not title or not marker:
            problems.append(f"{title or '(senza titolo)'}: title o start_marker vuoto")
            continue

        matches = [
            segment
            for segment in segments
            if normalise(segment.get("text")).startswith(marker)
        ]

        if not matches:
            # Ripiego: il marcatore può cadere dentro il segmento invece che
            # all'inizio, se la segmentazione ha tagliato diversamente.
            matches = [
                segment
                for segment in segments
                if marker in normalise(segment.get("text"))
            ]

        if not matches:
            problems.append(f"{title}: nessun segmento inizia con {marker[:50]!r}")
            continue

        if len(matches) > 1:
            problems.append(
                f"{title}: {len(matches)} segmenti corrispondono a "
                f"{marker[:50]!r} — allungare start_marker"
            )
            continue

        located.append((title, starts_ms[str(matches[0]["id"])]))

    return located, problems


def ffmetadata_escape(value):
    """ffmetadata usa = ; # \\ e newline come sintassi: vanno protetti.

    Senza questo un titolo con un punto e virgola tronca la riga e un titolo
    su due righe perde la seconda: il file resta valido e il capitolo esce
    sbagliato, che e' il modo peggiore di fallire.
    """

    out = []

    for char in str(value):
        if char in "=;#\\":
            out.append("\\" + char)
        elif char == "\n":
            out.append("\\\n")
        else:
            out.append(char)

    return "".join(out)


def write_metadata_file(located, total_ms, path):
    """Il formato ffmetadata: un blocco [CHAPTER] per capitolo."""

    lines = [";FFMETADATA1"]

    for index, (title, start_ms) in enumerate(located):
        end_ms = (
            located[index + 1][1]
            if index + 1 < len(located)
            else total_ms
        )

        # Un capitolo che finisce dove comincia farebbe fallire il muxer.
        end_ms = max(end_ms, start_ms + 1)

        lines += [
            "[CHAPTER]",
            "TIMEBASE=1/1000",
            f"START={start_ms}",
            f"END={end_ms}",
            f"title={ffmetadata_escape(title)}",
        ]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def human(ms):
    seconds = ms // 1000
    return f"{seconds // 3600}:{(seconds % 3600) // 60:02d}:{seconds % 60:02d}"


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: add_chapters.py /path/to/book.json")

    config_path = Path(sys.argv[1]).resolve()

    if not config_path.is_file():
        raise SystemExit(f"book.json non trovato: {config_path}")

    book = config_path.parent
    config = json.loads(config_path.read_text(encoding="utf-8"))

    chapters = config.get("chapters") or []

    if not chapters:
        raise SystemExit(
            "Nessun capitolo in book.json.\n"
            'Aggiungere "chapters": [{"title": ..., "start_marker": ...}, ...]'
        )

    state_path = book / "work" / "pandrator" / "session.json"

    if not state_path.is_file():
        raise SystemExit(f"Sessione Pandrator non trovata: {state_path}")

    session_id = json.loads(
        state_path.read_text(encoding="utf-8")
    ).get("session_id")

    if not session_id:
        raise SystemExit("session_id mancante in session.json")

    fmt = str((config.get("output") or {}).get("format") or "m4b").lower()
    target = book / "output" / f"{book.name}.{fmt}"

    if not target.is_file():
        raise SystemExit(
            f"Audiolibro non trovato: {target}\n"
            "Eseguire prima l'export."
        )

    print()
    print(f"Capitoli dichiarati: {len(chapters)}")

    state = json.loads(state_path.read_text(encoding="utf-8"))
    expected_assembly = check_provenance(state, target)

    segments = all_segments(session_id)
    durations, total_ms = take_durations(session_id, expected_assembly)

    print(f"Segmenti: {len(segments)} · durata {human(total_ms)}")
    print()

    located, problems = locate(chapters, segments, durations)

    for title, start_ms in located:
        print(f"  {human(start_ms):>9}  {title}")

    if problems:
        print()
        for problem in problems:
            print(f"  ✕ {problem}")

        raise SystemExit(
            "\nNessun capitolo scritto: sistemare i marcatori in book.json."
        )

    if [start for _title, start in located] != sorted(
        start for _title, start in located
    ):
        raise SystemExit(
            "\nI capitoli non sono in ordine di tempo: "
            "controllare l'ordine in book.json."
        )

    with tempfile.TemporaryDirectory() as tmp:
        metadata_path = Path(tmp) / "chapters.txt"
        write_metadata_file(located, total_ms, metadata_path)

        # L'estensione finale deve restare quella vera: ffmpeg sceglie il
        # muxer dal nome del file, e ".m4b.chapters" non gli dice niente.
        staged = target.with_name(f"{target.stem}.chapters{target.suffix}")

        print()
        print("→ Riscrittura del contenitore (senza ricodifica)")

        result = subprocess.run(
            [
                "ffmpeg",
                "-nostdin",
                "-hide_banner",
                "-loglevel", "error",
                "-y",
                "-i", str(target),
                "-i", str(metadata_path),
                "-map_metadata", "0",
                "-map_chapters", "1",
                # Solo audio e copertina. `-map 0` copierebbe anche la
                # traccia dati dei capitoli scritta da un giro precedente,
                # che il muxer ipod rifiuta: senza questo, riscrivere i
                # capitoli una seconda volta fallisce.
                "-map", "0:a",
                "-map", "0:v?",
                "-c", "copy",
                "-disposition:v:0", "attached_pic",
                str(staged),
            ],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            staged.unlink(missing_ok=True)
            raise SystemExit(
                "ffmpeg ha fallito:\n" + (result.stderr or "")[:2000]
            )

        # Sostituzione solo a file completo: un'interruzione non lascia
        # l'audiolibro a metà.
        staged.replace(target)

    # Scrivere i capitoli cambia il file: senza aggiornare l'impronta, il giro
    # successivo lo scambierebbe per un M4B estraneo all'export.
    if state.get("export_sha256"):
        state["export_sha256"] = sha256_file(target)
        state["chapters_written"] = len(located)
        save_json(state_path, state)

    print()
    print(f"✓ {len(located)} capitoli scritti")
    print(f"  {target}")
    print()


if __name__ == "__main__":
    main()
