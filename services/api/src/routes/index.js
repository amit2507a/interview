/**
 * routes/index.js
 * Central router mount — NO logic here, only wiring.
 */
const { Router } = require('express');

const healthRouter  = require('./health');
const authRouter    = require('./auth');
const sessionsRouter = require('./sessions');
const reportsRouter  = require('./reports');

const router = Router();

router.use('/health',   healthRouter);
router.use('/auth',     authRouter);
router.use('/sessions', sessionsRouter);
router.use('/reports',  reportsRouter);

module.exports = router;
