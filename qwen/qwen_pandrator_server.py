import io
import json
import os
import threading
import time
from contextlib import asynccontextmanager
from pathlib import Path

import soundfile as sf
import torch
from fastapi import FastAPI, HTTPException, Response
from pydantic import BaseModel
from qwen_tts import Qwen3TTSModel


BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

HF_MODEL = "Qwen/Qwen3-TTS-12Hz-1.7B-Base"

# La voce di riferimento e' configurazione, non codice: cambiarla non deve
# voler dire modificare questo file. Override con AUDIOBOOK_VOICE_CONFIG.
VOICE_CONFIG_PATH = Path(
    os.environ.get(
        "AUDIOBOOK_VOICE_CONFIG",
        ROOT_DIR / "config" / "voice.json",
    )
)


def load_voice_config():
    defaults = {
        "voice_id": "italiano",
        "language": "Italian",
        "reference_dir": "qwen/reference-bank/harry",
        "reference_audio": "reference_it_v2.wav",
        "reference_text": "reference_it_v2.txt",
    }

    if not VOICE_CONFIG_PATH.is_file():
        raise RuntimeError(
            f"Voice config not found: {VOICE_CONFIG_PATH}"
        )

    config = defaults | json.loads(
        VOICE_CONFIG_PATH.read_text(encoding="utf-8")
    )

    reference_dir = Path(config["reference_dir"])

    if not reference_dir.is_absolute():
        reference_dir = ROOT_DIR / reference_dir

    config["reference_dir"] = reference_dir
    config["audio_path"] = reference_dir / config["reference_audio"]
    config["text_path"] = reference_dir / config["reference_text"]

    return config


VOICE = load_voice_config()

VOICE_ID = VOICE["voice_id"]
LANGUAGE = VOICE["language"]

REF_DIR = VOICE["reference_dir"]
REF_AUDIO = VOICE["audio_path"]
REF_TEXT_FILE = VOICE["text_path"]

DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
DTYPE = torch.float16 if DEVICE == "mps" else torch.float32

model = None
voice_prompt = None
generation_lock = threading.Lock()


class SpeechRequest(BaseModel):
    model: str = "Voice Cloning"
    input: str
    voice: str = VOICE_ID
    speed: float = 1.0
    response_format: str = "wav"
    language: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global model, voice_prompt

    if not REF_AUDIO.exists():
        raise RuntimeError(f"Reference audio not found: {REF_AUDIO}")

    if not REF_TEXT_FILE.exists():
        raise RuntimeError(f"Reference text not found: {REF_TEXT_FILE}")

    ref_text = REF_TEXT_FILE.read_text(
        encoding="utf-8"
    ).strip()

    if not ref_text:
        raise RuntimeError("Reference transcript is empty")

    print()
    print("Loading official Qwen3-TTS...")
    print(f"Device: {DEVICE}")
    print(f"Dtype: {DTYPE}")
    print("Attention: SDPA")

    model = Qwen3TTSModel.from_pretrained(
        HF_MODEL,
        device_map=DEVICE,
        dtype=DTYPE,
        attn_implementation="sdpa",
    )

    print("Preparing Italian voice clone prompt...")

    voice_prompt = model.create_voice_clone_prompt(
        ref_audio=str(REF_AUDIO),
        ref_text=ref_text,
        x_vector_only_mode=False,
    )

    print()
    print("✓ Qwen3-TTS ready")
    print("✓ Italian ICL voice ready")
    print("✓ Pandrator endpoint: http://127.0.0.1:8042")
    print()

    yield


app = FastAPI(
    title="Official Qwen3-TTS Pandrator Adapter",
    lifespan=lifespan,
)


@app.get("/")
@app.get("/health")
def health():
    ready = model is not None and voice_prompt is not None

    return {
        "status": "ok" if ready else "loading",
        "kobold_online": ready,
        "child_online": ready,
        "backend": DEVICE,
        "engine": "official-qwen3-tts",
        "model": HF_MODEL,
        "language": LANGUAGE,
        "voice": VOICE_ID,
    }


@app.get("/readyz")
def ready():
    if model is None or voice_prompt is None:
        raise HTTPException(status_code=503, detail="Qwen3-TTS is loading")

    return {
        "status": "ready",
        "active_model": "Voice Cloning",
    }


@app.get("/v1/models")
@app.get("/v1/audio/models")
def models():
    return {
        "data": [
            {
                "id": "Voice Cloning",
                "object": "model",
                "owned_by": "Qwen",
                "description": "Official Qwen3-TTS 1.7B Base - Italian ICL voice cloning",
            }
        ]
    }


@app.get("/v1/audio/voices")
@app.get("/v1/voices")
@app.get("/v1/files")
def voices():
    return {
        "data": [
            {
                "id": VOICE_ID,
                "voice_id": VOICE_ID,
                "name": "Italiano - official Qwen3-TTS ICL",
                "type": "cloned",
                "model": "Voice Cloning",
            }
        ]
    }


@app.get("/v1/capabilities")
@app.get("/capabilities")
def capabilities():
    # Start conservatively: sequential synthesis.
    # We can add native Qwen batching after the audiobook pipeline is verified.
    return {
        "object": "capabilities",
        "batch_synthesis": {
            "supported": False,
            "streaming": False,
            "default_batch_size": 1,
            "max_batch_size": 1,
            "parallelism": 1,
        },
    }


@app.post("/v1/audio/speech")
@app.post("/audio/speech")
def speech(request: SpeechRequest):
    if model is None or voice_prompt is None:
        raise HTTPException(status_code=503, detail="Qwen3-TTS is not ready")

    if not request.input.strip():
        raise HTTPException(status_code=422, detail="Input text is empty")

    if request.model.lower() not in {
        "voice cloning",
        "qwen3-tts",
        "qwen3-tts-base",
    }:
        raise HTTPException(
            status_code=422,
            detail="This server only supports the Voice Cloning model",
        )

    # Pandrator historically seeds 'kobo' as a Qwen cloning voice.
    # Accept it as an alias, but our catalogue exposes 'italiano'.
    if request.voice.lower() not in {
        VOICE_ID.lower(),
        "kobo",
        "default",
    }:
        raise HTTPException(
            status_code=422,
            detail=f"Unknown voice '{request.voice}'. Use '{VOICE_ID}'.",
        )

    if abs(request.speed - 1.0) > 0.001:
        raise HTTPException(
            status_code=422,
            detail="Keep Pandrator speech speed at 1.0 for this adapter.",
        )

    started = time.time()

    with generation_lock:
        with torch.inference_mode():
            wavs, sample_rate = model.generate_voice_clone(
                text=request.input,
                language=LANGUAGE,
                voice_clone_prompt=voice_prompt,
            )

    elapsed = time.time() - started

    output = io.BytesIO()

    sf.write(
        output,
        wavs[0],
        sample_rate,
        format="WAV",
        subtype="PCM_16",
    )

    audio = output.getvalue()

    print(
        f"TTS: {len(request.input)} chars → "
        f"{len(audio) / 1024:.0f} KiB in {elapsed:.1f}s"
    )

    return Response(
        content=audio,
        media_type="audio/wav",
        headers={
            "X-Qwen-Generation-Seconds": f"{elapsed:.2f}",
        },
    )
