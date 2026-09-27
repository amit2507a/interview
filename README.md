# AI Interview Platform

> AI-powered interview preparation — Text, Voice, and Video with progress tracking over time.

## Architecture

See [ARCHITECTURE.md](./ARCHITECTURE.md) for full system design.

## Services

| Service | Stack | Path |
|---|---|---|
| Web Frontend | Next.js 14 | `apps/web/` |
| Backend API | Node.js + Express | `services/api/` |
| AI Service | Python + FastAPI | `services/ai/` |
| AI Worker | Python (SQS consumer) | `services/worker/` |

## Local Development

```bash
# 1. Copy env file
cp .env.example .env

# 2. Start all services
docker-compose up

# 3. Frontend runs on http://localhost:3000
# 4. API runs on http://localhost:4000
# 5. AI service runs on http://localhost:8000
```

## MVP Flow

```
Student → Setup → Interview → Processing → Report → Dashboard
```

## 7-Day Build Plan

| Day | Focus |
|---|---|
| 1 | Foundation — repo, Docker, schemas, skeletons |
| 2 | AI Interview Engine — adaptive Q&A loop |
| 3 | Voice — STT, filler words, pacing |
| 4 | Video — webcam, S3 upload, worker pipeline |
| 5 | Evaluation Engine — scoring rubric, report gen |
| 6 | Product UI — dashboard, charts, comparison |
| 7 | Testing — real students, fix top failures |
