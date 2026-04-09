require('dotenv').config();
const WebSocket = require('ws');
const { v4: uuidv4 } = require('uuid');
const axios = require('axios');
const FormData = require('form-data');
const fetch = require('node-fetch');
const multer = require('multer');
const fs = require('fs');
const path = require('path');
const Groq = require('groq-sdk');
const { generateReport } = require('./report-generator');

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });
const sessions = {};

function setupAICall(server, app) {

  const { WebSocketServer } = require('ws');
  const wss = new WebSocketServer({ noServer: true });

  server.on('upgrade', (request, socket, head) => {
    const url = new URL(request.url, 'http://localhost');
    if (url.pathname === '/ai-call') {
      wss.handleUpgrade(request, socket, head, (ws) => {
        wss.emit('connection', ws, request);
      });
    }
  });

  wss.on('connection', (ws, req) => {
    const sessionId = new URL(req.url, 'http://localhost')
      .searchParams.get('session');

    if (!sessionId || !sessions[sessionId]) {
      ws.close(1008, 'Invalid session');
      return;
    }

    console.log(`[AI Call] Customer connected: ${sessionId}`);
    sessions[sessionId].customerWs = ws;
    sessions[sessionId].status = 'connected';

    startAIConversation(sessionId);

    ws.on('message', async (data) => {
      const msg = JSON.parse(data);
      console.log(`[AI Call] Message received: type=${msg.type}`);

      if (sessions[sessionId]?.status === 'ended' ||
          sessions[sessionId]?.status === 'completing') {
        return;
      }

      if (msg.type === 'customer-speech') {
        console.log(`[AI Call] Customer said: ${msg.transcript}`);
        sessions[sessionId].lastLanguage = msg.languageCode || 'en-IN';
        await continueConversation(sessionId, msg.transcript);
      }

      if (msg.type === 'call-ended') {
        console.log(`[AI Call] Customer ended call: ${sessionId}`);
        sessions[sessionId].status = 'ended';
        sessions[sessionId].customerWs = null;
      }
    });

    ws.on('close', () => {
      console.log(`[AI Call] Customer disconnected: ${sessionId}`);
      if (sessions[sessionId]) sessions[sessionId].status = 'disconnected';
    });
  });

  // ── AI conversation ─────────────────────────────────────────
  async function startAIConversation(sessionId) {
    const s = sessions[sessionId];
    s.startTime = Date.now();
    s.createdAt = new Date().toISOString();

    const greeting = `Hello, this is an automated call from ${s.bankName}. Am I speaking with ${s.customerName}? I am calling regarding your loan account ending in ${s.loanAccount}. Do you have a moment to speak?`;
    s.conversationHistory = [{ role: 'model', content: greeting }];
    await speakToCustomer(sessionId, greeting);
  }

  async function continueConversation(sessionId, customerResponse) {
    const s = sessions[sessionId];
    s.conversationHistory.push({ role: 'user', content: customerResponse });

    try {
      const systemPrompt = `You are a professional loan recovery agent for ${s.bankName}.
    Call purpose: Collect overdue loan of ₹${s.loanAmount} from ${s.customerName} (account: ${s.loanAccount}).
    You already greeted them with: "${s.conversationHistory[0].content}"

    LANGUAGE: Always reply in the same language the customer uses.

    STRICT [CALL_COMPLETE] RULE:
    - [CALL_COMPLETE] can ONLY be output after ALL of these are done:
      a) Customer identity confirmed
      b) Loan account discussed
      c) Payment plan OR refusal after 3 attempts OR valid reason to end
      d) You asked "Is there anything else I can help you with?"
      e) Customer responded negatively to that question
    - NEVER output [CALL_COMPLETE] in the first 3 exchanges
    - NEVER output [CALL_COMPLETE] just because customer said yes or acknowledged

    CONVERSATION FLOW:
    Step 1 → Confirm identity
    Step 2 → Discuss loan amount
    Step 3 → Ask about payment status
    Step 4 → If not paid → understand reason → negotiate
    Step 5 → Confirm agreed plan with specific date and amount
    Step 6 → Ask "Is there anything else I can help you with?"
    Step 7 → On negative response → [CALL_COMPLETE]

    PRIORITY HANDLING:
    - Wrong person → apologize and [CALL_COMPLETE]
    - Already paid → note details and [CALL_COMPLETE]
    - Busy → get callback time and [CALL_COMPLETE]
    - Legal/bankruptcy → escalate and [CALL_COMPLETE]
    - Refusing payment → try 3 times before [CALL_COMPLETE]
    - Aggressive → warn once then [CALL_COMPLETE]

    STYLE: 2-3 short complete sentences. Never cut off mid sentence.

    When ending output exactly on its own line:
    [CALL_COMPLETE]
    Do not add any JSON after it.`;

      const messages = [
        { role: 'system', content: systemPrompt },
        ...s.conversationHistory.slice(1).map(msg => ({
          role: msg.role === 'model' ? 'assistant' : 'user',
          content: msg.content
        }))
      ];

      const response = await groq.chat.completions.create({
        model: 'llama-3.3-70b-versatile',
        messages,
        max_tokens: 500,
        temperature: 0.7
      });

      const aiReply = response.choices[0].message.content;
      console.log(`[AI Call] AI: ${aiReply}`);

      if (aiReply.includes('[CALL_COMPLETE]')) {
        console.log('[AI Call] Call complete — generating report...');

        s.durationSeconds = Math.floor((Date.now() - s.startTime) / 1000);
        s.status = 'completing';

        // Generate report
        generateReport(s, 'ai_call').then(report => {
          if (report) {
            s.summary = report.current_status;
            s.fullReport = report;
            console.log('[Report] Generated successfully');
          }
        });

        const goodbyeMsg = s.lastLanguage === 'kn-IN'
          ? 'ಧನ್ಯವಾದಗಳು. ನಿಮ್ಮ ದಿನ ಶುಭವಾಗಿರಲಿ.'
          : s.lastLanguage === 'hi-IN'
          ? 'धन्यवाद। आपका दिन शुभ हो।'
          : 'Thank you for your time. We will follow up as discussed. Have a good day.';

        await speakToCustomer(sessionId, goodbyeMsg, s.lastLanguage || 'en-IN');

        setTimeout(() => {
          if (s.customerWs?.readyState === WebSocket.OPEN) {
            s.customerWs.send(JSON.stringify({ type: 'call-ended' }));
            s.customerWs.close();
          }
          s.status = 'ended';
        }, 4000);
        return;
      }

      s.conversationHistory.push({ role: 'assistant', content: aiReply });
      await speakToCustomer(sessionId, aiReply, s.lastLanguage || 'en-IN');

    } catch (err) {
      console.error('[AI Call] Groq error:', err.message);
    }
  }

  // ── TTS ─────────────────────────────────────────────────────
  function splitIntoChunks(text, maxLength = 450) {
    if (text.length <= maxLength) return [text];
    const sentences = text.match(/[^.!?]+[.!?]+/g) || [text];
    const chunks = [];
    let current = '';
    for (const sentence of sentences) {
      if ((current + sentence).length <= maxLength) {
        current += sentence;
      } else {
        if (current) chunks.push(current.trim());
        current = sentence;
      }
    }
    if (current) chunks.push(current.trim());
    return chunks;
  }

  async function speakToCustomer(sessionId, text, languageCode = 'en-IN') {
    const s = sessions[sessionId];
    const chunks = splitIntoChunks(text);

    for (let i = 0; i < chunks.length; i++) {
      const chunk = chunks[i];
      const isFinal = i === chunks.length - 1;
      try {
        const response = await axios.post(
          'https://api.sarvam.ai/text-to-speech',
          {
            inputs: [chunk],
            target_language_code: languageCode,
            speaker: 'anushka',
            pace: 1.0,
            loudness: 1.5,
            model: 'bulbul:v2'
          },
          {
            headers: {
              'api-subscription-key': process.env.SARVAM_API_KEY,
              'Content-Type': 'application/json'
            }
          }
        );
        const audioBase64 = response.data.audios[0];
        if (s.customerWs?.readyState === WebSocket.OPEN) {
          s.customerWs.send(JSON.stringify({
            type: 'ai-speech',
            audio: audioBase64,
            text: chunk,
            isFinal
          }));
          await new Promise(r => setTimeout(r, 200));
        }
      } catch (err) {
        console.error('[AI Call] TTS error:', err.response?.data || err.message);
      }
    }
  }

  // ── STT ─────────────────────────────────────────────────────
  const upload = multer({ storage: multer.memoryStorage() });

  app.post('/transcribe-ai', upload.single('audio'), async (req, res) => {
    try {
      const form = new FormData();
      form.append('file', req.file.buffer, {
        filename: req.file.originalname.endsWith('.wav') ? 'audio.wav' : 'audio.webm',
        contentType: req.file.originalname.endsWith('.wav') ? 'audio/wav' : 'audio/webm'
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
      console.log('STT result:', result);
      res.json({
        transcript: result.transcript || '',
        language_code: result.language_code || 'en-IN'
      });
    } catch (err) {
      res.status(500).json({ error: err.message });
    }
  });

  // ── Routes ───────────────────────────────────────────────────
  app.post('/create-ai-session', (req, res) => {
    const sessionId = uuidv4();
    sessions[sessionId] = {
      sessionId,
      customerName: req.body.customerName || 'Customer',
      bankName: req.body.bankName || 'ABC Bank',
      loanAccount: req.body.loanAccount || 'XXXX1234',
      loanAmount: req.body.loanAmount || '50,000',
      phoneNumber: req.body.phoneNumber || 'N/A',
      conversationHistory: [],
      status: 'waiting',
      summary: null,
      fullReport: null,
      customerWs: null,
      startTime: null,
      createdAt: null,
      lastLanguage: 'en-IN'
    };

    const protocol = req.headers['x-forwarded-proto'] || 'http';
    const host = req.headers['x-forwarded-host'] || req.headers.host;
    const customerLink = `${protocol}://${host}/customer-ai.html?session=${sessionId}`;

    console.log(`[AI Call] Session created: ${sessionId}`);
    res.json({ sessionId, customerLink });
  });

  app.get('/ai-session/:id', (req, res) => {
    const s = sessions[req.params.id];
    if (!s) return res.status(404).json({ error: 'Not found' });
    res.json({
      status: s.status,
      summary: s.summary,
      fullReport: s.fullReport,
      conversationHistory: s.conversationHistory
    });
  });

  // ── Report routes ────────────────────────────────────────────
  app.get('/reports', (req, res) => {
    const reportsDir = path.join(__dirname, 'reports');
    if (!fs.existsSync(reportsDir)) return res.json({ reports: [] });

    const files = fs.readdirSync(reportsDir)
      .filter(f => f.endsWith('.json'))
      .map(f => {
        try {
          const data = JSON.parse(
            fs.readFileSync(path.join(reportsDir, f), 'utf8')
          );
          return {
            filename: f,
            customer_name: data.customer?.name,
            loan_account: data.customer?.loan_account_number,
            total_calls: data.current_status?.total_calls,
            remaining_balance: data.current_status?.remaining_balance,
            last_payment_status: data.current_status?.last_payment_status,
            next_scheduled_call: data.current_status?.next_scheduled_call,
            escalation: data.current_status?.escalation_required,
            updated_at: data.updated_at
          };
        } catch(e) { return null; }
      })
      .filter(Boolean)
      .sort((a, b) => new Date(b.updated_at) - new Date(a.updated_at));

    res.json({ reports: files });
  });

  app.get('/reports/:filename', (req, res) => {
    const filePath = path.join(__dirname, 'reports', req.params.filename);
    if (!fs.existsSync(filePath)) {
      return res.status(404).json({ error: 'Not found' });
    }
    res.json(JSON.parse(fs.readFileSync(filePath, 'utf8')));
  });

  app.put('/reports/:filename', (req, res) => {
    const filePath = path.join(__dirname, 'reports', req.params.filename);
    if (!fs.existsSync(filePath)) {
      return res.status(404).json({ error: 'Not found' });
    }
    const data = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    const callIndex = req.body.call_number - 1;
    if (data.call_history[callIndex]) {
      data.call_history[callIndex].finance_report = {
        ...data.call_history[callIndex].finance_report,
        ...req.body.updates,
        is_edited: true,
        edited_by: req.body.edited_by || 'agent',
        edited_at: new Date().toISOString(),
        updated_at: new Date().toISOString()
      };
      data.updated_at = new Date().toISOString();
      fs.writeFileSync(filePath, JSON.stringify(data, null, 2));
      res.json({ success: true });
    } else {
      res.status(400).json({ error: 'Invalid call number' });
    }
  });

  app.get('/scheduled-calls', (req, res) => {
    const reportsDir = path.join(__dirname, 'reports');
    if (!fs.existsSync(reportsDir)) return res.json({ scheduled_calls: [] });

    const all = [];
    fs.readdirSync(reportsDir).filter(f => f.endsWith('.json')).forEach(f => {
      try {
        const data = JSON.parse(
          fs.readFileSync(path.join(reportsDir, f), 'utf8')
        );
        data.call_history?.forEach(call => {
          call.scheduled_calls?.forEach(sc => {
            all.push({
              ...sc,
              customer_name: data.customer?.name,
              loan_account: data.customer?.loan_account_number,
              remaining_balance: data.current_status?.remaining_balance,
              report_file: f
            });
          });
        });
      } catch(e) {}
    });

    all.sort((a, b) => new Date(a.scheduled_time) - new Date(b.scheduled_time));
    res.json({ scheduled_calls: all });
  });
}

module.exports = { setupAICall };