# Local Audiobook

Pipeline locale per trasformare libri in audiolibri italiani usando:

- Pandrator
- Qwen3-TTS official
- voice cloning locale
- Apple Metal / MPS
- room tone naturale
- M4B come output finale

**Feature Map: [`docs/features/`](docs/features/README.md)** — cosa fa ogni comando,
come lanciarlo, dove vive nel codice, quali trappole ha. Da leggere prima dei sorgenti.

## Percorsi

Repository:

    ~/Code/solo/projects/local-audiobook

Pandrator (`PANDRATOR_HOME`):

    ~/src/Pandrator

Qwen (`QWEN_HOME`):

    ~/src/qwen3-tts-official

## Uso quotidiano

Una volta sola, per non perdere più una generazione lunga se l'adapter muore:

    ./audiobook daemon install

Controllare che tutto sia a posto:

    ./audiobook doctor

Avviare tutto:

    ./audiobook start

Stato, log, web UI, spegnimento:

    ./audiobook status
    ./audiobook logs
    ./audiobook open
    ./audiobook stop

## Pipeline

    ./audiobook new /path/to/libro.pdf
    ./audiobook prepare nome-libro        extract → clean → translate → QC → narrate → proofread

`prepare` si ferma e chiede una revisione umana quando il QC linguistico trova
qualcosa (exit 2), e chiede i marcatori di narrazione se mancano da `book.json`
(exit 3). Dopo la revisione:

    ./audiobook finish nome-libro         resolve-qc → apply-fixes → layout
    ./audiobook prepare-audio nome-libro
    ./audiobook generate nome-libro
    ./audiobook export nome-libro         → books/nome-libro/output/nome-libro.m4b
    ./audiobook chapters nome-libro       capitoli, senza ricodificare

Ogni stadio esiste anche come comando singolo. `./audiobook` senza argomenti li elenca,
`./audiobook info nome-libro` dice a che punto è un libro: `✓` fatto, `○` da fare,
`⚠` da rifare perché l'input è cambiato.

### Fare spazio

`work/` accumula audio di prova ed esperimenti chiusi — su un libro reale sono
arrivati a 118 MB su 119. Per recuperarli:

    ./audiobook prune nome-libro          # mostra cosa toglierebbe
    ./audiobook prune nome-libro --yes    # lo toglie davvero

Cancella solo da una lista chiusa di cose ricostruibili. Il checkpoint di traduzione,
la cache del QC e la sessione Pandrator non vengono mai toccati.

### Marcatori di narrazione

`narrate` ritaglia il corpo del libro, saltando indice, note e apparati. I marcatori
vanno in `book.json`, presi dal testo tradotto (`text/book_it.txt`):

    "narration": {
      "start_marker": "Prefazione di …",
      "end_marker": "RINGRAZIAMENTI"
    }

### Decisioni manuali sul QC

`apply-fixes` legge `work/language_qc_manual_fixes.json`, se c'è: le correzioni sono
dati per libro, non codice. Formato e guardie sono documentati in testa a
`scripts/apply_review_fixes.py`. Senza quel file il testo passa invariato.

## Room tone

    ./audiobook roomtone status
    ./audiobook roomtone -58
    ./audiobook roomtone off

Qualsiasi livello fra -90 e -30 dBFS. Default testato: **-58 dBFS**.

Il room tone evita il passaggio percepibile tra il noise floor della voce Qwen e il
silenzio digitale assoluto inserito durante le pause. Dipende da una patch applicata
a Pandrator (`patches/pandrator-roomtone.patch`): `./audiobook doctor` verifica che
sia ancora al suo posto.

Il livello va cambiato **prima** di `./audiobook start`: la config si legge al boot.

## Qwen

Configurazione testata:

- Qwen/Qwen3-TTS-12Hz-1.7B-Base
- Apple MPS
- float16
- SDPA
- Italian
- ICL voice cloning
- x_vector_only_mode = False

Voce di riferimento, in `config/voice.json`:

    {
      "reference_dir": "qwen/reference-bank/harry",
      "reference_audio": "reference_it_v2.wav",
      "reference_text": "reference_it_v2.txt"
    }

Cambiare voce = cambiare quel file e fare `./audiobook restart`. La clip e la sua
trascrizione devono corrispondere parola per parola: è così che funziona il cloning ICL.

Per costruirne una nuova:

    ./audiobook transcribe qwen/reference-bank/<nome>/reference_source.wav \
                           qwen/reference-bank/<nome>/reference_source_transcript_plain.txt
    ./audiobook reference qwen/reference-bank/<nome>

L'adapter locale espone Qwen a Pandrator sulla porta:

    http://127.0.0.1:8042

## Pandrator

Web UI:

    http://127.0.0.1:8097

Serve un token API in `.secrets/pandrator-token` per gli stadi audio.

Gli stadi audio della pipeline usano la sessione Pandrator:

    clean_source → prepare_text → generate_audio → export

`prepare-audio` la crea con `max_sentence_length=600`, scelto con
`./audiobook chunking-ab`: blocchi lunghi danno a Qwen abbastanza contesto per una
prosodia narrativa naturale. `generate` rifiuta una sessione preparata con un altro
valore.

## Output

    M4B
    AAC 192k
    lingua it

M4B conserva copertina, titolo/autore e metadata audiobook. La copertina si mette in
`assets/cover.jpg` (JPEG, PNG o WebP); `export` la carica e la applica, o procede
senza se non c'è.

I **capitoli** si dichiarano in `book.json` e si scrivono dopo l'export:

    ./audiobook chapters nome-libro

Pandrator da solo non li produce — li ricava da segmenti marcati come titoli, e un
testo estratto da PDF non ne conserva. Vedi
[`docs/features/chapters.md`](docs/features/chapters.md).

## Ripristino

Se una virtualenv si rompe o il progetto viene installato su un nuovo Mac:

    ./setup.sh
    ./audiobook doctor
    ./audiobook start

## Ambienti congelati

Le versioni che hanno funzionato sono archiviate in:

    environments/pandrator-packages.txt
    environments/qwen-packages.txt
    environments/versions.txt

## Cosa non è in git

`books/` (sorgenti protetti da copyright e file intermedi), `.secrets/`, e il materiale
grezzo delle voci di riferimento. La clip di riferimento in uso sì: un clone fresco
parte senza doverla ricostruire.

## Nota

Su questo Mac viene usato Amphetamine per impedire lo sleep durante generazioni
lunghe. Non è necessario usare caffeinate.
