# /squads — Agent Config & Multi-Agent Orchestration Skill

You are working on Vartalaap's agent layer — the assistant-as-config pattern,
function calling with filler phrases, and multi-agent squad orchestration.

This is the developer experience layer. The goal: a new voice bot for a new business
is a new Pydantic config object, not new pipeline code.

## The Core Abstraction: Assistant-as-Config

Every voice bot is a `AssistantConfig` — a single Pydantic model bundling everything:
```python
class AssistantConfig(BaseModel):
    id: str
    name: str
    system_prompt: str
    first_message: str          # Spoken immediately when call connects

    # Pipeline tuning (per-assistant)
    stt: STTConfig
    llm: LLMConfig
    tts: TTSConfig

    # Behavioral
    tools: list[ToolConfig] = []
    silence_timeout_s: int = 30
    barge_in_enabled: bool = True
    min_interruption_ms: int = 500  # Silero VAD threshold
    endpointing_ms: int = 400       # Deepgram utterance_end_ms

    # Squad config
    squad_members: list[str] = []   # IDs of agents this one can transfer to
    transfer_tool_name: str = "transfer_to_agent"
```

**Key principle (from Vapi):** Developers configure assistants, they don't write pipeline code.
Adding Himalayan Kitchen 2.0 = new AssistantConfig, not new Python modules.

## Key Files

| File | Purpose |
|------|---------|
| `src/agents/config.py` | AssistantConfig, STTConfig, LLMConfig, TTSConfig models |
| `src/agents/registry.py` | In-memory + DB registry of assistant configs |
| `src/agents/squads.py` | Squad definition, transfer logic |
| `src/core/tools.py` | Tool registry, filler system, execution |
| `src/core/session.py` | Active agent config per call session |
| `config/*.yaml` | Per-business configs (migrate to AssistantConfig) |

## Function Calling with Filler Phrases

**Why this matters:** A 2–3 second DB query sounds like a system failure without filler.
The filler phrase makes it feel like the bot is thinking, not broken.

```python
# Tool registration (decorator pattern from Pipecat)
from src.core.tools import tool_registry

@tool_registry.register(
    name="check_availability",
    filler_hi="Ek second, main availability check kar rahi hoon...",
    filler_en="One moment, checking availability for you..."
)
async def check_availability(date: str, party_size: int) -> str:
    # This runs while the filler is being spoken
    result = await db.check_slots(date, party_size)
    return f"Available times: {result}"

# Execution in pipeline (src/core/tools.py)
async def execute_tool(name: str, args: dict, pipeline: VoicePipeline) -> str:
    tool = tool_registry.get(name)
    lang = pipeline.session.detected_language  # "hi" or "en"
    filler = tool.filler_hi if lang == "hi" else tool.filler_en

    # Speak filler while executing
    filler_task = asyncio.create_task(pipeline.speak_text(filler))
    result = await tool.func(**args)
    await filler_task  # Let filler finish (or get interrupted by user)
    return result  # Fed back to LLM for natural response
```

## Built-in Tools for Restaurant Use Case

```python
# All registered in src/core/tools.py
check_availability(date: str, party_size: int) -> str
book_reservation(date: str, time: str, party_size: int, name: str) -> str
search_menu(query: str) -> str          # ChromaDB RAG
get_hours() -> str                      # From business config
get_specials() -> str                   # From business config
request_callback(reason: str) -> str    # Creates WhatsApp followup
transfer_to_agent(agent_id: str, summary: str) -> None  # Squad transfer
```

## Squad Architecture

A squad is a set of `AssistantConfig` objects with transfer relationships.
Handoff = swap active config, preserve conversation history, inject transfer context.

```
Himalayan Kitchen Squad:
  ReceptionistAgent (default)
      ├── transfer → BookingAgent    (when: user wants reservation)
      ├── transfer → SupportAgent    (when: menu/hours/info queries)
      └── transfer → HumanAgent      (when: complex/complaint/user asks for human)
```

### Transfer Flow (no telephony change, just config swap)

```python
# In src/agents/squads.py
async def transfer_agent(
    current_session: CallSession,
    target_agent_id: str,
    transfer_summary: str,
) -> None:
    new_config = registry.get(target_agent_id)

    # Inject transfer context into new agent's first message
    injected_context = f"[Transfer context: {transfer_summary}]\n[Full history: {current_session.get_transcript()}]"

    # Swap config — audio stream continues uninterrupted
    current_session.set_active_agent(new_config, injected_context)

    # State machine transitions to LISTENING after transfer
```

**Key insight from Vapi:** No telephony-level transfer needed for agent-to-agent within same call.
It's just swapping which system_prompt + tool_set is active while preserving message_history.

## Three-Layer Provider Abstraction

STT, LLM, TTS are independently swappable — changing one shouldn't touch the others:

```python
class STTConfig(BaseModel):
    provider: Literal["deepgram", "bhashini", "assemblyai"] = "deepgram"
    model: str = "nova-2"
    language: str = "hi"        # "hi" for Hindi, "hi-en" for Hinglish
    endpointing_ms: int = 400

class LLMConfig(BaseModel):
    provider: Literal["groq", "openai", "anthropic"] = "groq"
    model: str = "llama-3.3-70b-versatile"
    temperature: float = 0.3    # Lower for tasks, higher for chat
    max_tokens: int = 200       # Keep short for voice

class TTSConfig(BaseModel):
    provider: Literal["piper", "elevenlabs", "edge"] = "piper"
    voice: str = "hi_IN-priyamvada-medium"
    speed: float = 1.0
```

## Language Detection

Per-turn language detection for filler phrase selection:
```python
def detect_language(transcript: str) -> Literal["hi", "en", "hi-en"]:
    # Count Hindi Unicode chars (Devanagari: U+0900–U+097F)
    hindi_chars = sum(1 for c in transcript if '\u0900' <= c <= '\u097F')
    ratio = hindi_chars / max(len(transcript), 1)
    if ratio > 0.3: return "hi"
    if ratio > 0.1: return "hi-en"
    return "en"
```

## Async Function Calling (Long Operations)

For operations > 3 seconds (e.g., external API calls):
- Speak filler, execute async
- While waiting, offer continuation: "Aap hold karein, main dhundhti hoon"
- If user speaks before result: treat as new turn (barge-in), cancel the pending tool

## Adding a New Business (The Target DX)

```python
# config/spice_garden.py (new business = new config file)
spice_garden = AssistantConfig(
    id="spice_garden",
    name="Spice Garden Assistant",
    system_prompt="""...""",
    first_message="Namaste! Spice Garden mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?",
    stt=STTConfig(language="hi"),
    llm=LLMConfig(temperature=0.3),
    tts=TTSConfig(voice="hi_IN-priyamvada-medium"),
    tools=["check_availability", "book_reservation", "search_menu", "get_hours"],
)
# Register with registry and it's live. No pipeline code changed.
```

## Testing

```bash
# Test agent config loading
uv run python -c "from src.agents.config import AssistantConfig; print('OK')"

# Test tool execution
uv run python scripts/test_tools.py --tool check_availability --args '{"date":"2026-03-01","party_size":4}'

# Test squad transfer (simulated)
uv run python scripts/test_squad.py --from receptionist --to booking
```
