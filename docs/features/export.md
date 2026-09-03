# Export

Assembla i segmenti audio generati in un M4B con capitoli, copertina e metadata, e
lo porta dentro il progetto-libro.

L'assemblaggio lo fa lo stage `export` di Pandrator; questo stadio costruisce le
impostazioni da `book.json`, carica la copertina, attende il job e scarica il
risultato.

## Sub-features

- costruzione delle impostazioni da `book.json` (`output.format`, `bitrate`, titolo,
  autore, lingua)
- upload della copertina, una volta sola: l'artifact id resta in `session.json`
- attesa del job con avanzamento
- download dell'artefatto in `books/<slug>/output/<slug>.m4b`

## How to get to it

Serve un `generate` completato:

    ./audiobook start
    ./audiobook export nome-libro

Risultato:

    books/<slug>/output/<slug>.m4b

## Driving it

    ./audiobook export nome-libro; echo "exit=$?"

Stato dell'export senza rilanciarlo:

    python3 -m json.tool books/<slug>/work/pandrator/session.json

Vedere se l'audio a monte è pronto:

    ./audiobook info nome-libro

## Where it lives

- `scripts/export_m4b.py`
- `audiobook` — funzione `export_book`
- `books/<slug>/work/pandrator/session.json` — `export_job_id`, `export_artifact_id`,
  `cover_artifact_id`
- Contratto a monte: `~/src/Pandrator` — stage `export`, sezione di settings `output`

## Gotchas

- **Rifiuta di partire se `generate_audio` non è `completed`**, e dice in che stato è.
  È una guardia: senza segmenti non c'è niente da assemblare.
- La copertina deve essere JPEG, PNG o WebP e stare sotto i 25 MiB — limite di
  Pandrator, non nostro. Senza copertina l'export procede comunque, dicendolo.
- L'upload della copertina è ricordato per `nome:dimensione`: sostituendo il file con
  uno di dimensione diversa viene ricaricato, con la stessa dimensione no.
- I capitoli li ricava Pandrator dalla struttura del testo preparato, non da
  `book.json`: un testo senza struttura dà un M4B con un capitolo solo.
- Il file viene scritto prima come `.m4b.part` e poi rinominato: un download
  interrotto non lascia un M4B mezzo scritto al posto di uno buono.
- Rilanciare `export` rifà l'assemblaggio da zero e sovrascrive l'M4B: è idempotente
  ma non è gratis, su un libro lungo.
