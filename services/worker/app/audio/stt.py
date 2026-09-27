"""
Speech-to-Text module.
Primary: OpenAI Whisper (local)
Fallback: AWS Transcribe (for large files / low RAM)
"""
import whisper
import boto3
import time
import structlog

from app.config import settings

logger = structlog.get_logger()


class SpeechToText:
    def __init__(self, prefer_local: bool = True):
        self.prefer_local = prefer_local
        self._whisper_model = None  # lazy load

    def transcribe(self, audio_path: str) -> dict:
        """
        Returns: {
            "text": full transcript string,
            "words": [{"word": str, "start_ms": int, "end_ms": int, "confidence": float}],
            "provider": "whisper" | "aws_transcribe"
        }
        """
        if self.prefer_local:
            try:
                return self._whisper_transcribe(audio_path)
            except Exception as e:
                logger.warning("Whisper failed, falling back to AWS Transcribe", error=str(e))

        return self._aws_transcribe(audio_path)

    def _whisper_transcribe(self, audio_path: str) -> dict:
        """Local Whisper inference — word-level timestamps."""
        if self._whisper_model is None:
            logger.info("Loading Whisper model")
            self._whisper_model = whisper.load_model("base")  # balance of speed/accuracy

        result = self._whisper_model.transcribe(
            audio_path,
            word_timestamps=True,
            language="en",
        )

        words = []
        for segment in result.get("segments", []):
            for w in segment.get("words", []):
                words.append({
                    "word": w["word"].strip(),
                    "start_ms": int(w["start"] * 1000),
                    "end_ms": int(w["end"] * 1000),
                    "confidence": round(w.get("probability", 1.0), 4),
                })

        return {
            "text": result["text"],
            "words": words,
            "provider": "whisper",
        }

    def _aws_transcribe(self, audio_path: str) -> dict:
        """AWS Transcribe — used as fallback for large files or low RAM environments."""
        # Upload to S3 first, then start transcription job
        # Implementation: upload → start job → poll → parse → return
        # Omitted for MVP brevity — placeholder
        raise NotImplementedError("AWS Transcribe fallback — implement when needed")
