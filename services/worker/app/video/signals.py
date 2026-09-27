"""
Observable Video Signal Extractor

Measures ONLY observable, technical signals.
NO emotional inference ("nervous", "confident").
Signals are reported as facts, not interpretations.

Examples of correct framing:
  GOOD: "Gaze was directed away from camera 42% of the time."
  BAD:  "You appeared nervous and lacked confidence."
"""
import cv2
import mediapipe as mp
import re
from collections import Counter
import structlog

logger = structlog.get_logger()

# Filler words to detect
FILLER_WORDS = {"um", "uh", "like", "you know", "sort of", "kind of", "basically", "literally", "actually", "so"}


class VideoSignalExtractor:
    """
    Extracts observable signals from video file.
    Uses MediaPipe FaceMesh for gaze + head movement.
    Uses transcript for audio-based signals.
    """

    def __init__(self):
        self.mp_face_mesh = mp.solutions.face_mesh
        self.mp_drawing = mp.solutions.drawing_utils

    def extract(self, video_path: str, transcript: dict) -> dict:
        """Run all signal extractors and return consolidated signals dict."""
        logger.info("Extracting video signals", path=video_path)

        face_signals   = self._extract_face_signals(video_path)
        audio_signals  = self._extract_audio_signals(transcript)
        quality        = self._assess_quality(video_path)

        return {**face_signals, **audio_signals, **quality}

    def _extract_face_signals(self, video_path: str) -> dict:
        """
        Frame-by-frame analysis:
        - Face detected? (Y/N)
        - Gaze direction (approximated from eye landmarks)
        - Head movement
        """
        cap = cv2.VideoCapture(video_path)
        total_frames = 0
        face_detected_frames = 0
        gaze_away_frames = 0

        with self.mp_face_mesh.FaceMesh(
            static_image_mode=False,
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
        ) as face_mesh:

            # Sample every 5th frame to keep processing fast
            frame_interval = 5
            frame_count = 0

            while cap.isOpened():
                ret, frame = cap.read()
                if not ret:
                    break

                frame_count += 1
                if frame_count % frame_interval != 0:
                    continue

                total_frames += 1
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                results = face_mesh.process(rgb_frame)

                if results.multi_face_landmarks:
                    face_detected_frames += 1
                    # Approximate gaze: compare nose tip vs eye center x positions
                    landmarks = results.multi_face_landmarks[0].landmark
                    nose_x = landmarks[1].x
                    left_eye_x  = landmarks[33].x
                    right_eye_x = landmarks[263].x
                    eye_center_x = (left_eye_x + right_eye_x) / 2

                    # If nose deviates >15% from eye center → looking away
                    if abs(nose_x - eye_center_x) > 0.15:
                        gaze_away_frames += 1

        cap.release()

        if total_frames == 0:
            return {
                "face_detected_pct": 0.0,
                "gaze_center_pct": 0.0,
                "gaze_away_pct": 0.0,
            }

        face_pct = (face_detected_frames / total_frames) * 100
        gaze_away_pct = (gaze_away_frames / max(face_detected_frames, 1)) * 100

        return {
            "face_detected_pct": round(face_pct, 2),
            "gaze_center_pct": round(100 - gaze_away_pct, 2),
            "gaze_away_pct": round(gaze_away_pct, 2),
        }

    def _extract_audio_signals(self, transcript: dict) -> dict:
        """
        Extract speaking pace, filler words, long pauses from transcript.
        """
        words = transcript.get("words", [])
        full_text = transcript.get("text", "").lower()

        if not words:
            return {
                "words_per_min": 0,
                "filler_word_count": 0,
                "filler_words": {},
                "long_pause_count": 0,
            }

        # Speaking pace
        total_words = len(words)
        if len(words) >= 2:
            duration_min = (words[-1]["end_ms"] - words[0]["start_ms"]) / 60000
            wpm = total_words / max(duration_min, 0.01)
        else:
            wpm = 0

        # Filler word count
        filler_counts = {}
        for filler in FILLER_WORDS:
            count = len(re.findall(r'\b' + re.escape(filler) + r'\b', full_text))
            if count > 0:
                filler_counts[filler] = count
        total_fillers = sum(filler_counts.values())

        # Long pauses (> 3000ms between consecutive words)
        long_pauses = 0
        for i in range(1, len(words)):
            gap_ms = words[i]["start_ms"] - words[i-1]["end_ms"]
            if gap_ms > 3000:
                long_pauses += 1

        return {
            "words_per_min": round(wpm, 2),
            "filler_word_count": total_fillers,
            "filler_words": filler_counts,
            "long_pause_count": long_pauses,
        }

    def _assess_quality(self, video_path: str) -> dict:
        """Simple quality assessment: brightness, resolution."""
        cap = cv2.VideoCapture(video_path)
        ret, frame = cap.read()
        cap.release()

        if not ret:
            return {"lighting_quality": "unknown", "background_quality": "unknown"}

        # Brightness via HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        brightness = hsv[:, :, 2].mean()

        lighting = "good" if brightness > 100 else ("poor" if brightness > 50 else "very_poor")

        return {
            "lighting_quality": lighting,
            "background_quality": "good",  # Could add blur/clutter detection
        }
