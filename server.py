"""whisper-server: OpenAI-compatible /v1/audio/transcriptions on Apple Silicon.

Backend: pywhispercpp (Python bindings for whisper.cpp), reusing ggml model
already on disk at ~/.cache/whisper-cpp/ggml-large-v3.bin.

Run:
    .venv/bin/python server.py

Env vars (all optional):
    WHISPER_MODEL         default /Users/bobo/.cache/whisper-cpp/ggml-large-v3.bin
    WHISPER_N_THREADS     default 0  (0 = auto, min(4, os.cpu_count()))
    WHISPER_VAD           default 1  (whisper.cpp built-in VAD; 0 to disable)
    WHISPER_HOST          default 0.0.0.0
    WHISPER_PORT          default 8170
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from pywhispercpp.model import Model
from pywhispercpp.utils import output_srt, output_vtt

LOG = logging.getLogger("whisper-server")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

DEFAULT_MODEL_PATH = "/Users/bobo/.cache/whisper-cpp/ggml-large-v3.bin"
MODEL_PATH = os.getenv("WHISPER_MODEL", DEFAULT_MODEL_PATH)
N_THREADS = int(os.getenv("WHISPER_N_THREADS", "0"))
VAD_ENABLED = os.getenv("WHISPER_VAD", "1") not in ("0", "false", "False")
HOST = os.getenv("WHISPER_HOST", "0.0.0.0")
PORT = int(os.getenv("WHISPER_PORT", "8170"))

ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".mp4"}
RESPONSE_FORMATS = {"json", "text", "srt", "vtt"}

LOG.info(
    "loading model=%s n_threads=%d vad=%s",
    MODEL_PATH, N_THREADS, VAD_ENABLED,
)
ASR = Model(
    model=MODEL_PATH,
    n_threads=N_THREADS if N_THREADS > 0 else min(4, os.cpu_count() or 4),
    print_progress=False,
    print_realtime=False,
    print_timestamps=False,
    vad=VAD_ENABLED,
)
LOG.info("model loaded")


def _suffix(filename: str | None) -> str:
    if not filename:
        return ".wav"
    suf = Path(filename).suffix.lower()
    return suf if suf else ".wav"


def _error(message: str, status: int = 500, err_type: str = "internal_error") -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"message": message, "type": err_type, "param": None, "code": None}},
    )


def _segments_to_json(segments, language: str | None):
    return {
        "language": language,
        "text": "".join(s.text for s in segments).strip(),
        "segments": [
            {
                "id": i,
                "start": s.t0 / 100.0,
                "end": s.t1 / 100.0,
                "text": s.text,
                "no_speech_prob": None,
            }
            for i, s in enumerate(segments)
        ],
    }


app = FastAPI(title="whisper-server", version="0.2.0")


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form(default=MODEL_PATH),
    language: str | None = Form(default=None),
    response_format: str = Form(default="json"),
):
    if response_format not in RESPONSE_FORMATS:
        return _error(
            f"response_format must be one of {sorted(RESPONSE_FORMATS)}",
            status=400, err_type="invalid_request_error",
        )

    suffix = _suffix(file.filename)
    if suffix not in ALLOWED_SUFFIXES:
        return _error(
            f"unsupported audio suffix {suffix!r}; allowed: {sorted(ALLOWED_SUFFIXES)}",
            status=400, err_type="invalid_request_error",
        )

    raw = await file.read()
    if not raw:
        return _error("empty audio upload", status=400, err_type="invalid_request_error")

    tmp_path = ""
    out_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, dir="/tmp", delete=False) as tf:
            tf.write(raw)
            tmp_path = tf.name

        # whisper.cpp auto-detects language when language="" / None
        kwargs = {"language": language or ""}
        segments = ASR.transcribe(tmp_path, **kwargs)

        if response_format == "json":
            return JSONResponse(_segments_to_json(segments, language))

        if response_format == "text":
            return PlainTextResponse("".join(s.text for s in segments).strip())

        # srt / vtt via pywhispercpp utils (writes to disk then we read)
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=f".{response_format}", dir="/tmp", delete=False, encoding="utf-8"
        ) as of:
            out_path = of.name
        if response_format == "srt":
            output_srt(segments, out_path)
        else:
            output_vtt(segments, out_path)
        return PlainTextResponse(
            Path(out_path).read_text(encoding="utf-8"),
            media_type="text/plain; charset=utf-8",
        )

    except Exception as exc:  # noqa: BLE001
        LOG.exception("transcribe failed")
        return _error(f"transcribe failed: {exc}", status=500)
    finally:
        for p in (tmp_path, out_path):
            if p:
                try:
                    Path(p).unlink()
                except OSError:
                    pass


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": MODEL_PATH,
        "n_threads": N_THREADS,
        "vad": VAD_ENABLED,
        "backend": "pywhispercpp",
    }


if __name__ == "__main__":
    import uvicorn
    LOG.info("serving on %s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")