from pathlib import Path
import requests
import json
import time

BASE_URL = "http://localhost:1234/v1"
MODEL = "gemma-4-12b-it-qat"

SOURCE_FILE = Path("source_en_clean.txt")
OUTPUT_FILE = Path("book_it.txt")
CHECKPOINT_FILE = Path("translation_checkpoint.json")

CHUNK_SIZE = 3500


SYSTEM_PROMPT = """
You are a professional literary and technical translator working from English into Italian.

The text is from a nonfiction university-level book about fashion design,
pattern cutting, sustainability, textiles, and zero waste fashion.

Translate it into polished, idiomatic Italian suitable for a professionally
published Italian edition and for audiobook narration.

Never invent terminology, characters, symbols, explanations, or parenthetical glosses that are not present in the source.

If a technical term is uncertain, translate conservatively using ordinary Italian rather than inventing a specialized term.

Do not introduce non-Latin characters unless they are present in the source.

Perform a final silent proofreading pass for:
- Italian grammar
- agreement of articles, nouns and adjectives
- accidental foreign characters
- mistranslated technical terminology
- obvious semantic inconsistencies

For sewing terminology:
running stitch = punto filza
woven cloth = tessuto
off-grain = fuori drittofilo / fuori filo, according to context
gusset = tassello
yoke = carré
seam = cucitura

REQUIREMENTS

1. Preserve the exact meaning and all factual information.
2. Write natural, fluent Italian. Never reproduce English syntax mechanically.
3. Prefer terminology actually used by Italian fashion-design and pattern-making professionals.
4. Preserve the author's tone: academic but accessible, thoughtful and conversational.
5. Do not summarize, shorten, expand, explain, or add commentary.
6. Preserve paragraphs, headings, figure captions, citations and [[Chapter]] markers.
7. Keep names, project names, dates, measurements and references accurate.
8. Maintain terminology consistently throughout the entire book.
9. If a literal translation sounds unnatural in Italian, translate the intended meaning instead.
10. Return only the Italian translation.
11. Be grammatically meticulous. Re-read the Italian before returning it.
12. Do not creatively rewrite headings or titles.
13. Avoid false friends and English calques.
14. Prefer established Italian terminology over literal translation.
15. Maintain terminology choices made in previous passages.

TERMINOLOGY

zero waste = zero waste
zero waste fashion design = design della moda zero waste
fashion design = design della moda
fashion designer = fashion designer
fabric = tessuto
textile = tessile
fabric waste = scarto di tessuto / scarti di tessuto
textile waste = scarti tessili
pre-consumer waste = scarti pre-consumo
post-consumer waste = scarti post-consumo
pattern = cartamodello
wrap skirt = gonna a portafoglio
garment = capo / capo d'abbigliamento
cutting-room floor = reparto taglio
call to arms = chiamata all'azione
exclusionary = escludente
from history to now = dalla storia a oggi
restorative and regenerative by design = riparativa e rigenerativa per sua stessa concezione
holistic resourcefulness = uso attento, integrato e parsimonioso delle risorse
""".strip()


def make_chunks(text, max_chars=6000):
    paragraphs = text.split("\n\n")

    chunks = []
    current = []

    for paragraph in paragraphs:
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        candidate = "\n\n".join(current + [paragraph])

        if len(candidate) > max_chars and current:
            chunks.append("\n\n".join(current))
            current = [paragraph]
        else:
            current.append(paragraph)

    if current:
        chunks.append("\n\n".join(current))

    return chunks


def translate(chunk, previous_context=""):
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
        f"{BASE_URL}/chat/completions",
        json={
            "model": MODEL,
            "messages": [
                {
                    "role": "system",
                    "content": SYSTEM_PROMPT
                },
                {
                    "role": "user",
                    "content": f"""
{context}

Translate the following text:

--- SOURCE ---
{chunk}
--- END SOURCE ---
"""
                }
            ],
            "temperature": 0.1,
        },
        timeout=600,
    )

    response.raise_for_status()

    data = response.json()

    result = data["choices"][0]["message"]["content"].strip()

    return result, data.get("usage", {})


source = SOURCE_FILE.read_text(encoding="utf-8")

chunks = make_chunks(source, CHUNK_SIZE)

print(f"Book divided into {len(chunks)} chunks.")


# Resume support
completed = {}

if CHECKPOINT_FILE.exists():
    completed = json.loads(
        CHECKPOINT_FILE.read_text(encoding="utf-8")
    )

    print(f"Checkpoint found: {len(completed)} chunks already translated.")


previous_context = ""

for i, chunk in enumerate(chunks):

    key = str(i)

    if key in completed:
        print(f"[{i+1}/{len(chunks)}] already translated")
        previous_context = completed[key][-1500:]
        continue

    print()
    print(f"[{i+1}/{len(chunks)}] Translating...")
    print(f"Source characters: {len(chunk)}")

    for attempt in range(1, 4):

        try:

            translation, usage = translate(
                chunk,
                previous_context
            )

            break

        except Exception as e:

            print(f"Attempt {attempt} failed: {e}")

            if attempt == 3:
                raise

            time.sleep(5)

    completed[key] = translation

    CHECKPOINT_FILE.write_text(
        json.dumps(
            completed,
            ensure_ascii=False,
            indent=2
        ),
        encoding="utf-8"
    )

    previous_context = translation[-1500:]

    print(
        f"✓ {len(translation)} chars "
        f"| {usage.get('prompt_tokens', '?')} input "
        f"| {usage.get('completion_tokens', '?')} output"
    )


final_text = "\n\n".join(
    completed[str(i)]
    for i in range(len(chunks))
)

OUTPUT_FILE.write_text(
    final_text + "\n",
    encoding="utf-8"
)

print()
print("====================================")
print("✓ TRANSLATION COMPLETE")
print(f"✓ Saved to {OUTPUT_FILE}")
print("====================================")