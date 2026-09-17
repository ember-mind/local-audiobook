# Proofread

QC linguistico del testo di narrazione con un LLM locale, poi applicazione delle
correzioni: prima quelle sicure, poi le decisioni umane.

## Sub-features

- `language-qc` — legge `text/narration_it.txt`, scrive `work/language_qc.json`
- `resolve-qc` — applica le correzioni sicure di
  `work/language_qc_safe_fixes.json` → `text/narration_final_it.txt`
- `apply-fixes` — applica le decisioni umane di
  `work/language_qc_manual_fixes.json` → `text/narration_reviewed_it.txt`

## How to get to it

    ./audiobook language-qc nome-libro

Se trova problemi da rivedere esce **2** e lascia il verdetto in
`books/<slug>/work/language_qc.json`. Le decisioni umane si scrivono in
`books/<slug>/work/language_qc_manual_fixes.json`, poi:

    ./audiobook resolve-qc nome-libro
    ./audiobook apply-fixes nome-libro

Oppure, per fare resolve-qc + apply-fixes + layout in una volta:

    ./audiobook finish nome-libro

Senza file di decisioni `apply-fixes` fa passare il testo invariato: un libro il cui
QC non ha richiesto interventi attraversa comunque lo stadio.

### Formato della whitelist sicura

`work/language_qc_safe_fixes.json` — la chiave è il `from` dell'issue, il valore il
`to` atteso:

    {
      "safe": {
        "nella affascinante": "nell'affascinante",
        "produzione prolifico": "produzione prolifica"
      }
    }

La correzione parte solo se la proposta dell'LLM coincide **esattamente** col valore
e se la stringa compare una volta sola. Senza il file nessuna correzione è
automatica: è il default di un libro nuovo, tutti gli issue vanno in revisione.

### Formato delle decisioni

`work/language_qc_manual_fixes.json` — dati per libro, non codice:

    {
      "operations": [
        {"issue": 1, "kind": "exact", "from": "Risa di cuore.",
         "to": "Risero di cuore.", "expected": 1, "note": "perché"},
        {"issue": "13+14", "kind": "regex", "pattern": "...",
         "replacement": "...", "expected": 1, "flags": ["ignorecase"]}
      ],
      "rejected": {"11": "frase grammaticalmente valida"},
      "forbidden": ["hasorta"],
      "structural_remaining": {"issues": [2, 9], "token": "OPPOSITO"}
    }

Il formato completo è documentato in testa a `scripts/apply_review_fixes.py`.

## Driving it

    ./audiobook language-qc nome-libro; echo "exit=$?"
    ./audiobook resolve-qc nome-libro
    ./audiobook apply-fixes nome-libro
    ./audiobook finish nome-libro

Leggere il verdetto e il resoconto:

    python3 -m json.tool books/<slug>/work/language_qc.json | head -60
    python3 -m json.tool books/<slug>/work/language_qc_manual_resolution.json | head -40

## Where it lives

- `scripts/language_qc.py` — chunking, chiamate LLM, retry, timeout, parsing JSON
- `scripts/resolve_language_qc.py` — motore; la whitelist sta nei dati del libro
- `scripts/apply_review_fixes.py` — motore generico; le correzioni stanno nei dati
- `audiobook` — `language_qc_book`, `resolve_qc_book`, `apply_fixes_book`, `finish_book`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/work/language_qc.json`
  — esempio di verdetto reale
- `books/dressed-.../work/language_qc_safe_fixes.json` — esempio di whitelist (42 voci)
- `books/think/work/language_qc_manual_fixes.json` — esempio di decisioni umane
  (67 operazioni, 11 issue respinte)

## Gotchas

- Exit **2** significa "serve una revisione umana", non "errore". `prepare` lo
  interpreta e stampa REVIEW REQUIRED; qualsiasi altro chiamante deve fare lo stesso.
- **`apply-fixes` non scrive niente se una sostituzione non trova quello che si
  aspetta.** `expected` è la guardia contro l'applicazione di una patch a un testo
  diverso da quello per cui era scritta: mezza patch è peggio di nessuna patch.
  Ometterlo, o mettere `"optional": true`, disattiva la guardia per quella riga: da
  usare solo per le ricuciture opportunistiche (un page break che può non esserci).
- `forbidden` è il controllo opposto: token che dopo le correzioni **non** devono più
  esistere. Se ne resta uno, lo stadio non scrive.
- `resolve-qc` verifica che `language_qc.json` appartenga alla versione corrente di
  `narration_it.txt` (via sha256) e si ferma se non torna. Rifare `narrate` invalida
  un QC già fatto.
- **Il QC guarda la lingua, non la pronuncia.** Tabelle ASCII, formule, LaTeX
  rimasto dalla conversione (`$\\forall x$`), simboli nudi (`→`, `¬`, `&`) passano
  il QC e poi il TTS li legge come rumore. Si convertono in parole con le stesse
  operazioni, `kind: "regex"` (esempio: le 40 operazioni `tts-*` di `think`, che
  riscrivono tre tabelle di verità, i quantificatori e il teorema di Bayes).
- **Un simbolo che il PDF non ha estratto non si recupera dal testo.** In `think` il
  predicato φ è sparito da tutte le formule, in inglese come in italiano: il libro
  però lo nomina a parole ("la lettera greca phi"), e da lì si ricostruisce. Vale la
  pena controllare l'inglese prima di dare la colpa alla traduzione.
- **Una risposta senza il campo `issues` non è un testo pulito.** Prima
  `clean_json("{}")` restituiva `{"issues": []}`: un modello che sbagliava il
  formato produceva un capitolo dichiarato senza errori. Ora è un errore, e
  rientra nei retry dello stadio.
- La cache per chunk in `work/language_qc/` è legata a testo + prompt + modello +
  versione del validatore. Un verdetto salvato prima di questa modifica non viene
  riusato: lo stadio lo rifà.
- La whitelist e le decisioni sono **dati del libro**, non codice: un libro nuovo
  parte senza whitelist e con tutti gli issue in revisione. Non si aggiungono
  correzioni dentro gli script.
- L'LLM propone correzioni sbagliate con confidenza 0.99: inventa parole che non
  esistono e "corregge" termini tecnici resi bene. Va letto issue per issue col
  contesto sotto gli occhi, e `rejected` serve a scrivere perché.
- Le run vecchie restano in `work/` con il timestamp nel nome
  (`language_qc-full-book-<data>.json`): nessuno le cancella, crescono per sempre.
- L'LLM risponde JSON; il parsing ha retry e autosplit dei chunk, segno che fallisce
  regolarmente su chunk lunghi. Un chunk che non torna JSON valido dopo i retry ferma
  lo stadio.
