const Groq = require('groq-sdk');
const fs = require('fs');
const path = require('path');

const groq = new Groq({ apiKey: process.env.GROQ_API_KEY });
const REPORTS_DIR = path.join(__dirname, 'reports');

if (!fs.existsSync(REPORTS_DIR)) {
  fs.mkdirSync(REPORTS_DIR);
}

// ── Find existing customer file by loan account ──────────────
function getCustomerFile(loanAccount) {
  if (!fs.existsSync(REPORTS_DIR)) return null;
  const files = fs.readdirSync(REPORTS_DIR).filter(f => f.endsWith('.json'));
  for (const file of files) {
    try {
      const content = JSON.parse(
        fs.readFileSync(path.join(REPORTS_DIR, file), 'utf8')
      );
      if (content.customer?.loan_account_number === loanAccount) {
        return { filename: file, data: content };
      }
    } catch(e) {}
  }
  return null;
}

// ── Build transcript text for Groq prompt ───────────────────
function buildTranscriptText(session, mode) {
  if (mode === 'manual_call') {
    return (session.transcript || [])
      .sort((a, b) => a.time - b.time)
      .map(t => `${t.role === 'agent' ? 'Agent' : 'Customer'}: ${t.text}`)
      .join('\n');
  } else {
    return (session.conversationHistory || [])
      .map(msg => {
        const speaker = msg.role === 'model' || msg.role === 'assistant'
          ? 'AI' : 'Customer';
        return `${speaker}: ${msg.content}`;
      })
      .join('\n');
  }
}

// ── Build transcript array for JSON output ───────────────────
function buildTranscriptArray(session, mode) {
  if (mode === 'manual_call') {
    const sorted = (session.transcript || []).sort((a, b) => a.time - b.time);
    return sorted.map(t => ({
      speaker_label: t.role === 'agent' ? 'AGENT' : 'SPEAKER_1',
      speaker_role: t.role === 'agent' ? 'agent' : 'customer',
      text: t.text,
      language: session.language || session.lastLanguage || 'en-IN',
      timestamp_seconds: parseFloat(
        ((t.time - (session.startTime || t.time)) / 1000).toFixed(1)
      )
    }));
  } else {
    return (session.conversationHistory || []).map((msg, i) => ({
      speaker_label: msg.role === 'model' || msg.role === 'assistant'
        ? 'AI' : 'SPEAKER_1',
      speaker_role: msg.role === 'model' || msg.role === 'assistant'
        ? 'ai' : 'customer',
      text: msg.content,
      language: session.lastLanguage || 'en-IN',
      timestamp_seconds: parseFloat((i * 5).toFixed(1))
    }));
  }
}

// ── Main report generator ────────────────────────────────────
async function generateReport(session, mode = 'ai_call') {
  console.log(`[Report] Mode: ${mode}`);
  console.log(`[Report] Customer: ${session.customerName}`);
  console.log(`[Report] Loan account: ${session.loanAccount}`);

  const existing = getCustomerFile(session.loanAccount);
  const isFirstCall = !existing;
  const callNumber = isFirstCall ? 1 : existing.data.call_history.length + 1;

  console.log(`[Report] Call number: ${callNumber}`);

  // Build previous call history context
  let previousContext = '';
  if (!isFirstCall) {
    const history = existing.data.call_history;
    previousContext = `\nPREVIOUS CALL HISTORY:\n`;
    history.forEach((call, i) => {
      const r = call.finance_report;
      previousContext += `
Call ${i + 1} (${r.created_at?.split('T')[0]}) [${call.session?.mode || 'unknown'}]:
- Payment Status: ${r.payment_status}
- Amount Paid: ${r.amount_paid ? '₹' + r.amount_paid : 'N/A'}
- Payment Date: ${r.payment_date || 'N/A'}
- Promise Date: ${r.promise_to_pay_date || 'N/A'}
- Reason: ${r.reason_for_nonpayment || 'N/A'}
- Next Action: ${r.next_action || 'N/A'}
- Notes: ${r.executive_notes || 'N/A'}`;
    });

    previousContext += `\n
CUMULATIVE STATUS:
- Total calls: ${history.length}
- Original outstanding: ₹${existing.data.customer.outstanding_amount}
- Remaining balance: ₹${existing.data.current_status.remaining_balance}
- Total paid: ₹${existing.data.current_status.total_paid}
- Total promised: ₹${existing.data.current_status.total_promised}`;
  }

  const transcriptText = buildTranscriptText(session, mode);

  const speakerNote = mode === 'manual_call'
    ? 'Agent = bank recovery agent, Customer = loan defaulter'
    : 'AI = automated bank assistant, Customer = loan defaulter';

  const prompt = `You are a financial report generator for a loan recovery system.
Analyze this ${mode === 'manual_call' ? 'manual agent' : 'AI automated'} call transcript.
${speakerNote}
${previousContext}

CUSTOMER DETAILS:
- Name: ${session.customerName}
- Bank: ${session.bankName || 'N/A'}
- Loan Account: ${session.loanAccount}
- Outstanding Amount: ₹${session.loanAmount}
- Language: ${session.lastLanguage || session.language || 'en-IN'}
- Call Number: ${callNumber}

TRANSCRIPT:
${transcriptText}

${!isFirstCall ? `
IMPORTANT CUMULATIVE INSTRUCTIONS:
- Check if the promise from the previous call was kept
- Update remaining balance based on any new payments
- Note any changes in payment behaviour vs previous calls
- executive_notes must reference previous call history
` : ''}

Return ONLY valid JSON, no markdown, no extra text:
{
  "finance_report": {
    "identity_verified": true or false,
    "loan_account_confirmed": true or false,
    "payment_status": "paid" or "partial" or "promised" or "refused" or "no_response",
    "amount_paid": number or null,
    "payment_date": "YYYY-MM-DD" or null,
    "payment_mode": "upi" or "cash" or "bank_transfer" or "cheque" or "unknown" or null,
    "payer_type": "self" or "family" or "other",
    "payer_name": "name" or null,
    "payer_relationship": "relationship" or null,
    "payer_contact": "phone" or null,
    "reason_for_nonpayment": "reason" or null,
    "promise_to_pay_date": "YYYY-MM-DD" or null,
    "executive_notes": "2-3 sentence summary referencing previous calls if any",
    "escalation_required": true or false,
    "next_action": "follow_up" or "escalate" or "close" or "no_response",
    "previous_promise_kept": true or false or null
  },
  "scheduled_calls": [
    {
      "scheduled_time": "YYYY-MM-DDTHH:MM:SSZ",
      "reason": "reason for follow up",
      "status": "pending"
    }
  ],
  "alerts": [],
  "cumulative": {
    "total_paid_so_far": number,
    "remaining_balance": number,
    "total_promised_so_far": number
  }
}

EXTRACTION RULES:
- payment_date = date customer ALREADY paid (not future promise)
- promise_to_pay_date = future date customer promises to pay
- scheduled_time = set to promise_to_pay_date at 10:00:00Z if follow up needed
- alerts = add objects if escalation needed or previous promise broken, else []
- cumulative values must account for ALL calls including this one`;

  try {
    const response = await groq.chat.completions.create({
      model: 'llama-3.3-70b-versatile',
      messages: [{ role: 'user', content: prompt }],
      max_tokens: 1000,
      temperature: 0.1
    });

    let rawText = response.choices[0].message.content;
    rawText = rawText.replace(/```json/g, '').replace(/```/g, '').trim();

    const extracted = JSON.parse(rawText);
    const now = new Date().toISOString();
    const sessionId = session.sessionId || session.roomId || `session-${Date.now()}`;
    const language = session.lastLanguage || session.language || 'en-IN';

    const callEntry = {
      session: {
        id: sessionId,
        domain: 'finance',
        mode,
        status: 'completed',
        language_detected: language,
        duration_seconds: session.durationSeconds || 0,
        created_at: session.createdAt || now,
        completed_at: now
      },
      finance_report: {
        id: `fr-${Date.now()}`,
        session_id: sessionId,
        customer_id: null,
        identity_verified: extracted.finance_report.identity_verified,
        loan_account_confirmed: extracted.finance_report.loan_account_confirmed,
        payment_status: extracted.finance_report.payment_status,
        amount_paid: extracted.finance_report.amount_paid,
        payment_date: extracted.finance_report.payment_date,
        payment_mode: extracted.finance_report.payment_mode,
        payer_type: extracted.finance_report.payer_type,
        payer_name: extracted.finance_report.payer_name,
        payer_relationship: extracted.finance_report.payer_relationship,
        payer_contact: extracted.finance_report.payer_contact,
        reason_for_nonpayment: extracted.finance_report.reason_for_nonpayment,
        promise_to_pay_date: extracted.finance_report.promise_to_pay_date,
        executive_notes: extracted.finance_report.executive_notes,
        call_attempt_number: callNumber,
        customer_language: language,
        escalation_required: extracted.finance_report.escalation_required,
        next_action: extracted.finance_report.next_action,
        previous_promise_kept: extracted.finance_report.previous_promise_kept,
        is_edited: false,
        edited_by: null,
        created_at: now,
        updated_at: now
      },
      transcript: buildTranscriptArray(session, mode),
      scheduled_calls: (extracted.scheduled_calls || []).map(sc => ({
        customer_id: null,
        origin_session_id: sessionId,
        phone_number: session.phoneNumber || 'N/A',
        scheduled_time: sc.scheduled_time,
        reason: sc.reason,
        status: sc.status || 'pending'
      })),
      alerts: extracted.alerts || []
    };

    let masterJson;

    if (isFirstCall) {
      masterJson = {
        customer: {
          id: null,
          name: session.customerName,
          phone_number: session.phoneNumber || 'N/A',
          loan_account_number: session.loanAccount,
          outstanding_amount: parseFloat(
            String(session.loanAmount || 0).replace(/,/g, '')
          ),
          bank: session.bankName || 'N/A',
          due_date: null
        },
        current_status: {
          total_paid: extracted.cumulative?.total_paid_so_far || 0,
          remaining_balance: extracted.cumulative?.remaining_balance ||
            parseFloat(String(session.loanAmount || 0).replace(/,/g, '')),
          total_promised: extracted.cumulative?.total_promised_so_far || 0,
          last_call_date: now.split('T')[0],
          last_payment_status: extracted.finance_report?.payment_status,
          next_scheduled_call: extracted.scheduled_calls?.[0]?.scheduled_time || null,
          total_calls: 1,
          escalation_required: extracted.finance_report?.escalation_required || false
        },
        call_history: [callEntry],
        created_at: now,
        updated_at: now
      };
    } else {
      masterJson = existing.data;
      masterJson.call_history.push(callEntry);
      masterJson.current_status = {
        total_paid: extracted.cumulative?.total_paid_so_far ||
          masterJson.current_status.total_paid,
        remaining_balance: extracted.cumulative?.remaining_balance ||
          masterJson.current_status.remaining_balance,
        total_promised: extracted.cumulative?.total_promised_so_far ||
          masterJson.current_status.total_promised,
        last_call_date: now.split('T')[0],
        last_payment_status: extracted.finance_report?.payment_status,
        next_scheduled_call: extracted.scheduled_calls?.[0]?.scheduled_time ||
          masterJson.current_status.next_scheduled_call,
        total_calls: callNumber,
        escalation_required: extracted.finance_report?.escalation_required || false
      };
      masterJson.updated_at = now;
    }

    const safeName = session.customerName.replace(/\s+/g, '_');
    const safeAccount = session.loanAccount.replace(/[^a-zA-Z0-9]/g, '_');
    const filename = `customer_${safeName}_${safeAccount}.json`;
    const filePath = path.join(REPORTS_DIR, filename);

    fs.writeFileSync(filePath, JSON.stringify(masterJson, null, 2));

    console.log(`[Report] Saved: ${filename}`);
    console.log(`[Report] Mode: ${mode} | Call ${callNumber} | Status: ${extracted.finance_report?.payment_status}`);
    console.log(`[Report] Remaining: ₹${masterJson.current_status.remaining_balance}`);

    return masterJson;

  } catch (err) {
    console.error('[Report] Error:', err.message);
    const fallbackPath = path.join(
      REPORTS_DIR,
      `error_${session.customerName?.replace(/\s+/g, '_')}_${Date.now()}.json`
    );
    fs.writeFileSync(fallbackPath, JSON.stringify({
      error: err.message,
      mode,
      session_id: session.sessionId || session.roomId,
      customer: session.customerName,
      loan_account: session.loanAccount,
      transcript: mode === 'manual_call'
        ? session.transcript
        : session.conversationHistory,
      timestamp: new Date().toISOString()
    }, null, 2));
    return null;
  }
}

module.exports = { generateReport };