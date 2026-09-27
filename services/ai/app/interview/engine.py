"""
Interview Engine — Core interview state machine and LLM orchestration.

Design principle:
  This engine ONLY conducts the interview.
  It does NOT score or evaluate.
  Scoring is handled by the separate EvaluationEngine.
"""
import json
from typing import Optional
from pydantic import BaseModel
import structlog

from app.llm.bedrock_client import BedrockClient
from app.questions.generator import QuestionGenerator

logger = structlog.get_logger()

# Interview state machine
STATES = ["not_started", "in_progress", "completed"]


class InterviewContext(BaseModel):
    session_id: str
    job_title: str
    difficulty: str          # easy | medium | hard
    jd_text: str
    questions: list[dict] = []
    answers: list[dict] = []
    current_q_index: int = 0
    state: str = "not_started"
    total_duration_min: int = 20


class InterviewEngine:
    """
    Manages the interview conversation loop.
    Generates adaptive follow-up questions based on student answers.
    Handles edge cases: silence, "I don't know", off-topic answers.
    """

    def __init__(self):
        self.llm = BedrockClient()
        self.question_gen = QuestionGenerator()

    async def start_interview(self, ctx: InterviewContext) -> dict:
        """Generate initial question set from JD + role + difficulty."""
        logger.info("Starting interview", session=ctx.session_id)

        questions = await self.question_gen.generate(
            job_title=ctx.job_title,
            difficulty=ctx.difficulty,
            jd_text=ctx.jd_text,
            count=12,
        )

        ctx.questions = questions
        ctx.state = "in_progress"

        return {
            "session_id": ctx.session_id,
            "question": questions[0],
            "question_index": 0,
            "total_questions": len(questions),
        }

    async def process_answer(self, ctx: InterviewContext, answer_text: str) -> dict:
        """
        Process student answer and decide next action.
        Returns next question or signals interview complete.
        """
        log = logger.bind(session=ctx.session_id, q_index=ctx.current_q_index)

        # Classify the answer
        answer_type = await self._classify_answer(
            question=ctx.questions[ctx.current_q_index],
            answer=answer_text,
        )
        log.info("Answer classified", type=answer_type)

        # Store answer
        ctx.answers.append({
            "question_index": ctx.current_q_index,
            "answer_text": answer_text,
            "answer_type": answer_type,
        })

        # Handle edge cases
        if answer_type == "dont_know":
            # Offer a hint or move on gracefully
            hint = await self._generate_hint(ctx.questions[ctx.current_q_index])
            return {
                "action": "hint",
                "message": hint,
                "can_skip": True,
            }

        if answer_type == "silent":
            return {
                "action": "prompt",
                "message": "Take your time — share whatever comes to mind, even partially.",
                "can_skip": True,
            }

        if answer_type == "off_topic":
            return {
                "action": "redirect",
                "message": "Let's refocus on the question. " + ctx.questions[ctx.current_q_index]["text"],
                "redirect": True,
            }

        # Move to next question
        ctx.current_q_index += 1
        if ctx.current_q_index >= len(ctx.questions):
            ctx.state = "completed"
            return {"action": "complete", "message": "Interview complete. Generating your report..."}

        # Adaptive: optionally generate a follow-up instead of next preset question
        next_question = ctx.questions[ctx.current_q_index]

        return {
            "action": "next_question",
            "question": next_question,
            "question_index": ctx.current_q_index,
            "total_questions": len(ctx.questions),
        }

    async def _classify_answer(self, question: dict, answer: str) -> str:
        """
        Classify the type of student answer.
        Returns: 'good' | 'partial' | 'dont_know' | 'silent' | 'off_topic'
        """
        if not answer or len(answer.strip()) < 5:
            return "silent"

        dont_know_phrases = ["i don't know", "i dont know", "no idea", "not sure", "i have no idea"]
        if any(p in answer.lower() for p in dont_know_phrases):
            return "dont_know"

        # Use LLM to detect off-topic (cheap call, small prompt)
        prompt = f"""Question: {question['text']}
Answer: {answer[:500]}

Is this answer on-topic to the question? Respond with only: on_topic or off_topic"""

        response = await self.llm.generate(prompt, max_tokens=10, temperature=0)
        return "off_topic" if "off_topic" in response.lower() else "good"

    async def _generate_hint(self, question: dict) -> str:
        """Generate a gentle hint for a question the student doesn't know."""
        prompt = f"""The student said they don't know the answer to:
"{question['text']}"

Give a SHORT, encouraging hint (1-2 sentences) that points them in the right direction without giving away the answer.
Be warm and supportive."""
        return await self.llm.generate(prompt, max_tokens=100, temperature=0.3)
