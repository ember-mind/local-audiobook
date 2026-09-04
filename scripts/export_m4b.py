#!/usr/bin/env python3

"""Assembla i segmenti generati in un M4B e lo porta in books/<slug>/output/.

L'assemblaggio, i capitoli e i metadata li fa lo stage `export` di Pandrator:
qui si costruiscono le impostazioni da book.json, si carica la cover, si
attende il job e si scarica l'artefatto risultante.
"""

from pathlib import Path
import json
import sys
import time
import uuid

import requests


ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8097/api/v1"
TOKEN_FILE = ROOT / ".secrets" / "pandrator-token"

COVER_MIME = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def headers(write=False):
    h = {
        "Authorization": f"Bearer {TOKEN_FILE.read_text().strip()}",
    }

    if write:
        h["Idempotency-Key"] = str(uuid.uuid4())

    return h


def api(method, path, **kwargs):
    response = requests.request(
        method,
        API + path,
        headers=headers(method != "GET"),
        timeout=120,
        **kwargs,
    )

    if not response.ok:
        raise RuntimeError(
            f"{method} {path} → HTTP {response.status_code}\n"
            + response.text[:3000]
        )

    if response.status_code == 204:
        return {}

    return response.json()


def save(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def stages(session_id):
    snapshot = api("GET", f"/sessions/{session_id}/workflow")

    return {
        str(stage.get("key")): stage
        for stage in snapshot.get("stages", [])
    }


def wait_job(job_id, label):
    last = None

    while True:
        job = api("GET", f"/jobs/{job_id}")

        status = str(job.get("status") or "")
        progress = job.get("progress")

        try:
            pct = int(float(progress) * 100)
        except (TypeError, ValueError):
            pct = 0

        display = f"{status}:{pct}"

        if display != last:
            detail = str(job.get("progress_detail") or "").strip()

            line = f"  {label}: {status}"

            if status == "running":
                line += f" · {pct}%"

            if detail:
                line += f" · {detail}"

            print(line, flush=True)
            last = display

        if status in {"completed", "succeeded"}:
            return job

        if status in {"failed", "canceled", "cancelled"}:
            error = (
                job.get("error_message")
                or job.get("error")
                or "errore sconosciuto"
            )

            raise SystemExit(f"✕ {label} fallito:\n{error}")

        time.sleep(2)


def upload_cover(session_id, cover, state, state_path):
    """Carica la cover una volta sola e ricorda l'artifact id."""

    signature = f"{cover.name}:{cover.stat().st_size}"

    if (
        state.get("cover_signature") == signature
        and state.get("cover_artifact_id")
    ):
        print(f"✓ Cover già caricata · {cover.name}")
        return state["cover_artifact_id"]

    mime = COVER_MIME.get(cover.suffix.lower())

    if mime is None:
        raise SystemExit(
            f"Formato cover non supportato: {cover.suffix}\n"
            "Pandrator accetta JPEG, PNG o WebP."
        )

    print(f"→ Upload cover · {cover.name}")

    with cover.open("rb") as f:
        response = requests.post(
            API + "/uploads",
            headers=headers(True),
            data={"session_id": session_id, "purpose": "cover"},
            files={"file": (cover.name, f, mime)},
            timeout=300,
        )

    if not response.ok:
        raise SystemExit(
            f"Upload cover → HTTP {response.status_code}\n"
            + response.text[:2000]
        )

    artifact_id = str(response.json().get("artifact_id") or "")

    if not artifact_id:
        raise SystemExit(
            "Upload cover: risposta senza artifact_id."
        )

    state["cover_artifact_id"] = artifact_id
    state["cover_signature"] = signature
    save(state_path, state)

    print(f"✓ Cover collegata · {artifact_id}")

    return artifact_id


def download(artifact_id, destination):
    response = requests.get(
        API + f"/artifacts/{artifact_id}/content",
        headers=headers(),
        stream=True,
        timeout=600,
    )

    if not response.ok:
        raise SystemExit(
            f"Download artefatto → HTTP {response.status_code}\n"
            + response.text[:2000]
        )

    destination.parent.mkdir(parents=True, exist_ok=True)
    partial = destination.with_suffix(destination.suffix + ".part")

    with partial.open("wb") as f:
        for chunk in response.iter_content(1024 * 1024):
            if chunk:
                f.write(chunk)

    partial.replace(destination)

    return destination


def completed_run_id(session_id):
    """L'ultima generation run completata: l'assembly parte da quella."""

    runs = api("GET", f"/sessions/{session_id}/generation-runs")
    items = runs.get("items") if isinstance(runs, dict) else runs

    for run in items or []:
        if str(run.get("status")) == "completed" and run.get("id"):
            return str(run["id"])

    return ""


def export_artifact_id(session_id):
    """L'audio assemblato dall'ultimo run dello stage export."""

    stage = stages(session_id).get("export", {})

    artifact = stage.get("artifact")

    if isinstance(artifact, dict) and artifact.get("id"):
        return str(artifact["id"])

    for candidate in stage.get("artifacts", []) or []:
        if candidate.get("is_selected") and candidate.get("id"):
            return str(candidate["id"])

    return ""


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Uso: export_m4b.py <slug>")

    slug = sys.argv[1]

    book = ROOT / "books" / slug
    config_path = book / "book.json"
    state_path = book / "work" / "pandrator" / "session.json"

    if not TOKEN_FILE.is_file():
        raise SystemExit(f"Token Pandrator mancante: {TOKEN_FILE}")

    if not config_path.is_file():
        raise SystemExit(f"Libro non trovato: {slug}")

    if not state_path.is_file():
        raise SystemExit(
            "Sessione Pandrator non trovata.\n"
            f"Eseguire prima: ./audiobook prepare-audio {slug}"
        )

    config = json.loads(config_path.read_text(encoding="utf-8"))
    state = json.loads(state_path.read_text(encoding="utf-8"))

    session_id = state.get("session_id")

    if not session_id:
        raise SystemExit("session_id mancante in session.json")

    output_config = config.get("output", {})

    fmt = str(output_config.get("format") or "m4b").lower()
    bitrate = str(output_config.get("bitrate") or "192k")

    # L'audio deve esistere prima di poterlo assemblare.
    generate = stages(session_id).get("generate_audio", {})
    generate_status = str(generate.get("status") or "unknown")

    if generate_status != "completed":
        raise SystemExit(
            f"Audio non pronto: lo stage generate_audio è '{generate_status}'.\n"
            f"Eseguire prima: ./audiobook generate {slug}"
        )

    run_id = completed_run_id(session_id)

    if not run_id:
        raise SystemExit(
            "Nessuna generation run completata da assemblare.\n"
            f"Eseguire prima: ./audiobook generate {slug}"
        )

    settings = {
        "output": {
            "format": fmt,
            "bitrate": bitrate,
            "export_mode": "media",
            "title": str(config.get("title") or slug),
            "artist": str(config.get("author") or ""),
            "album": str(config.get("title") or slug),
            "genre": "Audiobook",
            "language": str(
                output_config.get("language")
                or config.get("translation", {}).get("target_language")
                or "it"
            ),
        }
    }

    cover_relative = str(output_config.get("cover") or "").strip()
    cover = (book / cover_relative) if cover_relative else None

    if cover is not None and cover.is_file():
        settings["output"]["cover_artifact_id"] = upload_cover(
            session_id,
            cover,
            state,
            state_path,
        )
    else:
        if cover_relative:
            print(f"○ Cover assente · {cover_relative}")

        print("  L'export procede senza copertina.")

    print()
    print(f"Formato:  {fmt.upper()} · {bitrate}")
    print(f"Titolo:   {settings['output']['title']}")
    print(f"Autore:   {settings['output']['artist'] or 'non impostato'}")
    print(f"Lingua:   {settings['output']['language']}")
    print()

    # Generazione e export non si toccano: in mezzo c'e' l'assembly, che
    # incolla i segmenti in un unico file applicando pause, room tone,
    # capitoli, metadata e copertina. Lo stage export impacchetta quel
    # risultato, e senza di esso risponde "missing a required input artifact".
    assembly = api(
        "POST",
        f"/sessions/{session_id}/output-assemblies",
        json={
            "generation_run_id": run_id,
            "run_override": settings,
        },
    )

    assembly_job = assembly.get("job_id") or assembly.get("job", {}).get("id")

    state["assembly_id"] = assembly.get("id")
    state["assembly_job_id"] = assembly_job
    state["export_settings"] = settings
    save(state_path, state)

    print(f"→ Assembly · {assembly.get('id')}")

    if assembly_job:
        wait_job(assembly_job, "Assembly")

    job = api(
        "POST",
        f"/sessions/{session_id}/stages/export/run",
        json=settings,
    )

    job_id = job["id"]

    state["export_job_id"] = job_id
    save(state_path, state)

    print(f"→ Job export · {job_id}")

    wait_job(job_id, "Export")

    artifact_id = export_artifact_id(session_id)

    if not artifact_id:
        raise SystemExit(
            "Export completato ma nessun artefatto selezionato.\n"
            f"Controllare la sessione in http://127.0.0.1:8097 ({session_id})"
        )

    destination = book / "output" / f"{slug}.{fmt}"

    print(f"→ Download · {destination.name}")

    download(artifact_id, destination)

    state["export_artifact_id"] = artifact_id
    state["export_output"] = str(destination.relative_to(book))
    save(state_path, state)

    size_mb = destination.stat().st_size / (1024 * 1024)

    print()
    print(f"✓ {fmt.upper()} pronto · {size_mb:.1f} MB")
    print(f"  {destination}")
    print()


if __name__ == "__main__":
    main()
