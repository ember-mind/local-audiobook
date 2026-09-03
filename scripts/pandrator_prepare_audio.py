#!/usr/bin/env python3

from pathlib import Path
import hashlib
import json
import sys
import time
import uuid

import requests


ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8097/api/v1"
TOKEN_FILE = ROOT / ".secrets" / "pandrator-token"


def sha256_file(path):
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


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
            + response.text[:2000]
        )

    if response.status_code == 204:
        return {}

    return response.json()


def save_state(path, state):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(state, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def ensure_session(title, state):
    session_id = state.get("session_id")

    if session_id:
        try:
            api("GET", f"/sessions/{session_id}")
            print(f"✓ Sessione esistente · {session_id}")
            return session_id
        except RuntimeError:
            print("○ Sessione precedente non trovata")

    result = api(
        "POST",
        "/sessions",
        json={
            "name": title,
            "workflow_kind": "audiobook",
            "source_language": "it",
            "target_language": "it",
            "workflow_preset": "custom",
            "included_stages": [
                "clean_source",
                "prepare_text",
                "generate_audio",
                "export",
            ],
        },
    )

    session_id = result["id"]
    state["session_id"] = session_id

    print(f"✓ Sessione creata · {session_id}")

    return session_id


def upload_source(session_id, path):
    print(f"→ Upload {path.name}")

    with path.open("rb") as f:
        response = requests.post(
            API + "/uploads",
            headers=headers(True),
            data={"session_id": session_id},
            files={
                "file": (
                    path.name,
                    f,
                    "text/plain",
                )
            },
            timeout=300,
        )

    if not response.ok:
        raise RuntimeError(
            f"Upload → HTTP {response.status_code}\n"
            + response.text[:2000]
        )

    result = response.json()

    print(
        "✓ Source collegato · "
        f"{result.get('artifact_id', 'unknown')}"
    )

    return result


def wait_job(job_id, label):
    last = None

    while True:
        job = api("GET", f"/jobs/{job_id}")

        status = str(job.get("status") or "")
        progress = job.get("progress")

        if progress is not None:
            try:
                pct = int(float(progress) * 100)
            except Exception:
                pct = 0
        else:
            pct = 0

        display = f"{status}:{pct}"

        if display != last:
            print(
                f"  {label}: {status}"
                + (f" · {pct}%" if status == "running" else "")
            )
            last = display

        if status in {"completed", "succeeded"}:
            print(f"✓ {label} completato")
            return job

        if status in {
            "failed",
            "canceled",
            "cancelled",
        }:
            error = (
                job.get("error_message")
                or job.get("error")
                or "errore sconosciuto"
            )

            raise RuntimeError(
                f"{label} fallito:\n{error}"
            )

        time.sleep(1)


def run_stage(session_id, stage, settings, label):
    print()
    print(f"→ {label}")

    job = api(
        "POST",
        f"/sessions/{session_id}/stages/{stage}/run",
        json=settings,
    )

    job_id = job["id"]

    return wait_job(job_id, label)


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: pandrator_prepare_audio.py <slug>"
        )

    slug = sys.argv[1]

    book = ROOT / "books" / slug
    config_path = book / "book.json"
    source = book / "text" / "narration_ready_it.txt"

    work = book / "work" / "pandrator"
    state_path = work / "session.json"

    if not TOKEN_FILE.is_file():
        raise SystemExit(
            "Token Pandrator mancante:\n"
            f"{TOKEN_FILE}"
        )

    if not config_path.is_file():
        raise SystemExit(
            f"Libro non trovato: {slug}"
        )

    if not source.is_file():
        raise SystemExit(
            "narration_ready_it.txt non trovato."
        )

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    title = config.get("title") or slug

    state = {}

    if state_path.exists():
        state = json.loads(
            state_path.read_text(encoding="utf-8")
        )

    print()
    print(f"Prepare audio · {slug}")
    print("────────────────────────")

    # Verifica server + token.
    api("GET", "/sessions")

    session_id = ensure_session(title, state)
    save_state(state_path, state)

    source_hash = sha256_file(source)

    # Preset audiobook scelto dopo A/B test con Qwen3-TTS.
    # Blocchi più lunghi danno al modello abbastanza contesto
    # per costruire una prosodia narrativa naturale.
    prepare_settings = {
        "max_sentence_length": 600,
        "enable_sentence_splitting": True,
        "enable_sentence_appending": True,
        "enable_nemo_normalization": False,
        "normalize_all_caps": False,
        "llm_processing_enabled": False,
        "llm_tts_optimization": False,
        "llm_tts_document_optimization": False,
        "remove_footnotes": False,
        "filter_citations": False,
    }

    prepare_fingerprint = hashlib.sha256(
        json.dumps(
            {
                "source_sha256": source_hash,
                "prepare_settings": prepare_settings,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()

    if state.get("prepared_fingerprint") == prepare_fingerprint:
        print()
        print("✓ Questa versione del testo è già segmentata")
        print("✓ max_sentence_length: 600")
        print(f"Sessione: {session_id}")
        return

    if state.get("source_sha256") != source_hash:
        upload_source(session_id, source)

        state["source_sha256"] = source_hash
        state.pop("prepared_sha256", None)
        state.pop("prepared_fingerprint", None)

        save_state(state_path, state)

    # Il testo è già stato pulito e validato da local-audiobook.
    # Non vogliamo un secondo passaggio LLM.
    clean_settings = {
        "agentic": False,
        "remove_footnotes": False,
        "filter_citations": False,
    }

    run_stage(
        session_id,
        "clean_source",
        clean_settings,
        "Clean source",
    )

    run_stage(
        session_id,
        "prepare_text",
        prepare_settings,
        "Segment narration",
    )

    state["prepared_sha256"] = source_hash
    state["prepared_fingerprint"] = prepare_fingerprint
    state["max_sentence_length"] = 600
    save_state(state_path, state)

    snapshot = api(
        "GET",
        f"/sessions/{session_id}/workflow",
    )

    (work / "workflow.json").write_text(
        json.dumps(
            snapshot,
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )

    print()
    print("✓ Testo pronto per generazione audio")
    print(f"Sessione Pandrator: {session_id}")
    print(f"State: {state_path}")
    print()
    print("NON è ancora stato avviato il TTS.")


if __name__ == "__main__":
    main()
