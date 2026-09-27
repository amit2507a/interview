/**
 * routes/health/index.js
 * Health check — no auth, no DB dependency.
 */
const { Router } = require('express');
const router = Router();

router.get('/', (req, res) => {
  res.json({
    status: 'ok',
    service: 'interview-api',
    ts: new Date().toISOString(),
  });
});

module.exports = router;
