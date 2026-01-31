# Product Requirements Document (PRD)
# Vartalaap - Voice Bot Platform for Local Businesses

**Product Name:** Vartalaap (वार्तालाप - "conversation" in Hindi)

**Version**: 1.0
**Date**: February 1, 2026
**Author**: Pronav
**Status**: MVP Planning

---

## 1. Executive Summary

### 1.1 Vision
Build a cost-effective, open-source voice calling bot platform to provide customer support automation for local Indian businesses, starting with a demo for an Indian Tibetan restaurant.

### 1.2 Problem Statement
Local businesses in India struggle with:
- Missing customer calls during busy hours
- High cost of dedicated customer support staff
- Language barriers (Hindi/English/Hinglish mix)
- Existing solutions (like Retell) are expensive and have poor Hindi voice quality

### 1.3 Solution
A self-hosted voice bot platform that:
- Handles inbound customer calls autonomously
- Supports natural Hindi-English code-switching
- Costs ~$16-27/month to operate (see Section 11)
- Can be configured for different businesses via a simple GUI

---

## 2. Goals & Success Metrics

### 2.1 MVP Goals (1 Month)
| Goal | Metric |
|------|--------|
| Working demo | Complete a full call flow (greeting → query → resolution) |
| Impressive quality | Voice natural enough to pitch to real business |
| Low latency | P50 processing latency < 500ms, P95 end-to-end < 1.2s (see Section 6.1 for definitions) |
| Language support | Handle Hindi, English, and Hinglish seamlessly |

### 2.2 Success Criteria (Measurable)

| Criteria | Metric | Target | Measurement Method |
|----------|--------|--------|-------------------|
| Reservation accuracy | % of bookings with correct date/time/party size | ≥ 95% | Manual review of 20 test calls |
| Menu query accuracy | % of correct price/item responses | ≥ 98% | Automated test suite |
| Language detection | % correct detection within first utterance | ≥ 90% | Test with 10 Hindi, 10 English, 10 Hinglish calls |
| Response latency | P95 end-to-end response time | < 1.2s | Automated latency logging |
| Barge-in success | % of interruptions correctly handled | ≥ 85% | Manual testing of 15 interruption scenarios |
| Call completion | % of calls reaching resolution without crash | ≥ 98% | Production logs |
| STT Word Error Rate | WER for Hindi utterances | < 15% | Compare transcripts to ground truth |

### 2.3 Qualitative Success Criteria
- [ ] Demo call successfully books a table reservation (with availability check)
- [ ] Bot correctly rejects bookings outside business hours
- [ ] At least one potential client finds demo impressive enough to discuss pricing

---

## 3. User Personas

### 3.1 End Caller (Restaurant Customer)
- **Demographics**: Mixed - Urban Hindi speakers, English-preferred professionals, Hinglish comfortable youth
- **Behavior**: Calls restaurant for quick queries, expects fast answers
- **Pain points**: Busy lines, language barriers, inconsistent information
- **Needs**: Quick menu info, easy table booking, clear communication

### 3.2 Business Owner (Future Client)
- **Demographics**: Local business owner, limited tech knowledge
- **Behavior**: Wants to reduce missed calls, improve customer service
- **Pain points**: Can't afford full-time receptionist, misses calls during rush
- **Needs**: Simple setup, reliable service, affordable pricing

### 3.3 Platform Admin (You)
- **Role**: Configure and deploy bots for different businesses
- **Needs**: Easy configuration GUI, quick deployment, monitoring tools

---

## 4. Demo Business Profile

### 4.1 Himalayan Kitchen (Fictional)
- **Type**: Indian Tibetan Restaurant
- **Location**: Delhi NCR
- **Operating Hours**: 11:00 AM - 10:30 PM (Tue-Sun), Closed Monday
- **Cuisine**: Momos, Thukpa, Tibetan dishes, North Indian
- **Capacity**: 40 seats, accepts reservations

### 4.2 Sample Menu Structure
```
MOMOS
- Veg Steam Momos - ₹180
- Chicken Steam Momos - ₹220
- Veg Fried Momos - ₹200
- Chicken Fried Momos - ₹240
- Paneer Momos - ₹220

THUKPA & SOUPS
- Veg Thukpa - ₹200
- Chicken Thukpa - ₹250
- Hot & Sour Soup - ₹150

MAIN COURSE
- Butter Chicken - ₹320
- Chilli Chicken - ₹280
- Veg Fried Rice - ₹180
- Chicken Fried Rice - ₹220

BEVERAGES
- Butter Tea - ₹80
- Masala Chai - ₹50
- Fresh Lime Soda - ₹60
```

---

## 5. Functional Requirements

### 5.1 Core Conversation Flows

#### 5.1.1 Greeting Flow
```
Bot: "Namaste! Himalayan Kitchen mein aapka swagat hai.
      Yeh call service improvement ke liye transcribe ho sakti hai.
      Main aapki kaise madad kar sakti hoon?"

[Wait for caller to speak]
[Detect language from caller's first complete utterance]
[Set language_preference for this session]
[Adapt response language - but allow mid-call switches if caller switches]
```

**Note:** Greeting includes transcription notice for consent compliance (see Section 15.2).

**Language Detection Logic:**
- Initial detection: Based on first complete utterance (not partial/filler words)
- Mid-call adaptation: If caller switches language, bot follows within 1-2 turns
- Fallback: If detection confidence < 70%, continue in Hindi (default)

#### 5.1.2 Menu Inquiry Flow
```
Caller: "Momos kitne ke hain?"
Bot: "Ji, hamare paas veg steam momos ₹180, chicken steam momos ₹220,
      aur paneer momos ₹220 ke hain. Fried momos bhi available hain.
      Aapko kaunse chahiye?"
```

#### 5.1.3 Table Reservation Flow

**Prerequisites:** System checks against configurable business rules (see Section 8.5).

```
Caller: "Table book karni hai"
Bot: "Zaroor! Kitne logon ke liye table chahiye?"
Caller: "4 log"
Bot: "Aur kis din aur time ke liye?"
Caller: "Aaj raat 8 baje"

[SYSTEM CHECK: Validate against business_config.reservation_rules]
├── Is requested date/time within operating hours?
├── Is restaurant open on that day?
├── Is requested time at least {min_advance_booking_mins} from now?
├── Is capacity available? (check current bookings)
└── Party size within {max_phone_party_size}?

[IF ALL CHECKS PASS:]
Bot: "Perfect. Aaj raat 8 baje, 4 logon ke liye table.
      Booking confirm karne ke liye aapka naam bata dijiye?"
Caller: "Rahul"
Bot: "Dhanyavaad Rahul ji. Aapka phone number kya hai?
      Confirmation WhatsApp pe bhej denge."
Caller: "98XXXXXXXX"
Bot: "98XXXXXXXX pe confirmation aa jayega. Aapka welcome hai!"

[WHATSAPP CONSENT: Captured implicitly when caller provides number for confirmation]
[Phone number stored encrypted (not hashed) for WhatsApp delivery - see Section 9.4]

[IF CLOSED/OUTSIDE HOURS:]
Caller: "Monday ko book karo"
Bot: "Sorry, Monday ko restaurant band rehta hai.
      Tuesday se Sunday, 11 baje se 10:30 baje tak khule hain.
      Koi aur din chalega?"

[IF CAPACITY FULL:]
Bot: "Sorry, 8 baje ke liye tables full hain.
      7:30 ya 9 baje available hai. Kaunsa time theek rahega?"

[IF PARTY TOO LARGE:]
Caller: "15 logon ke liye"
Bot: "15 logon ke liye phone pe booking nahi ho sakti.
      Aapka number dijiye, humari team WhatsApp pe contact karegi."
```

**Reservation Conflict Handling:**
- Double-booking prevention: Check existing reservations before confirming
- Time slot buffer: `{dining_window_mins}` from config (default 90 min)
- Capacity calculation: `{total_seats}` minus confirmed reservations for time slot
- Waitlist (future): If full, offer to add to waitlist with callback

#### 5.1.4 Timings & Location Flow
```
Caller: "Restaurant kab tak khula hai?"
Bot: "Hum subah 11 baje se raat 10:30 baje tak khule hain,
      Tuesday se Sunday. Monday ko restaurant band rehta hai."

Caller: "Address kya hai?"
Bot: "Hum [Address] mein hain, [Landmark] ke paas.
      Kya main aapko WhatsApp pe location bhej doon?"
```

#### 5.1.5 Fallback/Handoff Flow
```
[When bot cannot handle query]
Bot: "Yeh information mere paas abhi available nahi hai.
      Kya aap chahte hain ki humari team aapko WhatsApp pe contact kare?"

[IF CALLER AGREES:]
Caller: "Haan" / "Yes"
Bot: "Aapka WhatsApp number bata dijiye?"
Caller: "98XXXXXXXX"
Bot: "Shukriya! 98XXXXXXXX pe 10 minute mein message aayega."

[WHATSAPP CONSENT: Explicit - caller agreed AND provided number]
[Phone number stored encrypted for WhatsApp delivery]

[IF CALLER DECLINES:]
Caller: "Nahi" / "No need"
Bot: "Koi baat nahi. Aap kabhi bhi call kar sakte hain. Dhanyavaad!"
[No number captured, no WhatsApp sent]
```

### 5.2 Language Handling

#### 5.2.1 Language Detection Strategy
| Phase | Behavior | Timing |
|-------|----------|--------|
| Greeting | Bot speaks formal Hindi | Immediate |
| Detection | Analyze caller's first complete utterance (ignore fillers like "hello", "haan") | After first substantive response |
| Initial adaptation | Switch to detected language | From second bot response onwards |
| Mid-call switching | If caller switches language, bot follows within 1-2 turns | Continuous monitoring |

**Detection Confidence Thresholds:**
- High confidence (>85%): Switch immediately
- Medium confidence (70-85%): Switch but monitor for correction
- Low confidence (<70%): Stay in Hindi, adapt if caller repeats in different language

#### 5.2.2 Code-Switching Rules
| Caller Pattern | Bot Response Strategy |
|----------------|----------------------|
| Pure Hindi | Hindi with common English words (menu items, numbers, "okay", "booking") |
| Pure English | English |
| Hinglish | Hinglish (natural mix matching caller's ratio) |
| Switches mid-call | Match the switch within next response |
| Mixed in single sentence | Respond in Hinglish |

**Note:** Language preference is per-session, not locked after detection. Bot continuously adapts.

### 5.3 Context Management

#### 5.3.1 Information to Track (Per Call)
- Caller's detected language preference
- Name (if provided)
- Party size (for reservations)
- Requested date/time
- Items discussed/ordered
- Any special requests

#### 5.3.2 Information Handling Rules
| Type | Behavior | Example |
|------|----------|---------|
| General chitchat | Don't store in context | "Mausam kaisa hai" |
| Filler words | Ignore for context | "hmm", "okay", "achha", "uh" |
| Repeated confirmation | Keep latest value only | "haan 4 log" after already saying "4 log" |
| **Corrections** | **ALWAYS update to new value** | "actually 6 log, not 4" → update party_size to 6 |
| **Modifications** | **Replace previous value** | "8 nahi, 8:30 baje" → update time to 8:30 |

**Critical:** Corrections and modifications MUST override previous values. The bot should:
1. Acknowledge the correction: "Okay, 6 logon ke liye"
2. Update internal state immediately
3. Reflect corrected value in confirmation

### 5.4 Interruption Handling

| Interruption Type | Detection Method | Bot Behavior |
|-------------------|------------------|--------------|
| Question mid-response | Rising intonation, question words | Stop immediately, listen |
| Filler words ("hmm", "haan") | Short duration, no semantic content | Continue speaking |
| "Wait" or "ruko" | Explicit pause keywords | Pause, wait for caller to continue |
| Caller provides information | Substantive content detected | Stop, process new information |
| Caller says "no" or corrects | Negation/correction detected | Stop, acknowledge, update |

**Scope Clarification (MVP):**
- "Ordering" in this context means caller providing booking/query information, NOT food ordering for delivery
- Food ordering flow is OUT OF SCOPE for MVP (restaurant is dine-in only)
- If caller asks about delivery/takeaway: "Abhi sirf dine-in available hai, delivery nahi hai"

**Barge-in Technical Implementation:**
- Voice Activity Detection (VAD) threshold: 300ms of speech
- Ignore audio < 200ms (likely noise)
- On valid barge-in: Stop TTS playback within 100ms

---

## 6. Non-Functional Requirements

### 6.1 Performance & Latency

**Definitions:**
- **Response latency**: Time from end of caller speech to first byte of bot audio playing
- **End-to-end delay**: Time from caller finishing speaking to bot audio audible to caller (includes network)
- **Processing latency**: Internal server processing time (excludes network)

**Latency Budget Breakdown:**
```
Caller stops speaking
    │
    ├── [50-100ms]  VAD silence detection (detect speech ended)
    │
    ├── [100-200ms] STT final transcript (Deepgram streaming)
    │
    ├── [150-300ms] LLM first token (Groq streaming)
    │
    ├── [100-200ms] TTS first audio chunk (local Coqui)
    │
    └── [50-100ms]  Network to caller (Plivo)
    │
    ▼
First bot audio reaches caller
```

| Metric | Target (P50) | Acceptable (P95) | Measurement |
|--------|--------------|------------------|-------------|
| Processing latency | < 500ms | < 800ms | Server-side timestamps |
| End-to-end delay | < 800ms | < 1200ms | Timestamped transcript analysis (no audio) |
| STT streaming | < 200ms | < 400ms | Deepgram callback timestamps |
| LLM first token | < 300ms | < 500ms | Groq API response timing |
| TTS first chunk | < 200ms | < 350ms | Local TTS benchmark |

**Measurement Environment:**
- Test calls from Delhi region to VPS in Mumbai/Singapore
- Measure during business hours (peak load simulation)
- Log all component latencies per call for analysis

### 6.2 Reliability
- Uptime target: 99% during business hours
- Graceful degradation if any service fails
- Automatic WhatsApp fallback for failures

### 6.3 Scalability (Future)
- MVP: Single concurrent call
- Future: Multiple concurrent calls per business
- Future: Multiple businesses on same infrastructure

---

## 7. Technical Architecture

### 7.1 Tech Stack

| Component | Technology | Rationale |
|-----------|------------|-----------|
| **LLM** | Groq (Llama 3.1 70B) | Free, fast inference |
| **STT** | Deepgram | Free tier, good Hindi support, low latency |
| **TTS** | Open Source (Coqui/Piper/XTTS) | Free, customizable, self-hosted |
| **Telephony** | Plivo | Cheaper than Twilio, good India support |
| **Backend** | Python + FastAPI | Rich AI ecosystem, async support |
| **WebSocket** | FastAPI WebSocket | Real-time audio streaming |
| **Config GUI** | Streamlit | Quick Python-based UI |
| **Database** | SQLite → PostgreSQL | Call logs, analytics |
| **Hosting** | VPS (DigitalOcean/Hetzner) | Full control, cost-effective |

### 7.2 System Architecture
```
┌─────────────────────────────────────────────────────────────────┐
│                         PLIVO                                    │
│                    (Telephony Provider)                          │
└─────────────────────┬───────────────────────────────────────────┘
                      │ WebSocket (Audio Stream)
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    VOICE BOT SERVER                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   Plivo     │  │   Audio     │  │  Session    │              │
│  │  Handler    │──│  Pipeline   │──│  Manager    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│         │                │                │                      │
│         ▼                ▼                ▼                      │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │   STT       │  │    LLM      │  │    TTS      │              │
│  │ (Deepgram)  │  │   (Groq)    │  │  (Coqui)    │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌─────────────────────────────────────────────────────────────────┐
│                    CONFIG & ADMIN                                │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │  Streamlit  │  │   SQLite    │  │   Config    │              │
│  │    GUI      │  │  (Logs/DB)  │  │   Files     │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
└─────────────────────────────────────────────────────────────────┘
```

### 7.3 Audio Pipeline Flow
```
Caller Speaks
     │
     ▼
┌─────────────┐
│ Plivo Audio │ ──── Raw audio chunks (8kHz/16kHz)
│   Stream    │
└─────────────┘
     │
     ▼
┌─────────────┐
│  Deepgram   │ ──── Streaming STT
│    STT      │ ──── Interim + Final transcripts
└─────────────┘
     │
     ▼
┌─────────────┐
│   Groq      │ ──── Context + Transcript
│    LLM      │ ──── Streaming response
└─────────────┘
     │
     ▼
┌─────────────┐
│   Coqui     │ ──── Text chunks
│    TTS      │ ──── Audio chunks (streaming)
└─────────────┘
     │
     ▼
┌─────────────┐
│ Plivo Audio │ ──── Play audio to caller
│   Stream    │
└─────────────┘
```

### 7.4 Latency Optimization Strategy
1. **Streaming everything**: STT, LLM, and TTS all stream
2. **Sentence-level TTS**: Generate audio as sentences complete, not full response
3. **Warm connections**: Keep Deepgram/Groq connections warm
4. **Local TTS**: Self-hosted TTS eliminates network latency
5. **Speculative execution**: Start TTS on partial LLM output

---

## 8. Configuration System

### 8.1 Business Configuration (per client)
```yaml
business:
  name: "Himalayan Kitchen"
  type: "restaurant"
  language:
    primary: "hindi"
    supported: ["hindi", "english", "hinglish"]
    detection: "auto"

  greeting:
    hindi: "Namaste! {business_name} mein aapka swagat hai. Main aapki kaise madad kar sakti hoon?"
    english: "Hello! Welcome to {business_name}. How may I help you?"

  voice:
    accent: "delhi_hindi"
    gender: "female"
    style: "professional"

  operating_hours:
    monday: "closed"
    tuesday: "11:00-22:30"
    # ... etc

  fallback:
    type: "whatsapp"
    number: "+91XXXXXXXXXX"
    message: "Customer needs callback: {summary}"
```

### 8.2 Menu/Services Configuration
```yaml
menu:
  categories:
    - name: "Momos"
      items:
        - name: "Veg Steam Momos"
          price: 180
          description: "Steamed vegetable dumplings"
          tags: ["vegetarian", "popular"]
        # ... etc
```

### 8.3 Streamlit Admin GUI Features
- [ ] Business profile editor
- [ ] Menu/services manager
- [ ] Operating hours configuration
- [ ] Voice settings (accent, style)
- [ ] Greeting message customization
- [ ] Fallback rules configuration
- [ ] Call logs viewer (with PII masking)
- [ ] Basic analytics dashboard
- [ ] Reservation management view

### 8.4 Admin Authentication & Security

**MVP Authentication:**
- Single admin user with environment variable credentials
- Session-based auth with Streamlit's built-in session state
- Password hashed with bcrypt, stored in `.env` (not in code)
- Session timeout: 30 minutes of inactivity

```python
# .env (not committed to git)
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<bcrypt hash>
SESSION_SECRET=<random 32-char string>
```

**Access Control (MVP - Single Tenant):**
- All authenticated users have full access
- No role-based permissions in MVP (single admin)

**Future Multi-Tenant Requirements:**
- [ ] Per-business admin accounts
- [ ] Role-based access (owner, staff, view-only)
- [ ] Tenant isolation (business A cannot see business B data)
- [ ] Audit logging for config changes

**Audit Logging (MVP):**
```sql
CREATE TABLE audit_logs (
    id TEXT PRIMARY KEY,
    timestamp TEXT DEFAULT (datetime('now')),
    action TEXT NOT NULL,  -- 'config_update', 'reservation_cancel', etc.
    admin_user TEXT,
    details TEXT,  -- JSON with before/after values
    ip_address TEXT
);
```

**Sensitive Data Handling:**
- API keys stored in environment variables only
- Config files exclude secrets (reference env vars)
- Call logs mask phone numbers in UI: `98XXXX1234` format (first 2 + last 4 digits)
- Export functions exclude PII by default

### 8.5 Reservation Rules Configuration

Business-specific reservation rules (not hard-coded):

```yaml
reservation_rules:
  # Booking constraints
  min_advance_booking_mins: 30        # Minimum time before reservation
  max_advance_booking_days: 30        # How far ahead can book
  max_phone_party_size: 10            # Larger groups need manual handling
  min_party_size: 1

  # Capacity management
  total_seats: 40
  dining_window_mins: 90              # Assumed time per table
  buffer_between_bookings_mins: 15    # Cleanup time between seatings

  # Overbooking protection
  max_concurrent_reservations: null   # null = calculated from seats
  allow_waitlist: false               # Future feature

  # Special rules
  closed_days: ["monday"]
  special_closures: []                # ["2026-01-26", "2026-08-15"]
  peak_hours: ["19:00-21:00"]         # May have stricter limits
  peak_max_party_size: 6              # Smaller groups during peak
```

**Why Configurable:**
- Different restaurants have different turnover rates
- Fine dining vs casual = different dining windows
- Some businesses want 1-hour advance, others want same-day only
- Peak hour rules vary by business

---

## 9. Data Models

**Note:** MVP uses SQLite. Schemas use SQLite-compatible types. JSON stored as TEXT and parsed in application layer.

### 9.1 Call Log Schema (SQLite)
```sql
CREATE TABLE call_logs (
    id TEXT PRIMARY KEY,  -- UUID stored as text
    business_id TEXT NOT NULL,
    caller_id_hash TEXT,  -- Salted hash for deduplication only (see 9.4)
    call_start TEXT,  -- ISO8601 timestamp
    call_end TEXT,
    duration_seconds INTEGER,
    detected_language TEXT,
    transcript TEXT,  -- JSON string, parsed in app
    extracted_info TEXT,  -- JSON string, parsed in app
    outcome TEXT CHECK(outcome IN ('resolved', 'fallback', 'dropped', 'error', 'privacy_opt_out')),
    consent_type TEXT CHECK(consent_type IN ('none', 'transcript', 'whatsapp')),
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_call_logs_business ON call_logs(business_id);
CREATE INDEX idx_call_logs_created ON call_logs(created_at);
```

### 9.2 Reservation Schema (SQLite)
```sql
CREATE TABLE reservations (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    call_log_id TEXT REFERENCES call_logs(id),
    customer_name TEXT,
    customer_phone_encrypted TEXT,  -- AES-256 encrypted, for WhatsApp (see 9.4)
    party_size INTEGER NOT NULL,
    reservation_date TEXT NOT NULL,  -- YYYY-MM-DD
    reservation_time TEXT NOT NULL,  -- HH:MM
    status TEXT CHECK(status IN ('confirmed', 'cancelled', 'completed', 'no_show')),
    whatsapp_sent INTEGER DEFAULT 0,  -- 0=no, 1=yes
    whatsapp_consent INTEGER DEFAULT 0,  -- Explicit consent captured
    notes TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_reservations_datetime ON reservations(business_id, reservation_date, reservation_time);
```

### 9.2.1 Caller Preferences Schema (for opt-out tracking)
```sql
CREATE TABLE caller_preferences (
    caller_id_hash TEXT PRIMARY KEY,  -- HMAC hash of phone (see 9.4)
    whatsapp_opt_out INTEGER DEFAULT 0,  -- 1 = caller replied STOP
    transcript_opt_out INTEGER DEFAULT 0,  -- 1 = caller said "don't record"
    first_seen TEXT,  -- First call timestamp
    last_seen TEXT,  -- Most recent call
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now'))
);
```

### 9.2.2 WhatsApp Followups Schema (for non-reservation callbacks)
```sql
CREATE TABLE whatsapp_followups (
    id TEXT PRIMARY KEY,
    business_id TEXT NOT NULL,
    call_log_id TEXT REFERENCES call_logs(id),
    customer_phone_encrypted TEXT NOT NULL,  -- AES-256-GCM encrypted
    reason TEXT,  -- 'callback_request', 'large_party', 'catering_inquiry', etc.
    summary TEXT,  -- Brief context from call
    status TEXT CHECK(status IN ('pending', 'sent', 'responded', 'expired')),
    whatsapp_consent INTEGER DEFAULT 1,  -- Must be 1 to be in this table
    sent_at TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX idx_followups_status ON whatsapp_followups(business_id, status);
```

### 9.3 Conversation Turn Schema (JSON in TEXT field)
```json
{
  "turn_id": 1,
  "speaker": "caller",
  "timestamp": "2026-02-01T14:30:00Z",
  "transcript": "Momos kitne ke hain?",
  "detected_language": "hindi",
  "intent": "menu_inquiry",
  "entities": {
    "item": "momos"
  },
  "response_latency_ms": 450
}
```

### 9.4 Phone Number Handling (Critical)

**Two different storage methods for different purposes:**

| Purpose | Method | Reversible | Field |
|---------|--------|------------|-------|
| Caller deduplication & opt-out tracking | HMAC-SHA256 with global pepper | No (without pepper) | `caller_id_hash` |
| WhatsApp delivery | AES-256-GCM encryption | Yes (with key) | `customer_phone_encrypted` |

**Why HMAC with global pepper (not per-record salt) for deduplication:**
- Per-record salts make matching impossible (can't find if caller called before)
- Global pepper (secret key) prevents rainbow tables while allowing lookups
- HMAC-SHA256 is fast enough for real-time lookup, secure with 256-bit pepper
- Pepper stored in env var, if leaked → rehash all records with new pepper

**Why NOT plain SHA-256:**
- 10-digit Indian phone numbers = only 10 billion possibilities
- Plain SHA-256 reversed via rainbow table in minutes
- HMAC with secret pepper makes precomputation infeasible

**Hashing Implementation (for deduplication):**
```python
import hmac
import hashlib
import os

# Global pepper - stored in environment, NOT in code/DB
PHONE_HASH_PEPPER = os.environ['PHONE_HASH_PEPPER'].encode()  # 32+ bytes

def hash_phone_for_dedup(phone: str) -> str:
    """
    Creates consistent hash for deduplication and opt-out tracking.
    Same phone always produces same hash (with same pepper).
    """
    normalized = phone.replace(" ", "").replace("-", "")[-10:]  # Last 10 digits
    return hmac.new(PHONE_HASH_PEPPER, normalized.encode(), hashlib.sha256).hexdigest()

def check_caller_opted_out(phone: str) -> bool:
    """Check if this caller previously opted out of WhatsApp."""
    phone_hash = hash_phone_for_dedup(phone)
    # Query: SELECT whatsapp_opt_out FROM caller_preferences WHERE caller_id_hash = ?
    return db.query_opt_out_status(phone_hash)
```

**Encryption Implementation (for WhatsApp) - AES-256-GCM:**
```python
import os
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# 32-byte key for AES-256, stored in environment
PHONE_ENCRYPTION_KEY = bytes.fromhex(os.environ['PHONE_ENCRYPTION_KEY'])  # 64 hex chars

def encrypt_phone(phone: str) -> str:
    """Encrypt phone for later WhatsApp delivery using AES-256-GCM."""
    aesgcm = AESGCM(PHONE_ENCRYPTION_KEY)
    nonce = os.urandom(12)  # 96-bit nonce for GCM
    ciphertext = aesgcm.encrypt(nonce, phone.encode(), None)
    # Store nonce + ciphertext together (base64 encoded)
    import base64
    return base64.b64encode(nonce + ciphertext).decode()

def decrypt_phone(encrypted: str) -> str:
    """Decrypt for WhatsApp delivery."""
    import base64
    data = base64.b64decode(encrypted)
    nonce, ciphertext = data[:12], data[12:]
    aesgcm = AESGCM(PHONE_ENCRYPTION_KEY)
    return aesgcm.decrypt(nonce, ciphertext, None).decode()
```

**Data Flow:**
1. Caller's number arrives via Plivo (visible during call)
2. Hash phone → check `caller_preferences` for opt-out status
3. If WhatsApp consent given → encrypt and store in `customer_phone_encrypted`
4. For deduplication → hash and store in `caller_id_hash`
5. After call ends → original plaintext number discarded from memory
6. When sending WhatsApp → decrypt `customer_phone_encrypted`, send, log success
7. After 90 days → auto-purge encrypted numbers (hash retained for opt-out tracking)

**Admin UI Masking:**
- Display: `98XXXX1234` (first 2 + last 4 digits)
- Derived from decrypted value at display time, not stored separately
- Requires admin authentication to view even masked version

---

## 10. Development Phases

### Phase 1: Foundation (Week 1)
- [ ] Project setup (Python, FastAPI, folder structure)
- [ ] Deepgram STT integration (streaming)
- [ ] Groq LLM integration (streaming)
- [ ] Basic prompt engineering for restaurant bot
- [ ] Web-based testing interface (browser mic)

### Phase 2: Voice Pipeline (Week 2)
- [ ] Open source TTS setup (Coqui/Piper evaluation)
- [ ] Hindi voice model fine-tuning/selection
- [ ] Audio pipeline integration (STT → LLM → TTS)
- [ ] Latency optimization
- [ ] Interruption handling

### Phase 3: Telephony Integration (Week 3)
- [ ] Plivo account setup
- [ ] WebSocket audio streaming with Plivo
- [ ] Real phone call testing
- [ ] Call quality optimization
- [ ] Error handling and fallbacks

### Phase 4: Config & Polish (Week 4)
- [ ] Streamlit admin GUI
- [ ] Business configuration system
- [ ] Call logging to database
- [ ] Demo preparation
- [ ] Documentation

---

## 11. Budget Breakdown

### 11.1 Monthly Costs (MVP)
| Service | Cost | Limits | Notes |
|---------|------|--------|-------|
| Groq | $0 | 14,400 req/day, 6K tokens/min | Free tier; monitor usage |
| Deepgram | $0 | 100 hrs/month | ~200 calls @ 30min avg; sufficient for MVP |
| TTS | $0 | N/A | Self-hosted open source |
| Plivo | ~$10-15 | ~500 mins inbound | Phone number ($1) + minutes |
| VPS Hosting | ~$6-12 | 2 vCPU, 4GB RAM | Hetzner CX21 or DO Basic |
| **Total** | **~$16-27/month** | | |

### 11.2 VPS Sizing Requirements
| Component | RAM | CPU | Disk |
|-----------|-----|-----|------|
| FastAPI server | 512MB | 0.5 vCPU | 1GB |
| Coqui/Piper TTS | 2GB | 1 vCPU | 2GB (models) |
| SQLite + logs | 256MB | - | 1GB |
| OS + buffer | 1GB | 0.5 vCPU | 5GB |
| **Minimum** | **4GB** | **2 vCPU** | **10GB** |

**Recommended VPS Options:**
- Hetzner CX21: €4.85/mo (2 vCPU, 4GB, 40GB) - Best value
- DigitalOcean Basic: $12/mo (2 vCPU, 4GB, 80GB) - Better support
- Contabo: ~$6/mo - Cheapest but less reliable

### 11.3 Contingency & Fallback Plans

| Risk | Trigger | Fallback | Added Cost |
|------|---------|----------|------------|
| Groq rate limit hit | >100 calls/day | Queue requests, add delay | $0 (accept slower) |
| Groq unavailable | API down >5 min | Fallback to Groq backup model | $0 |
| Deepgram limit exceeded | >100 hrs/month | Switch to Whisper via Groq | $0 (slower) |
| Open source TTS quality poor | User complaints | ElevenLabs Starter | +$5/mo |
| VPS performance issues | Latency >1.5s P95 | Upgrade to 4 vCPU/8GB | +$6/mo |
| Plivo issues | Call quality poor | Switch to Twilio | +$5/mo |

**Total Contingency Budget:** Up to $40/month if all fallbacks needed

### 11.4 One-time Setup
| Item | Cost |
|------|------|
| Domain (optional) | ~$10/year |
| Initial testing minutes | ~$5 |
| TTS model download | $0 (bandwidth only) |

---

## 12. Risks & Mitigations

| Risk | Impact | Likelihood | Mitigation |
|------|--------|------------|------------|
| Open source Hindi TTS quality poor | High | Medium | Evaluate multiple options (Coqui, Piper, XTTS), fallback to ElevenLabs |
| Latency exceeds 500ms | High | Medium | Aggressive streaming, local TTS, optimize pipeline |
| Groq rate limits | Medium | Low | Implement request queuing, consider Groq paid tier |
| Deepgram Hindi accuracy issues | Medium | Low | Fine-tune prompts, add post-processing |
| Plivo integration complexity | Medium | Low | Good documentation, community support |

---

## 13. Future Roadmap (Post-MVP)

### Version 1.1
- Multiple concurrent calls
- Call analytics dashboard
- A/B testing for prompts

### Version 1.2
- Outbound calling capability
- CRM integrations
- Multi-business deployment

### Version 2.0
- Custom voice cloning
- Appointment sync with Google Calendar
- Payment integration

---

## 14. Open Questions

1. **TTS Selection**: Need to evaluate Coqui vs Piper vs XTTS for Hindi quality
2. **Voice Training**: Can we fine-tune a Delhi Hindi voice affordably?
3. **Plivo Streaming**: Verify WebSocket streaming capabilities and latency
4. **Context Window**: How much conversation history is optimal for Groq?

---

## 15. Privacy, Consent & Compliance

### 15.1 Terminology Clarification

**Important:** "Recording" in this system means **transcript capture**, NOT audio recording.

| Term | What It Means | What We Store |
|------|---------------|---------------|
| "Call recording" | Converting speech to text transcript | Text transcript only |
| "Monitoring" | Real-time analysis for quality | Latency metrics, outcome |
| "Audio recording" | Storing actual voice audio | **NOT DONE** - never stored |

**Why no audio storage:**
- Reduces privacy risk and storage costs
- Transcript sufficient for quality analysis
- Compliant with data minimization principles

### 15.2 Consent Types & Flows

**Three consent levels:**

| Level | Trigger | What's Stored | Can Undo |
|-------|---------|---------------|----------|
| **None** | Caller hangs up immediately | Nothing | N/A |
| **Transcript** | Caller continues after greeting | Transcript + metadata | Yes (deletion request) |
| **WhatsApp** | Caller provides phone for confirmation | Above + encrypted phone | Yes (deletion request) |

**Greeting (Transcript Consent):**
```
Bot: "Namaste! Himalayan Kitchen mein aapka swagat hai.
      Yeh call service improvement ke liye transcribe ho sakti hai.
      Main aapki kaise madad kar sakti hoon?"
```
*Note: Uses "transcribe" not "record" to be accurate.*

**Consent Handling:**
| Caller Response | Action | consent_type |
|-----------------|--------|--------------|
| Continues with query | Implied transcript consent | `transcript` |
| "Don't record" / "Transcribe mat karo" | Store metadata only, no transcript | `none` |
| Provides phone for WhatsApp | Transcript + WhatsApp consent | `whatsapp` |
| Hangs up before speaking | Nothing stored | N/A |

**What "Don't Record" Actually Does:**
- Transcript: NOT stored
- Extracted entities (name, party size): NOT stored
- Call happened: YES stored (call_start, call_end, duration, outcome=`privacy_opt_out`)
- Functionality: Full service continues (booking works, just not logged in detail)

**Latency Measurement (Section 6.1 reference):**
- "Call recording analysis" in latency measurement refers to **timestamped transcript analysis**
- No audio files are involved
- Timestamps embedded in transcript turns enable latency calculation

### 15.3 Data Handling & Retention

| Data Type | Storage | Retention | Deletion |
|-----------|---------|-----------|----------|
| Call transcripts | SQLite (encrypted at rest) | 90 days | Auto-purge via cron |
| Caller ID hash | HMAC-SHA256 with pepper (see Section 9.4) | Indefinite | Retained for opt-out tracking |
| Phone for WhatsApp | AES-256-GCM encrypted (see Section 9.4) | 90 days | Auto-purge or on request |
| Caller preferences | SQLite (opt-out flags) | Indefinite | On explicit request only |
| Reservation data | SQLite | 1 year | Manual or on request |
| Audio recordings | **NOT STORED** | N/A | N/A |
| Analytics (aggregated) | SQLite | Indefinite | Anonymized, no PII |

### 15.4 Caller Rights

**Right to Deletion:**
- Caller can request deletion via WhatsApp follow-up
- Admin can purge specific call records
- Provide deletion confirmation within 48 hours

**Right to Access:**
- If caller requests "what data do you have on me":
  - Bot: "Aap humein WhatsApp pe message karein, hum aapko details bhej denge"
  - Manual process for MVP (no self-service portal)

### 15.5 WhatsApp Handoff Compliance

**Prerequisites for sending WhatsApp:**
1. Caller explicitly provided their number during the call (not from caller ID)
2. Caller was informed it's for WhatsApp confirmation
3. `whatsapp_consent` = 1 in database

**Message Template:**
```
Himalayan Kitchen: Aapki booking confirm hui -
[Date] ko [Time] baje, [Party Size] logon ke liye.
Questions? Call us at [Number].
Reply STOP to opt out.
```

**Opt-out Handling:**
- If caller replies "STOP" → set `whatsapp_opt_out = 1` in `caller_preferences`, delete encrypted phone
- Future calls from same number → check `caller_preferences` via `caller_id_hash`, skip WhatsApp offer
- Opt-out persists indefinitely (hash retained even after 90-day transcript purge)

### 15.6 Security Measures

| Measure | Implementation |
|---------|----------------|
| Data at rest | SQLite with filesystem encryption (LUKS on VPS) |
| Phone encryption | AES-256-GCM with 12-byte nonce, key in env var (see Section 9.4) |
| Caller ID hashing | HMAC-SHA256 with global pepper (see Section 9.4) |
| Data in transit | TLS 1.3 for all API calls |
| API keys | Environment variables, not in code |
| Admin access | Password + session timeout |
| Logs | No PII in application logs |
| Backups | Encrypted, stored separately |

### 15.7 Compliance Checklist (MVP)

- [ ] Consent announcement in greeting (uses "transcribe" not "record")
- [ ] HMAC-SHA256 phone hashing with global pepper (not plain SHA-256)
- [ ] AES-256-GCM phone encryption for WhatsApp numbers
- [ ] 90-day auto-purge script configured (transcripts + encrypted phones)
- [ ] WhatsApp opt-out mechanism ready (STOP handling via `caller_preferences`)
- [ ] Admin panel masks phone numbers (`98XXXX1234` format)
- [ ] No audio files stored (transcript only)
- [ ] `.env` excluded from git
- [ ] `PHONE_ENCRYPTION_KEY` (64 hex chars) in environment
- [ ] `PHONE_HASH_PEPPER` (32+ bytes) in environment
- [ ] VPS disk encryption enabled (LUKS)

---

## 16. Appendix

### A. Sample Prompts

#### System Prompt (Restaurant Bot)
```
You are a friendly female voice assistant for Himalayan Kitchen, an Indian Tibetan restaurant in Delhi.

PERSONALITY:
- Warm, professional, helpful
- Speaks naturally in Hindi/Hinglish/English based on caller
- Uses "ji" and polite forms appropriately
- Keeps responses concise (1-2 sentences typically)

CAPABILITIES:
- Answer menu questions (prices, ingredients, recommendations)
- Provide restaurant timings and location
- Book table reservations (MUST check availability first)
- Handle basic complaints with empathy

LIMITATIONS:
- Cannot process payments
- Cannot modify existing reservations (handoff to WhatsApp)
- Cannot provide detailed recipes
- Cannot take delivery/takeaway orders (dine-in only)

RESERVATION RULES:
- Always check: Is the day valid? (closed Monday)
- Always check: Is time within 11:00-22:30?
- Always check: Is party size ≤10? (larger needs manual handling)
- Always confirm: date, time, party size, name before booking

When you cannot help, offer to have someone call back via WhatsApp.

CURRENT CONTEXT:
{business_config}
{menu_data}
{current_datetime}
{available_capacity}
```

### B. Test Scenarios (With Pass/Fail Criteria)

| # | Scenario | Input | Expected Output | Pass Criteria |
|---|----------|-------|-----------------|---------------|
| 1 | Happy path booking | "4 logon ke liye aaj 8 baje" | Booking confirmed | Correct date/time/size in DB |
| 2 | Closed day rejection | "Monday ko book karo" | Polite rejection + alternatives | No booking created |
| 3 | Outside hours | "Subah 9 baje" | Rejection with hours info | No booking created |
| 4 | Capacity full | (When slots full) | Alternative times offered | No overbooking |
| 5 | Party size correction | "4 log... actually 6" | Updated to 6 | Final booking = 6 |
| 6 | Language switch | Start English, switch Hindi | Bot follows | Response in Hindi |
| 7 | Interruption | Bot speaking, caller asks question | Bot stops, answers | TTS stops < 100ms, response P50 < 500ms |
| 8 | Menu query | "Chicken momos kitne ke hain?" | "₹220" | Correct price |
| 9 | Unknown query | "Catering karte ho?" | Handoff to WhatsApp | Graceful fallback |
| 10 | Large party | "20 logon ke liye" | Handoff for manual booking | No auto-booking |

### C. Latency Measurement Script
```python
# tools/measure_latency.py
import time
from datetime import datetime

def measure_turn_latency(call_session):
    """
    Measures end-to-end latency for a conversation turn.
    Timestamps:
    - t0: Last audio chunk from caller received
    - t1: STT final transcript received
    - t2: LLM first token received
    - t3: TTS first audio chunk generated
    - t4: First audio byte sent to Plivo
    """
    metrics = {
        'stt_latency': t1 - t0,
        'llm_latency': t2 - t1,
        'tts_latency': t3 - t2,
        'network_latency': t4 - t3,
        'total_processing': t3 - t0,
        'total_e2e': t4 - t0,
    }
    return metrics
```

---

*Document maintained by: Pronav*
*Last updated: February 1, 2026*
*Version: 1.2 - Fixed crypto specs (AES-256-GCM, HMAC-SHA256), added caller_preferences and whatsapp_followups schemas, aligned consent flows*
