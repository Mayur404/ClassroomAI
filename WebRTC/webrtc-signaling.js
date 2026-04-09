const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');
const FormData = require('form-data');
const fetch = require('node-fetch');
const multer = require('multer');
const { generateReport } = require('./report-generator');

const rooms = {};

function setupWebRTCSignaling(server, app) {

  const { WebSocketServer } = require('ws');
  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (request, socket, head) => {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname === '/webrtc-signal') {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
      });
    }
  });

  wss.on('connection', (ws, req) => {
    const url = new URL(req.url, 'http://localhost');
    const roomId = url.searchParams.get('room');
    const role = url.searchParams.get('role');

    if (!roomId || !rooms[roomId]) {
      console.log(`[WebRTC] Invalid room: ${roomId}`);
      ws.close(1008, 'Invalid room');
      return;
    }

    console.log(`[WebRTC] ${role} joined room: ${roomId}`);
    rooms[roomId][`${role}Ws`] = ws;
    ws.roomId = roomId;
    ws.role = role;

    // When both peers join, track start time and notify agent
    if (rooms[roomId].agentWs && rooms[roomId].customerWs) {
      rooms[roomId].startTime = Date.now();
      rooms[roomId].createdAt = new Date().toISOString();
      console.log(`[WebRTC] Both peers in room — notifying agent`);
      setTimeout(() => {
        if (rooms[roomId].agentWs?.readyState === WebSocket.OPEN) {
          rooms[roomId].agentWs.send(JSON.stringify({
            type: 'peer-joined',
            role: 'customer'
          }));
        }
      }, 500);
    }

    ws.on('message', (data) => {
      const msg = JSON.parse(data);
      const otherRole = ws.role === 'agent' ? 'customer' : 'agent';
      const otherWs = rooms[roomId]?.[`${otherRole}Ws`];

      // Forward SDP and ICE
      if (['offer', 'answer', 'ice-candidate'].includes(msg.type)) {
        if (otherWs?.readyState === WebSocket.OPEN) {
          otherWs.send(JSON.stringify(msg));
        }
      }

      // Store transcript chunk with timestamp
      if (msg.type === 'transcript-chunk') {
        if (!rooms[roomId].transcript) rooms[roomId].transcript = [];
        rooms[roomId].transcript.push({
          role: msg.role,
          text: msg.text,
          time: Date.now()
        });
        console.log(`[Transcript] ${msg.role}: ${msg.text}`);
      }

      // Agent ended call → generate report
      if (msg.type === 'end-call' && ws.role === 'agent') {
        console.log(`[WebRTC] Agent ended call — generating report: ${roomId}`);

        const room = rooms[roomId];
        room.durationSeconds = Math.floor(
          (Date.now() - (room.startTime || Date.now())) / 1000
        );

        // Notify customer
        if (otherWs?.readyState === WebSocket.OPEN) {
          otherWs.send(JSON.stringify({ type: 'call-ended' }));
        }

        // Generate report
        generateReport(room, 'manual_call').then(report => {
          if (report) {
            console.log('[Manual Report] Generated successfully');
          }
        });

        rooms[roomId].status = 'ended';
      }
    });

    ws.on('close', () => {
      console.log(`[WebRTC] ${role} left room: ${roomId}`);
      if (rooms[roomId]) {
        rooms[roomId][`${role}Ws`] = null;
        if (rooms[roomId].status !== 'ended') {
          rooms[roomId].status = 'disconnected';
        }
      }
    });
  });

  // ── STT endpoint ─────────────────────────────────────────────
  const upload = multer({ storage: multer.memoryStorage() });

  app.post('/transcribe-manual', upload.single('audio'), async (req, res) => {
    try {
      const form = new FormData();
      form.append('file', req.file.buffer, {
        filename: 'audio.webm',
        contentType: 'audio/webm'
      });
      form.append('model', 'saaras:v3');
      form.append('language_code', 'unknown');

      const response = await fetch('https://api.sarvam.ai/speech-to-text', {
        method: 'POST',
        headers: {
          'api-subscription-key': process.env.SARVAM_API_KEY,
          ...form.getHeaders()
        },
        body: form
      });

      const result = await response.json();
      res.json({
        transcript: result.transcript || '',
        language_code: result.language_code || 'en-IN'
      });
    } catch (err) {
      console.error('STT error:', err);
      res.status(500).json({ error: err.message });
    }
  });

  // ── Routes ───────────────────────────────────────────────────
  app.post('/create-manual-room', (req, res) => {
    const roomId = uuidv4();
    rooms[roomId] = {
      roomId,
      customerName: req.body.customerName || 'Customer',
      agentName: req.body.agentName || 'Agent',
      bankName: req.body.bankName || 'ABC Bank',
      loanAccount: req.body.loanAccount || 'XXXX1234',
      loanAmount: req.body.loanAmount || '50,000',
      phoneNumber: req.body.phoneNumber || 'N/A',
      agentWs: null,
      customerWs: null,
      status: 'waiting',
      transcript: [],
      startTime: null,
      createdAt: null,
      durationSeconds: 0
    };

    const protocol = req.headers['x-forwarded-proto'] || 'http';
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const baseUrl = `${protocol}://${host}`;

    const agentLink = `${baseUrl}/manual-call.html?room=${roomId}&role=agent`;
    const customerLink = `${baseUrl}/customer-manual.html?room=${roomId}&role=customer`;

    console.log(`[WebRTC] Room created: ${roomId}`);
    res.json({ roomId, agentLink, customerLink });
  });

  app.get('/room/:id', (req, res) => {
    const room = rooms[req.params.id];
    if (!room) return res.status(404).json({ error: 'Room not found' });
    res.json({
      status: room.status,
      transcript: room.transcript,
      customerName: room.customerName
    });
  });
}

module.exports = { setupWebRTCSignaling };
// ```

// ---

// ## Summary
// ```
// report-generator.js  → single generateReport(session, mode)
//                         mode = 'ai_call'     → uses conversationHistory
//                         mode = 'manual_call' → uses transcript array
//                         same JSON output for both
//                         cumulative across both modes

// ai-call.js          → calls generateReport(s, 'ai_call')
//                         on [CALL_COMPLETE]
//                         all report routes included

// webrtc-signaling.js → calls generateReport(room, 'manual_call')
//                         on end-call message from agent
//                         transcript stored with timestamps
//                         startTime tracked when both join