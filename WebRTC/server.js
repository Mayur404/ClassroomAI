require('dotenv').config();
const express = require('express');
const http = require('http');

const app = express();
const server = http.createServer(app);

app.use(express.json());
app.use(express.static('public'));

console.log('Sarvam key:', process.env.SARVAM_API_KEY ? 'YES' : 'NO');
console.log('Groq key:', process.env.GROQ_API_KEY ? 'YES' : 'NO');

// Mount both modules — pass the SAME server instance
const { setupWebRTCSignaling } = require('./webrtc-signaling');
const { setupAICall } = require('./ai-call');

setupWebRTCSignaling(server, app);
setupAICall(server, app);

server.listen(3000, () => {
  console.log('Server running on http://localhost:3000');
});