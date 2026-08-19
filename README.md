# Local Audiobook

Pipeline locale per trasformare libri in audiolibri italiani usando:

- Pandrator
- Qwen3-TTS official
- voice cloning locale
- Apple Metal / MPS
- room tone naturale
- M4B come output finale

## Percorsi

Repository:

    ~/Code/solo/projects/local-audiobook

Pandrator:

    ~/src/Pandrator

Qwen:

    ~/src/qwen3-tts-official

## Uso quotidiano

Controllare che tutto sia a posto:

    ./audiobook doctor

Avviare tutto:

    ./audiobook start

Aprire Pandrator:

    ./audiobook open

Stato:

    ./audiobook status

Log:

    ./audiobook logs

Spegnere:

    ./audiobook stop

## Room tone

Configurazione consigliata:

    ./audiobook roomtone -58

Alternative:

    ./audiobook roomtone -62
    ./audiobook roomtone -54
    ./audiobook roomtone off

Il room tone evita il passaggio percepibile tra il noise floor della voce
Qwen e il silenzio digitale assoluto inserito durante le pause.

Default usato e testato:

    -58 dBFS

## Qwen

Configurazione testata:

- Qwen/Qwen3-TTS-12Hz-1.7B-Base
- Apple MPS
- float16
- SDPA
- Italian
- ICL voice cloning
- x_vector_only_mode = False

Voice reference:

    qwen/reference_it.wav

L'adapter locale espone Qwen a Pandrator sulla porta:

    http://127.0.0.1:8042

## Pandrator

Web UI:

    http://127.0.0.1:8097

La pipeline dell'audiolibro usa:

    Clean source
      → Segment narration
      → Generate audio
      → Assemble output
      → Export M4B

## Output

Formato consigliato:

    M4B
    AAC 192k
    lingua it

M4B permette di conservare:

- copertina
- titolo/autore
- capitoli
- metadata audiobook

## Ripristino

Se una virtualenv si rompe o il progetto viene installato su un nuovo Mac:

    ./setup.sh

Poi:

    ./audiobook doctor
    ./audiobook start

## Ambienti congelati

Le versioni che hanno funzionato sono archiviate in:

    environments/pandrator-packages.txt
    environments/qwen-packages.txt
    environments/versions.txt

## Nota

Su questo Mac viene usato Amphetamine per impedire lo sleep durante
generazioni lunghe. Non è necessario usare caffeinate.
