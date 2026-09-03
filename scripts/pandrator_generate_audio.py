#!/usr/bin/env python3

from pathlib import Path
import json
import sys
import time
import uuid

import requests


ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8097/api/v1"
QWEN = "http://127.0.0.1:8042"
TOKEN_FILE = ROOT / ".secrets" / "pandrator-token"


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


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False,
        ) + "\n",
        encoding="utf-8",
    )


def qwen_ready():
    try:
        response = requests.get(
            QWEN + "/readyz",
            timeout=5,
        )

        return response.ok

    except requests.RequestException:
        return False


def wait_job(job_id, state_path, state):
    last = None

    while True:
        job = api("GET", f"/jobs/{job_id}")

        status = str(job.get("status") or "")
        progress = job.get("progress")

        try:
            pct = int(float(progress) * 100)
        except (TypeError, ValueError):
            pct = 0

        display = (status, pct)

        if display != last:
            if status == "running":
                print(
                    f"  Generazione: {pct}%"
                )
            else:
                print(
                    f"  Generazione: {status}"
                )

            last = display

        state["generation_job_id"] = job_id
        state["generation_job_status"] = status
        save(state_path, state)

        if status in {"completed", "succeeded"}:
            state["generation_job"] = job
            state["generation_job_status"] = status
            save(state_path, state)

            print()
            print("✓ GENERAZIONE TTS COMPLETATA")
            print()

            result = (
                job.get("result")
                or job.get("result_json")
                or {}
            )

            if result:
                print(
                    json.dumps(
                        result,
                        indent=2,
                        ensure_ascii=False,
                    )
                )

            return

        if status in {
            "failed",
            "canceled",
            "cancelled",
        }:
            state["generation_job"] = job
            save(state_path, state)

            error = (
                job.get("error_message")
                or job.get("error")
                or "errore sconosciuto"
            )

            raise RuntimeError(
                f"Generazione fallita:\n{error}"
            )

        time.sleep(2)


def segments(session_id):
    """Tutti i segmenti della sessione, con il loro stato.

    L'endpoint pagina a 250: senza seguire il cursore si vedrebbero solo i
    primi, tutti completati, e sembrerebbe che non ci sia niente da fare.
    """

    collected = []
    cursor = 0

    while True:
        page = api(
            "GET",
            f"/sessions/{session_id}/generation-segments"
            f"?limit=250&cursor={cursor}",
        )

        items = page.get("items") or []
        collected.extend(items)

        total = page.get("total") or 0
        cursor = page.get("next_cursor")

        if not items or not cursor or len(collected) >= total:
            return collected


def pending_segment_ids(session_id):
    """(da fare, totale) — i segmenti senza audio buono, in ordine."""

    everything = segments(session_id)

    pending = [
        item
        for item in everything
        if str(item.get("status")) != "completed"
    ]

    pending.sort(key=lambda item: item.get("ordinal") or 0)

    return [str(item["id"]) for item in pending], len(everything)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: pandrator_generate_audio.py <slug>"
        )

    slug = sys.argv[1]

    book = ROOT / "books" / slug
    state_path = (
        book
        / "work"
        / "pandrator"
        / "session.json"
    )

    if not TOKEN_FILE.is_file():
        raise SystemExit(
            f"Token Pandrator mancante: {TOKEN_FILE}"
        )

    if not state_path.is_file():
        raise SystemExit(
            "Sessione Pandrator non trovata. "
            "Eseguire prima prepare."
        )

    state = json.loads(
        state_path.read_text(encoding="utf-8")
    )

    session_id = state.get("session_id")

    if not session_id:
        raise SystemExit(
            "session_id mancante."
        )

    if state.get("max_sentence_length") != 600:
        raise SystemExit(
            "STOP: la sessione non risulta preparata "
            "con max_sentence_length=600."
        )

    if not qwen_ready():
        raise SystemExit(
            "Qwen3-TTS non è pronto su :8042.\n"
            "Eseguire prima: ./audiobook start"
        )

    # Se abbiamo già un job attivo, non crearne uno doppio.
    existing_job = state.get("generation_job_id")

    if existing_job:
        try:
            job = api(
                "GET",
                f"/jobs/{existing_job}",
            )

            status = str(job.get("status") or "")

            if status in {"queued", "running"}:
                print()
                print(
                    "✓ Generazione già attiva"
                )
                print(
                    f"Job: {existing_job}"
                )
                print()
                print("→ Riprendo il monitoraggio")

                wait_job(
                    existing_job,
                    state_path,
                    state,
                )
                return

            if status in {
                "completed",
                "succeeded",
            }:
                print()
                print(
                    "✓ La generazione risulta già completata."
                )
                print(
                    f"Job: {existing_job}"
                )
                return

        except Exception:
            pass

    settings = {
        # Pandrator first-class Qwen service
        "service": "kobold_qwen",

        # Native cloning mode exposed by Pandrator.
        # Il nostro adapter accetta questo valore.
        "model": "Voice Cloning",

        # Pandrator usa kobo come sample voice standard.
        # Il nostro adapter lo tratta come alias
        # della reference italiana corrente.
        "voice": "kobo",
        "speaker": "kobo",

        "language": "it",
        "target_language": "it",

        "speed": 1.0,

        # Il nostro adapter non supporta batching.
        "tts_batch_size": 1,

        # Nessun altro LLM modifica il testo.
        "llm_tts_optimization": False,

        # Retry di Pandrator in caso di errore temporaneo.
        "max_attempts": 5,

        # Endpoint locale.
        "kobold_qwen_base_url": QWEN,

        # Pause che useremo nell'assembly.
        "sentence_silence_ms": 250,
        "paragraph_silence_ms": 700,
    }

    # Un run precedente puo' aver generato buona parte dei segmenti prima di
    # morire. Rilanciare lo stage da capo li rigenererebbe tutti: su un libro
    # sono ore buttate. Se c'e' del lavoro fatto, si chiede una run mirata
    # sui soli segmenti mancanti.
    pending, total = pending_segment_ids(session_id)

    if total and not pending:
        print()
        print("✓ Tutti i segmenti hanno già audio.")
        print(f"  Prossimo passo → ./audiobook export {slug}")
        print()
        return

    done = total - len(pending)
    resuming = bool(done)

    print()
    print("GENERATE AUDIO")
    print("──────────────")
    print(f"Libro:    {slug}")
    print(f"Sessione: {session_id}")

    if resuming:
        print(f"Segmenti: {len(pending)} da fare · {done}/{total} già pronti")
    else:
        print(f"Segmenti: {total or 'n/d'}")

    print("TTS:      Qwen3-TTS")
    print("Mode:     Voice Cloning")
    print("Voice:    italiano (alias kobo)")
    print("Chunking: 600")
    print()

    if resuming:
        # Questa rotta accetta segment_ids; quella dello stage no. Con dei
        # segment_ids Pandrator riusa la run esistente e le sue impostazioni
        # gia' congelate — le stesse che hanno prodotto i segmenti fatti —
        # quindi `settings` qui non viene passato: sarebbe ignorato.
        run = api(
            "POST",
            f"/sessions/{session_id}/generation-runs",
            json={
                "segment_ids": pending,
                "operation": "generate",
            },
        )

        job_id = run["job_id"]

        state["generation_run_id"] = run.get("id")
    else:
        job = api(
            "POST",
            f"/sessions/{session_id}/stages/generate_audio/run",
            json=settings,
        )

        job_id = job["id"]

    state["generation_job_id"] = job_id
    state["generation_settings"] = settings

    save(state_path, state)

    print(f"✓ Job avviato: {job_id}")
    print()

    wait_job(
        job_id,
        state_path,
        state,
    )


if __name__ == "__main__":
    main()
