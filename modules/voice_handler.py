"""
voice_handler.py
Receives a WAV/WebM audio blob from the browser and transcribes it
using a local Whisper model (openai-whisper).
"""

import os
import tempfile


class VoiceHandler:
    def __init__(self, config: dict):
        self.config    = config
        self._model    = None
        self.model_size = config.get("whisper", {}).get("model", "base")

    def _load_model(self):
        if self._model is None:
            import whisper  # loaded lazily to avoid startup delay
            print(f"[Whisper] Loading model '{self.model_size}' ...")
            self._model = whisper.load_model(self.model_size)
            print("[Whisper] Model ready.")
        return self._model

    def transcribe_bytes(self, audio_bytes: bytes) -> str:
        """Write bytes to a temp file, run Whisper, return transcript."""
        suffix = ".wav"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(audio_bytes)
            tmp = f.name
        try:
            model  = self._load_model()
            result = model.transcribe(tmp, language=None)   # auto-detect language
            return result["text"].strip()
        except Exception as exc:
            return f"[Transcription error: {exc}]"
        finally:
            os.unlink(tmp)
