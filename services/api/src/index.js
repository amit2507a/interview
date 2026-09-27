require('dotenv').config();
const express = require('express');
const helmet = require('helmet');
const cors = require('cors');
const { createServer } = require('http');
const { WebSocketServer } = require('ws');

const authRoutes = require('./routes/auth');
const sessionRoutes = require('./routes/sessions');
const reportRoutes = require('./routes/reports');
const { errorHandler } = require('./middleware/errorHandler');
const { authMiddleware } = require('./middleware/auth');
const logger = require('./lib/logger');

const app = express();
const httpServer = createServer(app);

// ─── Security & Parsing ──────────────────────────────────────
app.use(helmet());
app.use(cors({ origin: process.env.FRONTEND_URL || 'http://localhost:3000' }));
app.use(express.json({ limit: '1mb' }));

// ─── Health Check ────────────────────────────────────────────
app.get('/health', (req, res) => {
  res.json({ status: 'ok', service: 'interview-api', ts: new Date().toISOString() });
});

// ─── Routes ──────────────────────────────────────────────────
app.use('/auth', authRoutes);
app.use('/sessions', authMiddleware, sessionRoutes);
app.use('/reports', authMiddleware, reportRoutes);

// ─── Error Handler ───────────────────────────────────────────
app.use(errorHandler);

// ─── WebSocket Server ────────────────────────────────────────
// Used to push "report ready" notifications to students
const wss = new WebSocketServer({ server: httpServer });
wss.on('connection', (ws, req) => {
  logger.info('WebSocket client connected');
  ws.on('close', () => logger.info('WebSocket client disconnected'));
});

// Attach wss to app so routes can broadcast
app.set('wss', wss);

// ─── Start ───────────────────────────────────────────────────
const PORT = process.env.API_PORT || 4000;
httpServer.listen(PORT, () => {
  logger.info(`Interview API running on port ${PORT}`);
});

module.exports = { app, httpServer };
