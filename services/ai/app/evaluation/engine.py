"""
Evaluation Engine — Scores the interview AFTER it is complete.

Design principle:
  Completely separate from the Interview Engine.
  Each dimension is scored independently.
  Final score is deterministic (temperature=0).
  Every result is tagged with rubric_version + model_id.
"""
from dataclasses import dataclass
from typing import Optional
import structlog

from app.llm.bedrock_client import BedrockClient
from app.evaluation.rubric import CURRENT_RUBRIC

logger = structlog.get_logger()


@dataclass
class EvaluationInput:
    session_id: str
    job_title: str
    jd_text: str
    qa_pairs: list[dict]          # [{question, answer, answer_type}]
    transcript: Optional[str]     # full STT transcript
    video_signals: Optional[dict] # from worker


@dataclass
class DimensionScore:
    dimension: str
    score: float          # 0–100
    feedback: str
    examples: list[str]   # specific quotes from student


@dataclass
class EvaluationResult:
    session_id: str
    rubric_version: str
    model_used: str
    dimension_scores: list[DimensionScore]
    overall_score: float
    readiness_level: str
    strengths: list[str]
    weaknesses: list[str]
    improvement_plan: list[dict]


class EvaluationEngine:
    """
    Runs each dimension evaluator independently.
    Aggregates into a final weighted score.
    Completely deterministic (temperature=0 on all scoring calls).
    """

    def __init__(self):
        self.llm = BedrockClient()
        self.rubric = CURRENT_RUBRIC

    async def evaluate(self, inp: EvaluationInput) -> EvaluationResult:
        log = logger.bind(session=inp.session_id)
        log.info("Starting evaluation", rubric=self.rubric["version"])

        # Run each evaluator independently
        technical     = await self._score_technical(inp)
        communication = await self._score_communication(inp)
        relevance     = await self._score_relevance(inp)
        structure     = await self._score_structure(inp)
        presentation  = await self._score_presentation(inp)

        dimensions = [technical, communication, relevance, structure, presentation]

        # Weighted final score
        weights = self.rubric["weights"]
        overall = (
            technical.score     * weights["technical_accuracy"] +
            communication.score * weights["communication"] +
            relevance.score     * weights["answer_relevance"] +
            structure.score     * weights["answer_structure"] +
            presentation.score  * weights["presentation"]
        )

        readiness = self._readiness_level(overall)
        strengths, weaknesses = self._extract_strengths_weaknesses(dimensions)
        plan = await self._generate_improvement_plan(inp, weaknesses)

        log.info("Evaluation complete", overall=overall, readiness=readiness)

        return EvaluationResult(
            session_id=inp.session_id,
            rubric_version=self.rubric["version"],
            model_used=self.rubric["model_used"],
            dimension_scores=dimensions,
            overall_score=round(overall, 2),
            readiness_level=readiness,
            strengths=strengths,
            weaknesses=weaknesses,
            improvement_plan=plan,
        )

    # ─── Individual Evaluators ────────────────────────────────

    async def _score_technical(self, inp: EvaluationInput) -> DimensionScore:
        """Evaluate technical accuracy of answers against JD requirements."""
        transcript_text = self._format_qa(inp.qa_pairs)
        prompt = f"""You are a senior {inp.job_title} evaluating a job interview.

Job Description:
{inp.jd_text[:1000]}

Interview Q&A:
{transcript_text}

Score the candidate's TECHNICAL ACCURACY on a scale of 0-100.
Criteria:
- Correctness of technical concepts
- Depth of knowledge relative to difficulty
- Use of relevant examples
- Awareness of trade-offs

Respond in JSON:
{{
  "score": <number 0-100>,
  "feedback": "<2-3 sentence explanation>",
  "examples": ["<quote from student that supports your score>", ...]
}}"""

        return await self._call_evaluator(prompt, "technical_accuracy")

    async def _score_communication(self, inp: EvaluationInput) -> DimensionScore:
        """Evaluate clarity, articulation, and conciseness."""
        prompt = f"""Evaluate the communication quality of this interview transcript.

Transcript:
{inp.transcript or self._format_qa(inp.qa_pairs)}

Score COMMUNICATION (0-100) based on:
- Clarity of expression
- Appropriate vocabulary
- Conciseness vs. rambling
- Logical sentence structure

Respond in JSON:
{{
  "score": <number 0-100>,
  "feedback": "<2-3 sentences>",
  "examples": ["<quote>"]
}}"""
        return await self._call_evaluator(prompt, "communication")

    async def _score_relevance(self, inp: EvaluationInput) -> DimensionScore:
        """Evaluate whether answers actually address the questions."""
        prompt = f"""Evaluate answer relevance for this interview.

Q&A:
{self._format_qa(inp.qa_pairs)}

Score ANSWER RELEVANCE (0-100):
- Did the student answer what was actually asked?
- Did they stay on topic?
- Were examples relevant?

Respond in JSON:
{{
  "score": <number 0-100>,
  "feedback": "<2-3 sentences>",
  "examples": ["<quote>"]
}}"""
        return await self._call_evaluator(prompt, "answer_relevance")

    async def _score_structure(self, inp: EvaluationInput) -> DimensionScore:
        """Evaluate answer structure — intro/body/conclusion, STAR method use."""
        prompt = f"""Evaluate the structure of answers in this interview.

Q&A:
{self._format_qa(inp.qa_pairs)}

Score ANSWER STRUCTURE (0-100):
- Did answers have clear structure (intro, body, conclusion)?
- Was STAR method used where appropriate?
- Were key points summarized?

Respond in JSON:
{{
  "score": <number 0-100>,
  "feedback": "<2-3 sentences>",
  "examples": ["<quote>"]
}}"""
        return await self._call_evaluator(prompt, "answer_structure")

    async def _score_presentation(self, inp: EvaluationInput) -> DimensionScore:
        """Evaluate observable presentation signals — no emotional inferences."""
        if not inp.video_signals:
            return DimensionScore(
                dimension="presentation",
                score=50.0,
                feedback="No video data available — presentation score defaulted.",
                examples=[],
            )

        s = inp.video_signals
        observations = []
        if s.get("gaze_away_pct", 0) > 30:
            observations.append(f"Frequent gaze away from camera ({s['gaze_away_pct']:.0f}% of time).")
        if s.get("filler_word_count", 0) > 10:
            observations.append(f"High filler word usage ({s['filler_word_count']} instances).")
        if s.get("long_pause_count", 0) > 5:
            observations.append(f"{s['long_pause_count']} long pauses (>3s) observed.")
        if s.get("face_detected_pct", 100) < 70:
            observations.append(f"Face not clearly visible in {100 - s['face_detected_pct']:.0f}% of video.")

        # Score based on signal severity
        deductions = len(observations) * 10
        score = max(0.0, 100.0 - deductions)

        feedback = "Observable signals: " + " ".join(observations) if observations else \
                   "No significant presentation issues detected."

        return DimensionScore(
            dimension="presentation",
            score=score,
            feedback=feedback,
            examples=observations,
        )

    # ─── Helpers ─────────────────────────────────────────────

    async def _call_evaluator(self, prompt: str, dimension: str) -> DimensionScore:
        """Call LLM with temperature=0 for deterministic scoring."""
        import json
        response = await self.llm.generate(prompt, temperature=0, max_tokens=500)
        try:
            data = json.loads(response)
            return DimensionScore(
                dimension=dimension,
                score=float(data["score"]),
                feedback=data.get("feedback", ""),
                examples=data.get("examples", []),
            )
        except Exception:
            logger.warning("Failed to parse evaluator response", dimension=dimension)
            return DimensionScore(dimension=dimension, score=50.0, feedback="Parse error.", examples=[])

    def _format_qa(self, qa_pairs: list[dict]) -> str:
        lines = []
        for i, qa in enumerate(qa_pairs, 1):
            lines.append(f"Q{i}: {qa['question'].get('text', '')}")
            lines.append(f"A{i}: {qa.get('answer_text', '[no answer]')}")
        return "\n".join(lines)

    def _readiness_level(self, score: float) -> str:
        if score >= 80: return "strong"
        if score >= 65: return "ready"
        if score >= 45: return "developing"
        return "not_ready"

    def _extract_strengths_weaknesses(self, dimensions: list[DimensionScore]):
        sorted_dims = sorted(dimensions, key=lambda d: d.score, reverse=True)
        strengths = [f"{d.dimension}: {d.feedback}" for d in sorted_dims if d.score >= 70][:3]
        weaknesses = [f"{d.dimension}: {d.feedback}" for d in sorted_dims if d.score < 60][:3]
        return strengths, weaknesses

    async def _generate_improvement_plan(self, inp: EvaluationInput, weaknesses: list[str]) -> list[dict]:
        """Generate a structured, actionable improvement plan."""
        if not weaknesses:
            return [{"priority": 1, "area": "Maintain performance", "action": "Practice advanced system design questions."}]

        prompt = f"""A {inp.job_title} candidate has these weaknesses after an interview:
{chr(10).join(f'- {w}' for w in weaknesses)}

Create a concrete 3-step improvement plan. Each step should have:
- area: which skill to improve
- action: specific, actionable task (e.g. "Practice 5 LeetCode medium problems per week")
- timeline: realistic timeframe

Respond in JSON array:
[{{"priority": 1, "area": "...", "action": "...", "timeline": "..."}}]"""

        import json
        response = await self.llm.generate(prompt, temperature=0.3, max_tokens=400)
        try:
            return json.loads(response)
        except Exception:
            return [{"priority": 1, "area": "General", "action": "Review weak areas and practice.", "timeline": "2 weeks"}]
