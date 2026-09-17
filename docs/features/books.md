# Books

Ogni libro è una cartella autonoma sotto `books/<slug>/` con la sua `book.json`.
Tutti i comandi della pipeline prendono lo slug.

## Sub-features

- `new` — copia il sorgente, crea slug, alberatura e `book.json` di default
- `books` — elenca slug e titolo di tutti i progetti
- `info` — config, stato e freschezza di ogni stadio, cover e marcatori
- `prune` — cancella da `work/` quello che è sicuro ricostruire

## How to get to it

I comandi si lanciano con `./audiobook` dalla radice del repo, oppure da qualunque
directory se c'e' un symlink nel PATH:

    ln -sfn "$PWD/audiobook" ~/.local/bin/audiobook

Lo script risolve il symlink prima di calcolare `ROOT`, quindi trova `books/` anche
lanciato da fuori.

    ./audiobook new ~/Downloads/libro.pdf     # PDF o TXT
    ./audiobook books
    ./audiobook info nome-libro

`info` marca ogni stadio `✓` fatto, `○` da fare, `⚠` da rifare. `prune` mostra
cosa si può cancellare e non cancella niente finché non glielo si dice:

    ./audiobook prune nome-libro              # mostra e basta
    ./audiobook prune nome-libro --yes        # cancella davvero
    ./audiobook prune nome-libro --keep 0     # anche le run di QC archiviate

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
    ./audiobook prune nome-libro
    ./audiobook prune nome-libro --yes --keep 0

    # leggere la config senza CLI
    python3 -c "import json;print(json.load(open('books/nmmng/book.json')))"

## Where it lives

- `audiobook` — funzioni `new_book`, `book_info`, `list_books`, `prune_work`
- `scripts/prune_work.py` — l'allowlist di cosa è cancellabile
- `books/nmmng/book.json` — config minima, come la genera `new`
- `books/dressed-a-century-of-hollywood-costume-design-landis-deborah-nadoolman/book.json`
  — config completa: `translation.context`, `terminology`, `instructions`, `narration`

## Gotchas

- **Un comando per libro alla volta.** Ogni stadio prende `books/<slug>/work/.lock`
  (una directory, quindi la presa è atomica) e lo lascia uscendo, anche su Ctrl-C.
  Un secondo comando sullo stesso libro si ferma dicendo chi sta lavorando; un lock
  rimasto da un processo morto viene riconosciuto e rimosso. Stadi concatenati nello
  stesso processo (`generate` → `prepare-audio`, `export` → `chapters`) riusano il
  lock che hanno già.

- **`info` distingue "fatto" da "da rifare".** Dove lo stadio ha annotato lo sha256
  del proprio input — `language-qc` e `prepare-audio` lo fanno — il confronto è sui
  contenuti ed è esatto. Per gli altri resta la mtime, che è grossolana: rifare uno
  stadio senza cambiare niente sposta la data e può far comparire un `⚠` innocuo.
  L'hash vince quando c'è, proprio per non gridare al lupo. Lo registrano
  `language-qc`, `prepare-audio` e — da quando esiste `export_sha256` — anche
  `export`.
- `prune` lavora su una **allowlist**: audio di prova, esperimenti di chunking, run
  di QC archiviate. Tutto il resto è intoccabile per costruzione — il checkpoint di
  traduzione (ore di LLM), la cache del QC, la sessione Pandrator. Aggiungendo una
  categoria, aggiungerla lì e non altrove.
- `prune` senza `--yes` non cancella niente: `books/` non è in git e non c'è undo.
- `info` accetta sia `translation.server_model` (quello che scrive `new`) sia il
  vecchio `translation.model`, per le config create prima.
- `new` è idempotente sullo slug: se la cartella esiste stampa `EXISTS` e non tocca
  niente. Per rigenerare la config bisogna cancellare a mano.
- Lo slug arriva dal nome del file, non dal titolo interno: `Dressed_Landis.pdf`
  diventa uno slug lungo e brutto che poi va digitato in ogni comando. Rinominare il
  file *prima* di `new`.
- I campi ricchi (`source.body`, `context`, `terminology`, `instructions`, `narration`) **non** sono
  generati da `new`: si aggiungono a mano, e senza `narration` la fase narration non parte.
- `books/` è in `.gitignore`: niente qui è in git, e niente qui è ricostruibile da
  git. I sorgenti sono protetti da copyright e la cartella pesa centinaia di MB.
  Un backup dei libri va fatto fuori da git.
