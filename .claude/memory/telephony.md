# Telephony (Plivo) — Institutional Memory

## Audio Format

- Plivo sends and receives: **8kHz μ-law (PCMU)**
- Codec code in Plivo XML: `0` (PCMU)
- Binary format: signed 8-bit μ-law encoded samples
- Python decoding: `audioop.ulaw2lin(data, 2)` → signed 16-bit PCM

## WebSocket Architecture

- WebSocket path: `/ws/plivo/{call_uuid}` (defined in `src/api/websocket/`)
- Plivo connects to this endpoint when call is answered
- Messages are binary (audio chunks), not JSON
- Session keyed by `call_uuid`; stored in Redis for multi-process access

## Webhook Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/plivo/answer` | POST | Called when call connects; returns Plivo XML with `<Stream>` |
| `/plivo/hangup` | POST | Called when call ends; triggers cleanup |

## Plivo XML for Bidirectional Streaming

```xml
<Response>
  <Stream bidirectional="true" keepCallAlive="true">
    wss://your-domain.com/ws/plivo/{call_uuid}
  </Stream>
</Response>
```

- `bidirectional="true"` required for two-way audio
- `keepCallAlive="true"` keeps call connected while streaming
- Must be `wss://` (secure WebSocket) in production

## Session & Business Context

- Session lifecycle: answer webhook → WebSocket connect → audio loop → hangup
- Business context (restaurant config) loaded at session start
- Context switching: caller's previous preferences fetched via `caller_id_hash`
- Session state machine: `src/core/session.py`

## Call Flow

```
Inbound call → Plivo → POST /plivo/answer
                         ↓ Returns XML with <Stream>
              Plivo → WS /ws/plivo/{call_uuid}
                         ↓ Binary audio frames
              App → Deepgram STT → Groq LLM → Piper TTS
                         ↓ Binary audio frames
              App → Plivo → Caller
```

## Testing Without Real Calls

- Test script: `uv run python scripts/test_call.py`
- Simulates Plivo WebSocket connection with recorded audio
- Admin voice test page also supports browser-based testing (no telephony needed)

## Plivo Credentials

- `PLIVO_AUTH_ID` and `PLIVO_AUTH_TOKEN` in `.env`
- Phone number purchased in Plivo console; set answer/hangup URLs there
- Webhook URLs must be publicly accessible (use ngrok for local dev)

## ngrok for Local Development

```bash
ngrok http 8000
# Then set in Plivo console:
# Answer URL: https://<ngrok-id>.ngrok.io/plivo/answer
# Hangup URL: https://<ngrok-id>.ngrok.io/plivo/hangup
```

## Known Gotchas

- Plivo WebSocket sends a start frame (JSON) before audio — skip it
- Audio frames are base64-encoded in some Plivo modes — check `event` field
- Call UUID is in the answer webhook POST body, not query params
- If WebSocket closes unexpectedly, Plivo may not trigger hangup webhook
- Plivo has ~100ms jitter buffer — account for this in latency measurements
- Test calls from India require Indian DID number (local number rules apply)
