# Chapters

Scrive i capitoli dentro un M4B già prodotto, così l'audiolibro si può navigare.
Rimux, non ricodifica: qualche secondo, nessuna perdita di qualità.

## Sub-features

- `chapters` — legge `book.json`, trova i segmenti di inizio, riscrive il contenitore

## How to get to it

I capitoli sono **dati del libro**, come i marcatori di narrazione. In `book.json`:

    "chapters": [
      {"title": "Prefazione", "start_marker": "Prefazione di Deborah Nadoolman"},
      {"title": "Anni '20",   "start_marker": "Negli anni '20, Hollywood era"}
    ]

`start_marker` è l'inizio del primo segmento del capitolo, copiato da
`text/narration_ready_it.txt`. Con la chiave presente **non serve nessun comando
in più**: `export` scrive i capitoli da sé, subito dopo aver scaricato l'M4B.

    ./audiobook export nome-libro

Il comando separato resta per riscriverli senza rifare l'export, per esempio dopo
aver corretto un marcatore:

    ./audiobook chapters nome-libro

## Driving it

    ./audiobook chapters nome-libro; echo "exit=$?"

Verificare il risultato:

    ffprobe -v error -show_chapters -print_format json books/<slug>/output/<slug>.m4b

Vedere i paragrafi da cui ricavare i marcatori:

    grep -n "" books/<slug>/text/narration_ready_it.txt | head -40

## Where it lives

- `scripts/add_chapters.py`
- `audiobook` — `chapters_book`, `has_chapters`, e la chiamata dentro `export_book`
- `books/<slug>/book.json` — la chiave `chapters`
- I tempi vengono dal manifest dell'assembly: `takes[].duration_ms` +
  `silence_after_ms`, sommati in ordine di `ordinal`

## Gotchas

- **L'export cancella i capitoli** ogni volta che riscrive il file: per questo li
  riscrive lui stesso alla fine. Chi lancia `add_chapters.py` a mano deve rifarlo
  dopo ogni export.
- Se i capitoli non si scrivono, l'export **non** si annulla: l'M4B resta sul disco
  senza navigazione e il comando esce 1, dicendo quale marcatore non ha trovato.
- Senza la chiave `chapters` l'export non fallisce: lo dice e va avanti.
- **O tutti o nessuno.** Se un solo marcatore non trova il suo segmento, lo script
  non scrive niente e dice quali: un M4B con metà capitoli è peggio di uno senza.
- I marcatori vanno confrontati **normalizzati**: lo stage `clean_source` di
  Pandrator converte `«»` in virgolette dritte, quindi un marcatore copiato dalla
  narrazione non combacerebbe mai alla lettera. Lo script appiattisce virgolette,
  trattini lunghi e spazi prima di confrontare.
- Un marcatore troppo corto può corrispondere a più segmenti: in quel caso lo
  script si ferma e chiede di allungarlo. 60 caratteri di solito bastano.
- **ffmpeg fa partire il primo capitolo da 0** comunque: se il primo marcatore non
  è all'inizio del libro, tutto ciò che lo precede finisce dentro quel capitolo.
  Meglio dichiarare un capitolo esplicito per la prefazione.
- La riscrittura mappa solo audio e copertina (`-map 0:a -map 0:v?`). Con `-map 0`
  il secondo giro fallirebbe: la traccia dati dei capitoli scritta dal giro
  precedente non è accettata dal muxer ipod.
- Il file viene scritto di fianco e poi rinominato: un'interruzione non lascia
  l'audiolibro a metà.
- I capitoli seguono la **prosa**, non l'impaginazione: in un libro molto
  illustrato un capitolo fatto quasi solo di didascalie risulta cortissimo.
