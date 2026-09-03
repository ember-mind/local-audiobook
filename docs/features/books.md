# Books

Ogni libro è una cartella autonoma sotto `books/<slug>/` con la sua `book.json`.
Tutti i comandi della pipeline prendono lo slug.

## Sub-features

- `new` — copia il sorgente, crea slug, alberatura e `book.json` di default
- `books` — elenca slug e titolo di tutti i progetti
- `info` — config, stato di ogni stadio della pipeline, cover e marcatori

## How to get to it

    ./audiobook new ~/Downloads/libro.pdf     # PDF, EPUB o TXT
    ./audiobook books
    ./audiobook info nome-libro

Alberatura creata:

    books/<slug>/
      book.json        configurazione
      source/          originale copiato come original.<ext>
      text/            testo estratto, tradotto, narrazione
      work/            file intermedi, checkpoint, report QC
      assets/          cover
      output/          audiobook finale
      README.md

## Driving it

    ./audiobook new /path/assoluto/libro.pdf
    ./audiobook books
    ./audiobook info nome-libro

    # leggere la config senza CLI
    python3 -c "import json;print(json.load(open('books/nmmng/book.json')))"

## Where it lives

- `audiobook` — funzioni `new_book`, `book_info`, `list_books`
- `books/nmmng/book.json` — config minima, come la genera `new`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/book.json`
  — config completa: `translation.context`, `terminology`, `instructions`, `narration`

## Gotchas

- `info` è il modo più rapido di sapere a che punto è un libro: elenca gli stadi con
  `✓`/`○` in base all'artefatto che ognuno produce. Un `✓` prova che il file esiste,
  non che sia aggiornato rispetto agli stadi precedenti.
- `info` accetta sia `translation.server_model` (quello che scrive `new`) sia il
  vecchio `translation.model`, per le config create prima.
- `new` è idempotente sullo slug: se la cartella esiste stampa `EXISTS` e non tocca
  niente. Per rigenerare la config bisogna cancellare a mano.
- Lo slug arriva dal nome del file, non dal titolo interno: `Dressed_Landis.pdf`
  diventa uno slug lungo e brutto che poi va digitato in ogni comando. Rinominare il
  file *prima* di `new`.
- I campi ricchi (`context`, `terminology`, `instructions`, `narration`) **non** sono
  generati da `new`: si aggiungono a mano, e senza `narration` la fase narration non parte.
- `books/` è in `.gitignore`: niente qui è in git, e niente qui è ricostruibile da
  git. I sorgenti sono protetti da copyright e la cartella pesa centinaia di MB.
  Un backup dei libri va fatto fuori da git.
