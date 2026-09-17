#!/usr/bin/env python3

from pathlib import Path
from urllib.parse import urlsplit
import hashlib
import json
import re
import socket
import subprocess
import sys
import time

import requests


ROOT = Path(__file__).resolve().parent.parent


SYSTEM_PROMPT = """
You are proofreading an Italian translation of a professionally published nonfiction book.

Your job is NOT to rewrite or improve style.

Find only HIGH-CONFIDENCE objective problems such as:
- spelling errors
- words accidentally joined together
- malformed words
- obvious article/noun or subject/verb agreement errors
- accidental foreign characters or corrupted Unicode
- obvious OCR/translation residue
- duplicated accidental words
- clearly broken punctuation
- clearly ungrammatical Italian

Do NOT:
- rewrite good Italian merely because you prefer another phrasing
- modernize or simplify the author's prose
- alter quotations without a clear error
- translate proper names
- change film titles
- alter specialist terminology unless clearly wrong
- make stylistic suggestions

Be conservative. False positives are worse than missing a minor issue.

STRICT OUTPUT RULES:

- Report an issue ONLY when an actual correction is required.
- NEVER report an item where "from" and "to" are identical.
- NEVER report "no error", stylistic observations, or low-confidence observations as issues.
- If confidence is below 0.95, OMIT the issue entirely.
- Return at most 12 issues.
- If nothing clearly needs correction, return exactly {"issues":[]}.
- Do not repeat the same issue.

Return VALID JSON only:

{
  "issues": [
    {
      "from": "exact problematic substring",
      "to": "exact corrected substring",
      "reason": "short explanation in Italian",
      "confidence": 0.99
    }
  ]
}

If there are no objective errors:

{"issues":[]}

The value of "from" MUST be copied exactly from the supplied Italian text.
""".strip()


def chunks(text, max_chars=7000):
    paragraphs = text.split("\n\n")
    result = []
    current = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = "\n\n".join(current + [paragraph])

        if current and len(candidate) > max_chars:
            result.append("\n\n".join(current))
            current = [paragraph]
        else:
            current.append(paragraph)

    if current:
        result.append("\n\n".join(current))

    return result


def health(origin):
    try:
        return requests.get(
            origin + "/health",
            timeout=2,
        ).status_code == 200
    except requests.RequestException:
        return False


def port_busy(host, port):
    with socket.socket() as sock:
        sock.settimeout(0.4)
        return sock.connect_ex((host, port)) == 0


def wait_ready(origin, process=None):
    for _ in range(180):
        if health(origin):
            return

        if process is not None and process.poll() is not None:
            raise RuntimeError(
                "llama-server si è chiuso durante il caricamento."
            )

        time.sleep(1)

    raise RuntimeError(
        "Timeout durante il caricamento di llama.cpp."
    )


def loaded_model(api_base):
    r = requests.get(
        api_base + "/models",
        timeout=10,
    )
    r.raise_for_status()

    models = r.json().get("data") or []

    if not models:
        raise RuntimeError(
            "Nessun modello restituito da /v1/models."
        )

    return models[0]["id"]


def clean_json(raw):
    raw = raw.strip()

    raw = re.sub(
        r"^```(?:json)?\\s*",
        "",
        raw,
        flags=re.I,
    )

    raw = re.sub(
        r"\\s*```$",
        "",
        raw,
    )

    # Caso ideale: risposta composta soltanto dal JSON.
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        # Alcuni modelli aggiungono una spiegazione dopo il JSON.
        # Estraiamo quindi il primo oggetto JSON completo e
        # ignoriamo qualsiasi testo successivo.
        start = raw.find("{")

        if start < 0:
            raise ValueError(
                "Gemma non ha restituito alcun oggetto JSON."
            )

        decoder = json.JSONDecoder()

        try:
            result, _end = decoder.raw_decode(raw[start:])
        except json.JSONDecodeError as error:
            raise ValueError(
                "Risposta Gemma non interpretabile come JSON:\n"
                + raw[:1500]
            ) from error

    if not isinstance(result, dict):
        raise ValueError(
            "Il risultato del proofreading deve essere un oggetto JSON."
        )

    # Una risposta senza il campo richiesto non e' un verdetto "nessun
    # errore": e' una risposta non valida. Confonderle significa dichiarare
    # pulito un capitolo che il modello non ha mai controllato davvero.
    if "issues" not in result:
        raise ValueError(
            'Risposta senza il campo "issues": il modello non ha prodotto '
            "un verdetto."
        )

    issues = result["issues"]

    if not isinstance(issues, list):
        raise ValueError(
            'Il campo "issues" deve essere una lista, non '
            f"{type(issues).__name__}."
        )

    for position, issue in enumerate(issues, 1):
        if not isinstance(issue, dict):
            raise ValueError(
                f"Issue #{position} non e' un oggetto JSON."
            )

    return result


def split_qc_text(text):
    """Split vicino al centro senza spezzare parole se possibile."""

    middle = len(text) // 2
    minimum = min(600, max(100, len(text) // 5))

    candidates = []

    for marker in ("\n\n", ". ", "? ", "! ", "; "):
        left = text.rfind(marker, minimum, middle)
        right = text.find(marker, middle)

        if left >= 0:
            candidates.append(left + len(marker))

        if (
            right >= 0
            and right < len(text) - minimum
        ):
            candidates.append(right + len(marker))

    if candidates:
        split_at = min(
            candidates,
            key=lambda pos: abs(pos - middle),
        )
    else:
        split_at = middle

        # Cerca almeno uno spazio vicino al centro.
        left_space = text.rfind(" ", minimum, middle)
        right_space = text.find(" ", middle)

        choices = [
            pos
            for pos in (left_space, right_space)
            if pos > minimum
            and pos < len(text) - minimum
        ]

        if choices:
            split_at = min(
                choices,
                key=lambda pos: abs(pos - middle),
            )

    return (
        text[:split_at].strip(),
        text[split_at:].strip(),
    )


def request_qc(api_base, model, text):
    response = requests.post(
        api_base + "/chat/completions",
        json={
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT,
                },
                {
                    "role": "user",
                    "content": (
                        "Proofread the following Italian text.\n\n"
                        "--- TEXT ---\n"
                        + text
                        + "\n--- END TEXT ---"
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 800,
            "stream": False,
        },
        timeout=240,
    )

    response.raise_for_status()

    raw = (
        response.json()["choices"][0]
        ["message"]["content"]
    )

    return clean_json(raw)


def inspect_chunk(
    api_base,
    model,
    text,
    *,
    depth=0,
    max_depth=3,
):
    """
    Try normally; if the model produces malformed/runaway JSON,
    automatically split only this problematic block.
    """

    last_error = None

    # Two attempts are enough before changing strategy.
    for attempt in range(1, 3):
        try:
            result = request_qc(
                api_base,
                model,
                text,
            )

            # Sanitize obvious model nonsense immediately.
            clean_issues = []

            for issue in result.get("issues", []):
                if not isinstance(issue, dict):
                    continue

                old = str(
                    issue.get("from") or ""
                ).strip()

                new = str(
                    issue.get("to") or ""
                ).strip()

                try:
                    confidence = float(
                        issue.get("confidence", 0)
                    )
                except (TypeError, ValueError):
                    confidence = 0

                if (
                    not old
                    or not new
                    or old == new
                    or confidence < 0.95
                ):
                    continue

                clean_issues.append(issue)

            return {"issues": clean_issues}

        except (
            requests.Timeout,
            requests.ConnectionError,
            requests.HTTPError,
            ValueError,
            KeyError,
            IndexError,
        ) as error:
            last_error = error

            print(
                f"    ↻ tentativo {attempt}/2 fallito: "
                f"{type(error).__name__}",
                flush=True,
            )

            if attempt < 2:
                time.sleep(1)

    # Same input repeatedly failed: don't keep asking
    # the model exactly the same question.
    if depth >= max_depth or len(text) < 1400:
        raise RuntimeError(
            "Gemma non è riuscito ad analizzare "
            "un sottoblocco anche dopo lo split automatico."
        ) from last_error

    left, right = split_qc_text(text)

    if not left or not right:
        raise RuntimeError(
            "Impossibile dividere ulteriormente "
            "il blocco problematico."
        ) from last_error

    print(
        f"    ↳ split automatico "
        f"{len(text):,} → {len(left):,} + {len(right):,} chars",
        flush=True,
    )

    left_result = inspect_chunk(
        api_base,
        model,
        left,
        depth=depth + 1,
        max_depth=max_depth,
    )

    right_result = inspect_chunk(
        api_base,
        model,
        right,
        depth=depth + 1,
        max_depth=max_depth,
    )

    return {
        "issues": (
            left_result.get("issues", [])
            + right_result.get("issues", [])
        )
    }


# Cambiando prompt o modello un verdetto in cache descrive un controllo che
# non e' piu' quello che si sta chiedendo. Sale quando cambia la validazione.
VALIDATOR_VERSION = 2


def fingerprint(text):
    return hashlib.sha256(
        text.encode("utf-8")
    ).hexdigest()


def qc_fingerprint(text, model):
    return hashlib.sha256(
        json.dumps(
            {
                "text": text,
                "system_prompt": SYSTEM_PROMPT,
                "model": model,
                "validator": VALIDATOR_VERSION,
            },
            sort_keys=True,
            ensure_ascii=False,
        ).encode("utf-8")
    ).hexdigest()


def main():
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: language_qc.py /path/to/book.json"
        )

    config_path = Path(sys.argv[1]).resolve()
    book = config_path.parent

    config = json.loads(
        config_path.read_text(encoding="utf-8")
    )

    translation = config.get("translation", {})

    api_base = str(
        translation.get("base_url")
        or "http://127.0.0.1:1234/v1"
    ).rstrip("/")

    server_model = str(
        translation.get("server_model")
        or "google/gemma-4-12B-it-qat-q4_0-gguf:Q4_0"
    )

    parsed = urlsplit(api_base)
    host = parsed.hostname or "127.0.0.1"
    port = parsed.port or 1234

    origin = f"{parsed.scheme}://{host}:{port}"

    source = book / "text" / "narration_it.txt"

    if not source.is_file():
        raise SystemExit(
            "narration_it.txt non trovato. "
            "Eseguire build_narration.py prima del proofreading."
        )

    if not source.is_file():
        raise SystemExit(
            f"Traduzione non trovata: {source}"
        )

    text = source.read_text(encoding="utf-8")
    source_hash = fingerprint(text)

    work = book / "work" / "language_qc"
    work.mkdir(parents=True, exist_ok=True)

    output = book / "work" / "language_qc.json"

    pieces = chunks(text)
    owned_process = None

    print(f"Testo: {len(pieces)} blocchi")
    print("Modalità: solo errori ad alta confidenza")

    try:
        if health(origin):
            print("✓ llama.cpp già disponibile")
        else:
            if port_busy(host, port):
                raise RuntimeError(
                    f"La porta {port} è occupata da un "
                    "servizio che non sembra llama.cpp."
                )

            print("→ Avvio Gemma per proofreading")

            owned_process = subprocess.Popen(
                [
                    "llama-server",
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
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )

            wait_ready(origin, owned_process)
            print("✓ Gemma pronto")

        model = loaded_model(api_base)

        all_issues = []

        for index, piece in enumerate(pieces, 1):
            checkpoint = (
                work / f"chunk-{index:04d}.json"
            )

            piece_hash = fingerprint(piece)
            piece_qc_hash = qc_fingerprint(piece, model)

            cached = None

            if checkpoint.exists():
                try:
                    cached = json.loads(
                        checkpoint.read_text(
                            encoding="utf-8"
                        )
                    )
                except Exception:
                    cached = None

            if (
                cached
                and cached.get("source_hash") == piece_hash
                and cached.get("qc_hash") == piece_qc_hash
            ):
                result = cached["result"]
                print(
                    f"✓ {index:3}/{len(pieces)} cached"
                )
            else:
                print(
                    f"→ {index:3}/{len(pieces)}",
                    flush=True,
                )

                result = inspect_chunk(
                    api_base,
                    model,
                    piece,
                )

                checkpoint.write_text(
                    json.dumps(
                        {
                            "source_hash": piece_hash,
                            "qc_hash": piece_qc_hash,
                            "result": result,
                        },
                        indent=2,
                        ensure_ascii=False,
                    )
                    + "\n",
                    encoding="utf-8",
                )

            for issue in result.get("issues", []):
                if not isinstance(issue, dict):
                    continue

                old = str(
                    issue.get("from") or ""
                ).strip()

                new = str(
                    issue.get("to") or ""
                ).strip()

                try:
                    confidence = float(
                        issue.get("confidence", 0)
                    )
                except Exception:
                    confidence = 0

                # Deliberately conservative.
                if confidence < 0.95:
                    continue

                if (
                    not old
                    or not new
                    or old == new
                    or old not in piece
                ):
                    continue

                all_issues.append(
                    {
                        "from": old,
                        "to": new,
                        "reason": str(
                            issue.get("reason")
                            or ""
                        ).strip(),
                        "confidence": confidence,
                        "chunk": index,
                    }
                )

        # Deduplicate identical proposals.
        unique = []
        seen = set()

        for issue in all_issues:
            key = (
                issue["from"],
                issue["to"],
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(issue)

        payload = {
            "source_sha256": source_hash,
            "issues": unique,
        }

        output.write_text(
            json.dumps(
                payload,
                indent=2,
                ensure_ascii=False,
            )
            + "\n",
            encoding="utf-8",
        )

        print()
        print(
            f"Proposte ad alta confidenza: "
            f"{len(unique)}"
        )
        print(f"Report: {output}")

        if unique:
            print()

            for n, issue in enumerate(
                unique,
                1,
            ):
                print(
                    f"{n:2}. {issue['from']}"
                )
                print(
                    f"    → {issue['to']}"
                )
                print(
                    f"    {issue['reason']} "
                    f"({issue['confidence']:.0%})"
                )

            # 2 = review required, not a crash.
            raise SystemExit(2)

        print("✓ Nessun errore linguistico evidente")

    finally:
        if owned_process is not None:
            print("→ Spengo llama.cpp...")
            owned_process.terminate()

            try:
                owned_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                owned_process.kill()

            print("✓ llama.cpp spento")


if __name__ == "__main__":
    main()
