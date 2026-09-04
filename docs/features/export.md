# Export

Assembla i segmenti audio generati in un M4B con copertina e metadata, e lo porta
dentro il progetto-libro.

Sono **due** job di Pandrator, non uno: prima l'*assembly* incolla i segmenti in
un'unica traccia applicando pause, room tone, metadata e copertina; poi lo stage
`export` impacchetta quel risultato. Questo stadio li lancia in ordine, attende
entrambi e scarica l'artefatto.

## Sub-features

- costruzione delle impostazioni da `book.json` (`output.format`, `bitrate`, titolo,
  autore, lingua)
- upload della copertina, una volta sola: l'artifact id resta in `session.json`
- assembly dei segmenti nella traccia unica, con avanzamento per segmento
- export e download dell'artefatto in `books/<slug>/output/<slug>.m4b`

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
- **Saltare l'assembly non dà un errore comprensibile.** Lo stage `export` da solo
  risponde 409 `Stage 'export' is missing a required input artifact`, che non dice
  qual è l'input mancante. L'input è la traccia assemblata: `POST
  /sessions/<id>/output-assemblies` con la generation run completata.
- **I capitoli non arrivano dal testo.** Pandrator li ricava dai segmenti marcati
  `chapter_marker`, e `prepare_text` marca solo quello che riconosce come titolo: sul
  primo libro reale sono usciti 3763 segmenti tutti `paragraph` e **zero capitoli**.
  L'M4B è valido e ha copertina e metadata, ma senza navigazione. Per averla servono
  intestazioni riconoscibili nel testo di narrazione, cosa che l'estrazione da PDF
  in genere non conserva.
- **Il bitrate richiesto non è quello che esce.** Con `192k` su una sorgente mono a
  24 kHz l'encoder AAC si ferma intorno ai 92 kbps: 10 ore stanno in ~394 MB. Non è
  un problema di qualità a questa frequenza, ma `book.json` dice una cosa e il file
  ne dice un'altra.
- La copertina deve essere JPEG, PNG o WebP e stare sotto i 25 MiB — limite di
  Pandrator, non nostro. Senza copertina l'export procede comunque, dicendolo.
- L'upload della copertina è ricordato per `nome:dimensione`: sostituendo il file con
  uno di dimensione diversa viene ricaricato, con la stessa dimensione no.
- Il file viene scritto prima come `.m4b.part` e poi rinominato: un download
  interrotto non lascia un M4B mezzo scritto al posto di uno buono.
- Rilanciare `export` rifà l'assemblaggio da zero e sovrascrive l'M4B: è idempotente
  ma non è gratis, su un libro lungo.
