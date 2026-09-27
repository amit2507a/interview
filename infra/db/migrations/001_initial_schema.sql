-- ============================================================
-- AI Interview Platform — Initial Database Schema
-- Migration: 001_initial_schema.sql
-- ============================================================

-- Enable pgvector for JD similarity search
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS vector;

-- ─── Users ──────────────────────────────────────────────────
CREATE TABLE users (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    email       VARCHAR(255) UNIQUE NOT NULL,
    name        VARCHAR(255),
    password_hash TEXT,                -- null if Cognito managed
    created_at  TIMESTAMPTZ DEFAULT NOW(),
    updated_at  TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Rubric Versions ─────────────────────────────────────────
-- Every report must reference the rubric used to produce it
CREATE TABLE rubric_versions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    version         VARCHAR(20) NOT NULL UNIQUE,  -- e.g. "1.0.0"
    model_used      VARCHAR(100) NOT NULL,
    weights         JSONB NOT NULL,               -- per-dimension weights
    prompt_hash     TEXT,                          -- hash of scoring prompts
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- Insert baseline rubric
INSERT INTO rubric_versions (version, model_used, weights) VALUES (
    '1.0.0',
    'anthropic.claude-3-5-sonnet-20241022-v2:0',
    '{
        "technical_accuracy": 0.40,
        "communication": 0.20,
        "answer_relevance": 0.20,
        "answer_structure": 0.10,
        "presentation": 0.10
    }'::jsonb
);

-- ─── Interview Sessions ───────────────────────────────────────
CREATE TYPE session_status AS ENUM (
    'not_started',
    'in_progress',
    'completed',
    'processing',
    'report_ready',
    'failed'
);

CREATE TYPE interview_mode AS ENUM ('text', 'voice', 'video');

CREATE TABLE interview_sessions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    user_id         UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    status          session_status DEFAULT 'not_started',
    mode            interview_mode DEFAULT 'text',

    -- Setup config
    job_title       VARCHAR(255) NOT NULL,
    difficulty      VARCHAR(50) NOT NULL,   -- easy | medium | hard
    jd_text         TEXT,
    jd_s3_key       TEXT,                   -- if uploaded as file
    duration_min    INTEGER DEFAULT 20,

    -- Idempotency
    idempotency_key VARCHAR(255) UNIQUE,

    -- S3 references for media
    video_s3_key    TEXT,
    audio_s3_key    TEXT,

    -- Timestamps
    started_at      TIMESTAMPTZ,
    completed_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_sessions_user_id ON interview_sessions(user_id);
CREATE INDEX idx_sessions_status ON interview_sessions(status);

-- ─── Questions ────────────────────────────────────────────────
CREATE TABLE questions (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    sequence_num    INTEGER NOT NULL,       -- order within interview
    question_text   TEXT NOT NULL,
    question_type   VARCHAR(50),            -- technical | behavioral | situational
    generated_by    VARCHAR(100),           -- model that generated it
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_questions_session ON questions(session_id, sequence_num);

-- ─── Answers ──────────────────────────────────────────────────
CREATE TABLE answers (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    question_id     UUID NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    answer_text     TEXT,
    audio_s3_key    TEXT,
    duration_sec    INTEGER,
    started_at      TIMESTAMPTZ,
    submitted_at    TIMESTAMPTZ,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Transcripts ──────────────────────────────────────────────
CREATE TABLE transcripts (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    answer_id       UUID REFERENCES answers(id),
    full_text       TEXT NOT NULL,
    words_json      JSONB,          -- [{word, start_ms, end_ms, confidence}]
    stt_provider    VARCHAR(50),    -- whisper | aws_transcribe
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Evaluation Scores ────────────────────────────────────────
CREATE TABLE evaluation_scores (
    id                   UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id           UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,
    rubric_version_id    UUID NOT NULL REFERENCES rubric_versions(id),

    -- Per-dimension scores (0-100)
    technical_accuracy   NUMERIC(5,2),
    communication        NUMERIC(5,2),
    answer_relevance     NUMERIC(5,2),
    answer_structure     NUMERIC(5,2),
    presentation         NUMERIC(5,2),

    -- Weighted final
    overall_score        NUMERIC(5,2),

    -- Evaluator output details
    dimension_details    JSONB,     -- per-dimension breakdown + feedback
    created_at           TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_scores_user ON evaluation_scores(session_id);

-- ─── Observable Video Signals ─────────────────────────────────
-- Signals only — no emotional inferences
CREATE TABLE video_signals (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id              UUID NOT NULL REFERENCES interview_sessions(id) ON DELETE CASCADE,

    -- Face signals
    face_detected_pct       NUMERIC(5,2),   -- % frames face visible
    gaze_center_pct         NUMERIC(5,2),   -- % time looking at camera
    gaze_away_pct           NUMERIC(5,2),   -- % time looking away
    head_movement_score     NUMERIC(5,2),   -- 0=still, 100=excessive

    -- Audio signals
    words_per_min           NUMERIC(7,2),
    filler_word_count       INTEGER,
    filler_words            JSONB,           -- {"um": 12, "uh": 5, "like": 3}
    long_pause_count        INTEGER,         -- pauses > 3s
    audio_clarity_score     NUMERIC(5,2),

    -- Environment
    lighting_quality        VARCHAR(20),     -- good | poor | very_poor
    background_quality      VARCHAR(20),

    created_at              TIMESTAMPTZ DEFAULT NOW()
);

-- ─── Reports ──────────────────────────────────────────────────
CREATE TABLE reports (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id          UUID NOT NULL UNIQUE REFERENCES interview_sessions(id),
    user_id             UUID NOT NULL REFERENCES users(id),
    rubric_version_id   UUID NOT NULL REFERENCES rubric_versions(id),

    overall_score       NUMERIC(5,2),
    readiness_level     VARCHAR(50),    -- not_ready | developing | ready | strong

    strengths           JSONB,          -- list of strength strings
    weaknesses          JSONB,          -- list of weakness strings
    improvement_plan    JSONB,          -- structured plan with priorities

    full_report_json    JSONB,          -- complete report for rendering
    pdf_s3_key          TEXT,

    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_reports_user ON reports(user_id, created_at DESC);

-- ─── JD Embeddings (for similarity search) ────────────────────
CREATE TABLE jd_embeddings (
    id              UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    session_id      UUID NOT NULL REFERENCES interview_sessions(id),
    embedding       vector(1536),       -- OpenAI / Bedrock embedding dim
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX idx_jd_embeddings_vector ON jd_embeddings
    USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);

-- ─── Auto-update updated_at ───────────────────────────────────
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_users_updated_at
    BEFORE UPDATE ON users
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

CREATE TRIGGER update_sessions_updated_at
    BEFORE UPDATE ON interview_sessions
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();
