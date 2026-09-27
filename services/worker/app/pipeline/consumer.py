"""
SQS Worker Consumer — Processes video jobs asynchronously.
Triggered by SQS messages posted after S3 video upload.

Pipeline per job:
  1. Download video from S3
  2. Extract audio (FFmpeg)
  3. Speech-to-text (Whisper)
  4. Extract observable video signals (OpenCV + MediaPipe)
  5. Send data to Evaluation Engine
  6. Store report in PostgreSQL
  7. Notify via WebSocket / update session status
"""
import json
import time
import boto3
import structlog

from app.audio.extractor import AudioExtractor
from app.audio.stt import SpeechToText
from app.video.signals import VideoSignalExtractor
from app.pipeline.report_writer import ReportWriter
from app.config import settings

logger = structlog.get_logger()

sqs = boto3.client("sqs", region_name=settings.AWS_REGION)
s3  = boto3.client("s3",  region_name=settings.AWS_REGION)


def run_consumer():
    """
    Long-running SQS polling loop.
    Processes one message at a time — keeps it simple for MVP.
    """
    logger.info("Worker consumer starting", queue=settings.SQS_QUEUE_URL)

    while True:
        try:
            response = sqs.receive_message(
                QueueUrl=settings.SQS_QUEUE_URL,
                MaxNumberOfMessages=1,
                WaitTimeSeconds=20,       # long polling — reduces cost
                VisibilityTimeout=300,    # 5 min processing window
            )

            messages = response.get("Messages", [])
            if not messages:
                continue

            for message in messages:
                receipt_handle = message["ReceiptHandle"]
                body = json.loads(message["Body"])

                try:
                    process_job(body)
                    # Delete from queue on success
                    sqs.delete_message(
                        QueueUrl=settings.SQS_QUEUE_URL,
                        ReceiptHandle=receipt_handle,
                    )
                except Exception as e:
                    logger.error("Job failed — leaving in queue for retry", error=str(e), body=body)
                    # SQS will redeliver after VisibilityTimeout
                    # After maxReceiveCount it goes to DLQ

        except KeyboardInterrupt:
            logger.info("Worker shutting down")
            break
        except Exception as e:
            logger.error("Consumer loop error", error=str(e))
            time.sleep(5)


def process_job(body: dict):
    """Process a single video analysis job."""
    session_id = body["sessionId"]
    user_id    = body["userId"]
    log = logger.bind(session=session_id)

    log.info("Processing video job")

    # 1. Download video from S3
    video_path = _download_video(session_id)
    log.info("Video downloaded", path=video_path)

    # 2. Extract audio
    audio_extractor = AudioExtractor()
    audio_path = audio_extractor.extract(video_path)

    # 3. Speech-to-text
    stt = SpeechToText()
    transcript = stt.transcribe(audio_path)
    log.info("Transcription complete", word_count=len(transcript.get("words", [])))

    # 4. Observable video signals
    signal_extractor = VideoSignalExtractor()
    signals = signal_extractor.extract(video_path, transcript)
    log.info("Signals extracted", filler_words=signals.get("filler_word_count"))

    # 5. Write report
    writer = ReportWriter()
    writer.write(
        session_id=session_id,
        transcript=transcript,
        signals=signals,
    )
    log.info("Report written — job complete")


def _download_video(session_id: str) -> str:
    """Download video from S3 to local /tmp."""
    from app.db import get_session_video_key
    import tempfile, os

    s3_key = get_session_video_key(session_id)
    local_path = os.path.join(tempfile.gettempdir(), f"{session_id}.webm")

    s3.download_file(settings.S3_BUCKET_NAME, s3_key, local_path)
    return local_path


if __name__ == "__main__":
    run_consumer()
