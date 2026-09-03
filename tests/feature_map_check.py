#!/usr/bin/env python3
"""Guardia meccanica della Feature Map.

Verifica, senza capire il senso delle schede, le tre derive che si possono
prendere automaticamente:

  verità      mappa → codice: path citati esistono, comandi citati sono reali
  copertura   codice → mappa: comandi e script esistenti sono nominati
  puntatori   i comandi che il CLI stampa a schermo esistono

La quarta deriva — comportamento nuovo su un comando che c'era già — non è
verificabile qui: la prende solo una passata semantica.

    python3 tests/feature_map_check.py
"""

from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parent.parent
FEATURES = ROOT / "docs" / "features"
CLI = ROOT / "audiobook"

# Comandi documentati nell'indice come non implementati: la mappa li nomina
# proprio per dire che non esistono, quindi non sono errori di verità.
KNOWN_MISSING = {"generate"}

# Backup manuali e sorgenti superati: non fanno parte della superficie utente.
SKIP_SCRIPT_SUFFIXES = (".old",)
SKIP_SCRIPT_PATTERN = re.compile(r"\.pre-")

failures = []


def fail(check, message):
    failures.append(f"[{check}] {message}")


def cards():
    return sorted(p for p in FEATURES.glob("*.md") if p.name != "README.md")


def cli_commands():
    """Rami del `case` in ./audiobook, cioè i comandi che esistono davvero."""
    text = CLI.read_text(encoding="utf-8")
    body = text.split('case "${1:-}" in', 1)[-1]
    found = set()
    for line in body.splitlines():
        match = re.match(r"^ {2}([a-z][a-z-]*)\)\s*$", line)
        if match:
            found.add(match.group(1))
    return found


def cited_commands(text):
    return set(re.findall(r"\./audiobook ([a-z][a-z-]*)", text))


# Solo i path repo-relativi sono verificabili: una rotta HTTP (`/readyz`) o un
# artefatto dentro un libro (`text/book_it.txt`) non sono file di questo repo.
REPO_PREFIXES = (
    "scripts/", "qwen/", "config/", "docs/", "tests/", "patches/",
    "environments/", "books/", "logs/", "run/",
)

REPO_FILES = ("audiobook", "setup.sh", "README.md", ".gitignore")

# Alberi che stanno fuori da git di proposito: progetti-libro, log, pidfile,
# virtualenv. Una scheda che ne cita uno sta facendo un esempio o indicando un
# artefatto di runtime, non promettendo un file del repo — su un clone fresco
# non esistono, e pretenderli renderebbe la guardia rossa per tutti tranne chi
# ha gia\' lavorato qui. I path sotto questi prefissi non vengono verificati.
DATA_ROOTS = (
    "books/",
    "logs/",
    "run/",
    ".secrets/",
    "environments/whisper",
)


def cited_paths(text):
    """Path in backtick che indicano un file o una cartella di questo repo."""
    out = set()
    for token in re.findall(r"`([^`\n]+)`", text):
        token = token.strip()
        if " " in token or "<" in token or "*" in token:
            continue
        if not re.match(r"^[A-Za-z0-9_./-]+$", token):
            continue
        if token.startswith(REPO_PREFIXES) or token in REPO_FILES:
            out.add(token.rstrip("/"))
    return out


def repo_scripts():
    out = set()
    for path in (ROOT / "scripts").glob("*.py"):
        if path.name.endswith(SKIP_SCRIPT_SUFFIXES):
            continue
        if SKIP_SCRIPT_PATTERN.search(path.name):
            continue
        out.add(f"scripts/{path.name}")
    return out


def main():
    if not FEATURES.is_dir():
        print(f"✗ Feature Map assente: {FEATURES}")
        return 1

    card_paths = cards()

    if not card_paths:
        print(f"✗ Nessuna scheda in {FEATURES}")
        return 1

    all_text = "\n".join(p.read_text(encoding="utf-8") for p in card_paths)
    index_text = (FEATURES / "README.md").read_text(encoding="utf-8")
    commands = cli_commands()

    if not commands:
        fail("verità", "nessun ramo `case` trovato in ./audiobook: parser da rivedere")

    # ── verità: struttura delle schede ────────────────────────────────────
    required = ("## Sub-features", "## How to get to it", "## Driving it",
                "## Where it lives", "## Gotchas")

    for path in card_paths:
        text = path.read_text(encoding="utf-8")
        for section in required:
            if section not in text:
                fail("verità", f"{path.name}: manca la sezione {section!r}")

    # ── verità: ogni path citato esiste ───────────────────────────────────
    skipped = 0

    for path in card_paths:
        text = path.read_text(encoding="utf-8")
        for cited in sorted(cited_paths(text)):
            if (ROOT / cited).exists():
                continue

            # `cited` arriva senza slash finale: confronta anche la radice nuda.
            if cited.startswith(DATA_ROOTS) or any(
                cited == root.rstrip("/") for root in DATA_ROOTS
            ):
                skipped += 1
                continue

            fail("verità", f"{path.name}: path inesistente `{cited}`")

    # ── verità: ogni comando citato è un ramo reale ───────────────────────
    for path in card_paths:
        text = path.read_text(encoding="utf-8")
        for command in sorted(cited_commands(text) - commands - KNOWN_MISSING):
            fail("verità", f"{path.name}: `./audiobook {command}` non esiste")

    # ── copertura: ogni comando è nominato da una scheda ──────────────────
    documented = cited_commands(all_text)

    for command in sorted(commands - documented):
        fail("copertura", f"comando `./audiobook {command}` non documentato")

    # ── copertura: ogni script è nominato da una scheda ───────────────────
    for script in sorted(repo_scripts()):
        if script not in all_text:
            fail("copertura", f"{script} non nominato da nessuna scheda")

    # ── copertura: ogni scheda è nell'indice ──────────────────────────────
    for path in card_paths:
        if path.name not in index_text:
            fail("copertura", f"{path.name} manca dall'indice README")

    # ── puntatori: i comandi che il CLI stampa esistono ───────────────────
    cli_text = CLI.read_text(encoding="utf-8")

    for command in sorted(cited_commands(cli_text) - commands):
        fail("puntatori", f"./audiobook stampa `./audiobook {command}`, che non esiste")

    # ── esito ─────────────────────────────────────────────────────────────
    summary = f"Feature Map · {len(card_paths)} schede · {len(commands)} comandi"

    if skipped:
        summary += f" · {skipped} path di dati non verificati"

    print(summary)

    if not failures:
        print("✓ mappa e codice allineati")
        return 0

    print()
    for line in failures:
        print(f"✗ {line}")
    print()
    print(f"✗ {len(failures)} disallineamento/i")
    return 1


if __name__ == "__main__":
    sys.exit(main())
