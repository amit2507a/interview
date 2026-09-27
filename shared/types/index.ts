// Shared TypeScript types across frontend and API

export type Difficulty = 'easy' | 'medium' | 'hard';
export type InterviewMode = 'text' | 'voice' | 'video';
export type SessionStatus =
  | 'not_started'
  | 'in_progress'
  | 'completed'
  | 'processing'
  | 'report_ready'
  | 'failed';

export type ReadinessLevel = 'not_ready' | 'developing' | 'ready' | 'strong';

export interface InterviewSession {
  id: string;
  userId: string;
  status: SessionStatus;
  mode: InterviewMode;
  jobTitle: string;
  difficulty: Difficulty;
  jdText?: string;
  durationMin: number;
  startedAt?: string;
  completedAt?: string;
  createdAt: string;
}

export interface Question {
  id: string;
  sessionId: string;
  sequenceNum: number;
  questionText: string;
  questionType: 'technical' | 'behavioral' | 'situational';
}

export interface DimensionScore {
  dimension: string;
  score: number;          // 0-100
  feedback: string;
  examples: string[];
}

export interface VideoSignals {
  faceDetectedPct: number;
  gazeAwayPct: number;
  gazeCenterPct: number;
  wordsPerMin: number;
  fillerWordCount: number;
  fillerWords: Record<string, number>;
  longPauseCount: number;
  audioClarity: number;
  lightingQuality: 'good' | 'poor' | 'very_poor';
}

export interface ImprovementStep {
  priority: number;
  area: string;
  action: string;
  timeline: string;
}

export interface InterviewReport {
  id: string;
  sessionId: string;
  userId: string;
  rubricVersion: string;
  modelUsed: string;
  overallScore: number;
  readinessLevel: ReadinessLevel;
  dimensionScores: DimensionScore[];
  videoSignals?: VideoSignals;
  strengths: string[];
  weaknesses: string[];
  improvementPlan: ImprovementStep[];
  createdAt: string;
}
