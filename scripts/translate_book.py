#!/usr/bin/env python3

from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import time

import requests


def build_system_prompt(translation_config):
    context = str(
        translation_config.get("context")
        or "a nonfiction book"
    ).strip()

    terminology = translation_config.get("terminology") or {}

    if isinstance(terminology, dict):
        terminology_text = "\n".join(
            f"- {source} = {target}"
            for source, target in terminology.items()
        )
    elif isinstance(terminology, list):
        terminology_text = "\n".join(
            f"- {item}" for item in terminology
        )
    else:
        terminology_text = str(terminology).strip()

    if not terminology_text:
        terminology_text = (
            "Use established Italian terminology appropriate "
            "to the subject and context."
        )

    extra = str(
        translation_config.get("instructions") or ""
    ).strip()

    return f"""
You are a professional literary and technical translator
working from English into Italian.

BOOK CONTEXT

{context}

GOAL

Translate the source into polished, idiomatic Italian suitable
for a professionally published Italian edition and for audiobook
narration.

TRANSLATION RULES

1. Preserve the exact meaning and all factual information.
2. Write natural, fluent Italian. Do not reproduce English syntax mechanically.
3. Preserve the author's tone, register, nuance and level of formality.
4. Do not summarize, shorten, expand, explain or add commentary.
5. Preserve paragraphs, headings, captions, quotations, citations and lists.
6. Preserve structural markers only when they actually occur in the source.
7. Never invent headings, chapter markers, labels or metadata.
8. In particular, never invent [[Chapter]] or similar markers.
9. Keep names, film titles, book titles, dates, measurements and references accurate.
10. Maintain terminology consistently throughout the book.
11. If a literal translation sounds unnatural in Italian, translate the intended meaning.
12. Return only the Italian translation.
13. Do not invent terminology, characters, symbols, explanations or glosses.
14. Do not introduce non-Latin characters unless they occur in the source.
15. Avoid false friends, awkward calques and unnecessarily literal wording.
16. Prefer terminology genuinely used by Italian professionals in the relevant field.
17. If terminology is uncertain, translate conservatively rather than inventing a specialist term.
18. Do not creatively rewrite headings or titles.

TERMINOLOGY GUIDANCE

{terminology_text}

ADDITIONAL BOOK-SPECIFIC INSTRUCTIONS

{extra if extra else "None."}

Before returning the translation, silently proofread it for:
- Italian grammar
- agreement
- accidental foreign characters
- semantic inconsistencies
- missing or invented material
- terminology consistency
""".strip()


SYSTEM_PROMPT = build_system_prompt({})


def sha256(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def make_chunks(text, max_chars):
    paragraphs = text.split("\n\n")

    chunks = []
    current = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = "\n\n".join(current + [paragraph])

        if current and len(candidate) > max_chars:
            chunks.append("\n\n".join(current))
            current = [paragraph]
        else:
            current.append(paragraph)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def port_busy(host, port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.5)
        return sock.connect_ex((host, port)) == 0


def health_ok(origin):
    try:
        response = requests.get(
            f"{origin}/health",
            timeout=2,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def get_loaded_model(api_base):
    response = requests.get(
        f"{api_base}/models",
        timeout=10,
    )
    response.raise_for_status()

    data = response.json().get("data", [])

    if not data:
        raise RuntimeError(
            "llama-server non restituisce alcun modello in /v1/models."
        )

    return data[0]["id"]


def start_llama_server(server_model, api_base, log_path):
    parts = urlsplit(api_base)

    host = parts.hostname or "127.0.0.1"
    port = parts.port or 1234
    origin = f"{parts.scheme or 'http'}://{host}:{port}"

    if health_ok(origin):
        print("✓ llama.cpp già attivo")
        return None, get_loaded_model(api_base)

    if port_busy(host, port):
        raise RuntimeError(
            f"La porta {port} è occupata, "
            "ma /health di llama.cpp non risponde correttamente."
        )

    executable = shutil.which("llama-server")

    if not executable:
        raise RuntimeError(
            "llama-server non trovato.\n"
            "Installa llama.cpp con:\n"
            "  brew install llama.cpp"
        )

    log_path.parent.mkdir(parents=True, exist_ok=True)

    log = open(log_path, "a", encoding="utf-8")

    command = [
        executable,
        "-hf",
        server_model,
        "--host",
        host,
        "--port",
        str(port),
        "-ngl",
        "all",
        "--reasoning",
        "off",
    ]

    print("→ Avvio llama.cpp")
    print(f"  Modello: {server_model}")
    print("  Reasoning: OFF")
    print("  Caricamento...", flush=True)

    process = subprocess.Popen(
        command,
        stdout=log,
        stderr=subprocess.STDOUT,
    )

    deadline = time.time() + 600

    try:
        while time.time() < deadline:
            if process.poll() is not None:
                log.flush()

                tail = ""
                try:
                    lines = log_path.read_text(
                        encoding="utf-8",
                        errors="replace",
                    ).splitlines()
                    tail = "\n".join(lines[-30:])
                except Exception:
                    pass

                raise RuntimeError(
                    "llama-server si è fermato durante l'avvio.\n\n"
                    + tail
                )

            if health_ok(origin):
                model_id = get_loaded_model(api_base)
                print(f"✓ Gemma pronto · {model_id}")
                return process, model_id

            time.sleep(1)

        raise RuntimeError(
            "Timeout: Gemma non è diventato ready entro 10 minuti."
        )

    except Exception:
        if process.poll() is None:
            process.terminate()
        raise

    finally:
        log.close()


def stop_llama_server(process):
    if process is None:
        return

    if process.poll() is not None:
        return

    print()
    print("→ Spengo llama.cpp...")

    process.terminate()

    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()

    print("✓ llama.cpp spento")


def translate_chunk(
    api_base,
    model,
    chunk,
    previous_context="",
):
    context = ""

    if previous_context:
        context = f"""
For continuity only, here is the end of the previous Italian translation:

--- PREVIOUS CONTEXT ---
{previous_context}
--- END CONTEXT ---

Do not repeat this context.
"""

    response = requests.post(
        f"{api_base}/chat/completions",
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": f"""
{context}

Translate the following text:

--- SOURCE ---
{chunk}
--- END SOURCE ---
""",
                },
            ],
            "temperature": 0.1,
            "stream": False,
        },
        timeout=900,
    )

    response.raise_for_status()

    data = response.json()

    try:
        choice = data["choices"][0]
        result = choice["message"]["content"].strip()
    except (KeyError, IndexError, AttributeError, TypeError):
        raise RuntimeError(
            "Risposta inattesa da llama.cpp:\n"
            + json.dumps(
                data,
                ensure_ascii=False,
                indent=2,
            )[:2000]
        )

    if not result:
        raise RuntimeError(
            "llama.cpp ha restituito una traduzione vuota."
        )

    # Never persist a token-limited or otherwise interrupted completion as
    # finished work. A non-empty response is not proof of a full translation.
    if choice.get("finish_reason") != "stop":
        raise RuntimeError(
            "Traduzione non completata: finish_reason="
            f"{choice.get('finish_reason')!r}. "
            "Il chunk non è stato salvato. Verificare il limite di output "
            "e la finestra di contesto di llama.cpp prima di riprovare."
        )

    return result


def atomic_write(path, text):
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(text, encoding="utf-8")
    temp.replace(path)


def assemble(chunks_dir, total):
    result = []

    for index in range(total):
        path = chunks_dir / f"chunk-{index + 1:04d}.txt"

        if not path.exists():
            return None

        result.append(
            path.read_text(encoding="utf-8").strip()
        )

    return "\n\n".join(result).strip() + "\n"


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            "Uso: translate_book.py /path/to/book.json [--reset]"
        )

    config_path = Path(sys.argv[1]).resolve()
    reset = "--reset" in sys.argv[2:]

    if not config_path.is_file():
        raise SystemExit(
            f"Configurazione non trovata: {config_path}"
        )

    book = config_path.parent
    root = book.parent.parent

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    global SYSTEM_PROMPT
    translation_config = config.get("translation", {})
    SYSTEM_PROMPT = build_system_prompt(translation_config)

    translation = config.setdefault("translation", {})

    api_base = translation.get(
        "base_url",
        "http://127.0.0.1:1234/v1",
    ).rstrip("/")

    server_model = translation.get(
        "server_model",
        "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0",
    )

    chunk_size = int(
        translation.get("chunk_chars", 3500)
    )

    source = book / "text" / "source_en.txt"
    output = book / "text" / "book_it.txt"

    work = book / "work" / "translation"
    translated_dir = work / "translated"
    checkpoint = work / "checkpoint.json"

    log_path = root / "logs" / "translator.log"

    if not source.exists():
        raise SystemExit(
            "text/source_en.txt non trovato.\n"
            "Esegui prima:\n"
            f"  ./audiobook clean {book.name}"
        )

    if reset and work.exists():
        shutil.rmtree(work)

    translated_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    source_text = source.read_text(
        encoding="utf-8",
        errors="replace",
    ).strip()

    chunks = make_chunks(
        source_text,
        chunk_size,
    )

    if not chunks:
        raise SystemExit("Il testo sorgente è vuoto.")

    source_hash = sha256(source_text)

    checkpoint_data = {
        "version": 3,
        "system_prompt_sha256": sha256(SYSTEM_PROMPT),
        "source_sha256": source_hash,
        "server_model": server_model,
        "chunk_chars": chunk_size,
        "chunks": len(chunks),
    }

    if checkpoint.exists():
        old = json.loads(
            checkpoint.read_text(encoding="utf-8")
        )

        critical = (
            "version",
            "system_prompt_sha256",
            "source_sha256",
            "server_model",
            "chunk_chars",
            "chunks",
        )

        if any(
            old.get(key) != checkpoint_data.get(key)
            for key in critical
        ):
            raise SystemExit(
                "Sorgente, prompt o configurazione cambiati, oppure checkpoint "
                "precedente alla versione 3 (prompt non verificabile).\n"
                "I chunk esistenti non sono stati modificati. Archiviali prima "
                "di ricominciare; --reset elimina il checkpoint e ritraduce.\n"
                "Per ricominciare usa:\n"
                f"  ./audiobook translate {book.name} --reset"
            )
    else:
        atomic_write(
            checkpoint,
            json.dumps(
                checkpoint_data,
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
        )

    print()
    print(f"Libro: {config.get('title', book.name)}")
    print(f"Chunk: {len(chunks)}")
    print(f"Dimensione chunk: {chunk_size:,} chars")
    print(f"Parole EN: {len(source_text.split()):,}")
    print()

    process = None

    try:
        process, model_id = start_llama_server(
            server_model,
            api_base,
            log_path,
        )

        print()
        print("Traduzione")
        print("──────────")

        previous_context = ""

        for index, chunk in enumerate(chunks):
            chunk_file = (
                translated_dir
                / f"chunk-{index + 1:04d}.txt"
            )

            if chunk_file.exists() and chunk_file.stat().st_size:
                translated = chunk_file.read_text(
                    encoding="utf-8"
                ).strip()

                previous_context = translated[-1200:]

                print(
                    f"✓ {index + 1:>3}/{len(chunks)} "
                    "già tradotto"
                )
                continue

            print(
                f"→ {index + 1:>3}/{len(chunks)} "
                f"· {len(chunk):,} chars",
                flush=True,
            )

            started = time.time()

            translated = translate_chunk(
                api_base,
                model_id,
                chunk,
                previous_context,
            )

            atomic_write(
                chunk_file,
                translated + "\n",
            )

            elapsed = time.time() - started

            print(
                f"  ✓ {len(translated.split()):,} parole "
                f"· {elapsed:.1f}s"
            )

            previous_context = translated[-1200:]

        final = assemble(
            translated_dir,
            len(chunks),
        )

        if final is None:
            raise RuntimeError(
                "Uno o più chunk risultano mancanti."
            )

        atomic_write(output, final)

        print()
        print("✓ Traduzione completata")
        print()
        print(f"Parole EN: {len(source_text.split()):,}")
        print(f"Parole IT: {len(final.split()):,}")
        print()
        print(f"Output: {output}")

    finally:
        stop_llama_server(process)


if __name__ == "__main__":
    main()
