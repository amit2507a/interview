const express = require('express');
const router = express.Router();
const { v4: uuidv4 } = require('uuid');
const db = require('../db');
const { generatePresignedUploadUrl } = require('../aws/s3');
const { enqueueVideoJob } = require('../aws/sqs');

/**
 * POST /sessions/start
 * Create a new interview session
 */
router.post('/start', async (req, res, next) => {
  try {
    const { jobTitle, difficulty, jdText, mode, durationMin } = req.body;
    const userId = req.user.id;

    // Idempotency: client should send a unique key
    const idempotencyKey = req.headers['x-idempotency-key'] || uuidv4();

    // Check for duplicate
    const existing = await db.query(
      'SELECT id FROM interview_sessions WHERE idempotency_key = $1',
      [idempotencyKey]
    );
    if (existing.rows.length > 0) {
      return res.json({ sessionId: existing.rows[0].id, duplicate: true });
    }

    const result = await db.query(
      `INSERT INTO interview_sessions
        (user_id, job_title, difficulty, jd_text, mode, duration_min, idempotency_key, status)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'not_started')
       RETURNING id`,
      [userId, jobTitle, difficulty, jdText, mode || 'text', durationMin || 20, idempotencyKey]
    );

    res.status(201).json({ sessionId: result.rows[0].id });
  } catch (err) {
    next(err);
  }
});

/**
 * GET /sessions/:id/status
 * Poll processing status
 */
router.get('/:id/status', async (req, res, next) => {
  try {
    const { id } = req.params;
    const result = await db.query(
      'SELECT id, status, updated_at FROM interview_sessions WHERE id = $1 AND user_id = $2',
      [id, req.user.id]
    );
    if (!result.rows.length) return res.status(404).json({ error: 'Session not found' });
    res.json(result.rows[0]);
  } catch (err) {
    next(err);
  }
});

/**
 * POST /sessions/:id/upload-url
 * Get S3 presigned URL for video upload
 */
router.post('/:id/upload-url', async (req, res, next) => {
  try {
    const { id } = req.params;
    const { contentType } = req.body; // e.g. "video/webm"

    const s3Key = `videos/${req.user.id}/${id}/${uuidv4()}.webm`;
    const uploadUrl = await generatePresignedUploadUrl(s3Key, contentType);

    // Store key so worker knows where to find it
    await db.query(
      'UPDATE interview_sessions SET video_s3_key = $1 WHERE id = $2 AND user_id = $3',
      [s3Key, id, req.user.id]
    );

    res.json({ uploadUrl, s3Key });
  } catch (err) {
    next(err);
  }
});

/**
 * POST /sessions/:id/submit
 * Called after video upload completes — enqueues worker job
 */
router.post('/:id/submit', async (req, res, next) => {
  try {
    const { id } = req.params;

    // Update status to processing
    await db.query(
      "UPDATE interview_sessions SET status = 'processing', completed_at = NOW() WHERE id = $1 AND user_id = $2",
      [id, req.user.id]
    );

    // Enqueue to SQS
    await enqueueVideoJob({ sessionId: id, userId: req.user.id });

    res.json({ status: 'processing', message: 'Video submitted for analysis' });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
