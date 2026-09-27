"""
AI Interview Platform — FastAPI AI Service
Entry point
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.interview.router import router as interview_router
from app.evaluation.router import router as evaluation_router
from app.questions.router import router as questions_router
from app.config import settings
import structlog

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("AI service starting up", model=settings.BEDROCK_MODEL_ID)
    yield
    logger.info("AI service shutting down")


app = FastAPI(
    title="Interview AI Service",
    description="AI Interview Engine + Evaluation Engine",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.API_URL],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "interview-ai"}


# ─── Routers ──────────────────────────────────────────────────
app.include_router(interview_router, prefix="/interview", tags=["interview"])
app.include_router(evaluation_router, prefix="/evaluation", tags=["evaluation"])
app.include_router(questions_router, prefix="/questions", tags=["questions"])
