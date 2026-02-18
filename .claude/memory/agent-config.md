# Agent Config & Squads — Institutional Memory

## The Core Insight (from Vapi)

Vapi's success is the abstraction: **the assistant is a JSON config object**.
Developers don't write pipeline code. They write configuration.

Vartalaap's equivalent: `AssistantConfig` Pydantic model. New business = new config.
No code changes to `pipeline.py`, `session.py`, or any service file.

## Current State vs Target State

**Current:** Business config in `config/*.yaml`, hardcoded into `PipelineConfig`, no agent abstraction.

**Target:** `AssistantConfig` Pydantic model → loaded from DB or YAML → injected into session at call start.

## Why Three-Layer Provider Abstraction Matters

STT, LLM, TTS are independently swappable. This enables:
- Cost optimization: swap ElevenLabs TTS for Piper (free)
- Latency optimization: swap OpenAI for Groq (sub-100ms)
- Quality optimization: swap Deepgram for Bhashini (better pure Hindi)
- A/B testing: different TTS voices per business

Implemented as `STTConfig`, `LLMConfig`, `TTSConfig` — each with `provider` field.

## Squad Design Patterns

### Simple Restaurant Squad (current use case)
```
ReceptionistAgent
  ├─ BookingAgent      (when: reservation intent detected)
  ├─ SupportAgent      (when: info/menu/hours queries)
  └─ TransferAgent     (when: human requested OR complaint)
```

### Transfer vs Handoff
- **Within-call agent swap** (squads): No telephony change. Swap config + inject history.
- **Human transfer** (warm/cold): Uses Plivo `Call.transfer()` API. Telephony-level.

Always prefer within-call agent swap unless the destination is a human on a different phone.

## Conversation History in Transfers

When transferring from ReceptionistAgent → BookingAgent:
```python
# Injected as first system message to BookingAgent
transfer_context = {
    "role": "system",
    "content": f"""[Agent transfer from: ReceptionistAgent]
[Transfer summary: {summary}]
[Conversation so far:
{conversation_history}
]
Now continue as BookingAgent. The user wants to make a reservation."""
}
```

Full history available. BookingAgent knows what was already discussed.

## Function Tool Design Principles

1. **Every tool has filler phrases** (Hindi + English). No exceptions.
2. **Tools return strings** — LLM generates the natural spoken version.
   Don't return JSON; return "Table for 4 available at 7pm and 8:30pm on Saturday."
3. **Tools are async** — always. DB queries, API calls, everything async.
4. **Tool failures have voice responses** — `request_failed` phrase defined per tool.

```python
# Good tool return value (string for LLM)
"Tables available for 4 on Saturday: 7:00 PM, 8:30 PM, and 9:00 PM"

# Bad tool return value (forces LLM to format it)
{"slots": ["19:00", "20:30", "21:00"], "date": "2026-03-07", "capacity": 4}
```

## Per-Agent Endpointing

Different call types need different endpointing sensitivity:

| Call Type | `endpointing_ms` | Reasoning |
|-----------|-----------------|-----------|
| Fast booking call | 250ms | User knows what they want, fast paced |
| Customer support | 400ms (default) | Allow thinking pauses |
| Elderly / slow speakers | 600ms | Don't cut them off |
| Noisy environments | 500ms | More silence before commit |

Expose as `AssistantConfig.stt.endpointing_ms`. Set in YAML per business.

## Multi-Language Squad Routing

For a multilingual business, route to specialized agents by detected language:

```python
# In ReceptionistAgent tools:
@tool_registry.register(name="route_by_language")
async def route_by_language(detected_language: str) -> str:
    if detected_language == "hi":
        await squad.transfer("hindi_agent", "Caller prefers Hindi")
    elif detected_language == "en":
        await squad.transfer("english_agent", "Caller prefers English")
    return "Routing to appropriate assistant..."
```

## Async Function Calling for Long Ops (>3 seconds)

Pattern for slow operations (payment processing, external API):
1. Speak filler immediately: "Ek minute, main process kar rahi hoon..."
2. Execute async
3. If user speaks during execution: barge-in cancels, treat as new turn
4. If completes: LLM speaks result naturally

If op takes >10s, offer intermediate update: "Still working on it, almost done..."

## Agent Config Storage

- **MVP:** YAML files in `config/`, loaded at startup, cached in memory
- **Multi-tenant (Phase 6):** PostgreSQL `agent_configs` table, CRUD via admin UI
- **Migration path:** YAML → DB should be a config migration, not code change

## What Config Should NOT Contain

- Pipeline implementation details (that's `pipeline.py`)
- Business logic that applies to all assistants (that's `session.py`)
- Raw audio processing parameters (that's `PipelineConfig`)
- PII or API keys (that's `.env`)
