"""whisper-server: OpenAI-compatible /v1/audio/transcriptions on Apple Silicon.

Run:
    .venv/bin/python server.py

Env vars (all optional):
    WHISPER_MODEL         default Systran/faster-distil-whisper-large-v3
    WHISPER_COMPUTE_TYPE  default float32   (int8/float16/float32)
    WHISPER_VAD           default 1         (0 to disable Silero VAD)
    WHISPER_BEAM_SIZE     default 5
    WHISPER_HOST          default 0.0.0.0
    WHISPER_PORT          default 8170
"""

import logging
import os
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse, PlainTextResponse
from faster_whisper import WhisperModel
from faster_whisper.utils import get_writer

LOG = logging.getLogger("whisper-server")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)

MODEL_NAME = os.getenv("WHISPER_MODEL", "Systran/faster-distil-whisper-large-v3")
COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "float32")
VAD_ENABLED = os.getenv("WHISPER_VAD", "1") not in ("0", "false", "False")
BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
HOST = os.getenv("WHISPER_HOST", "0.0.0.0")
PORT = int(os.getenv("WHISPER_PORT", "8170"))

ALLOWED_SUFFIXES = {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".opus", ".webm", ".mp4"}
RESPONSE_FORMATS = {"json", "text", "srt", "vtt"}

LOG.info(
    "loading model=%s compute_type=%s vad=%s beam=%d",
    MODEL_NAME, COMPUTE_TYPE, VAD_ENABLED, BEAM_SIZE,
)
MODEL = WhisperModel(MODEL_NAME, device="cpu", compute_type=COMPUTE_TYPE)
LOG.info("model loaded")

app = FastAPI(title="whisper-server", version="0.1.0")


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


@app.post("/v1/audio/transcriptions")
async def transcriptions(
    file: UploadFile = File(...),
    model: str = Form(default=MODEL_NAME),
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

    # fastapi 接收到的 UploadFile 已经全部在内存里（无 spool 到磁盘）
    raw = await file.read()
    if not raw:
        return _error("empty audio upload", status=400, err_type="invalid_request_error")

    tmp_path = ""
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, dir="/tmp", delete=False) as tf:
            tf.write(raw)
            tmp_path = tf.name

        segments, info = MODEL.transcribe(
            tmp_path,
            beam_size=BEAM_SIZE,
            language=language,
            vad_filter=VAD_ENABLED,
            vad_parameters={"min_silence_duration_ms": 500} if VAD_ENABLED else None,
        )
        seg_list = list(segments)
        full_text = "".join(s.text for s in seg_list).strip()

        if response_format == "json":
            return JSONResponse({
                "text": full_text,
                "language": info.language,
                "duration": info.duration,
                "segments": [
                    {
                        "id": s.id,
                        "start": s.start,
                        "end": s.end,
                        "text": s.text,
                        "avg_logprob": getattr(s, "avg_logprob", None),
                        "compression_ratio": getattr(s, "compression_ratio", None),
                        "no_speech_prob": getattr(s, "no_speech_prob", None),
                    }
                    for s in seg_list
                ],
            })

        if response_format == "text":
            return PlainTextResponse(full_text)

        # srt / vtt: use faster-whisper's writer to tempfile then read back
        out_dir = tempfile.mkdtemp(prefix="whisper-out-")
        try:
            writer = get_writer(response_format, out_dir)
            writer(seg_list, {"language": info.language}, AudioStub())
            out_file = next(Path(out_dir).iterdir())
            return PlainTextResponse(out_file.read_text(encoding="utf-8"), media_type="text/plain; charset=utf-8")
        finally:
            for p in Path(out_dir).iterdir():
                try:
                    p.unlink()
                except OSError:
                    pass
            try:
                Path(out_dir).rmdir()
            except OSError:
                pass

    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001
        LOG.exception("transcribe failed")
        return _error(f"transcribe failed: {exc}", status=500)
    finally:
        if tmp_path:
            try:
                Path(tmp_path).unlink()
            except OSError:
                pass


class AudioStub:
    """faster-whisper writer 期望一个 .stem 属性。"""
    stem = "audio"


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL_NAME, "compute_type": COMPUTE_TYPE, "vad": VAD_ENABLED}


if __name__ == "__main__":
    import uvicorn
    LOG.info("serving on %s:%d", HOST, PORT)
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")