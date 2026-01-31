# /model - Database Models & Schema Generation

## Context

You are working on **Vartalaap**, a voice bot platform for local Indian businesses.

**Tech Stack Reference:** `docs/TECH_STACK.md` (Section 3, 18)
**PRD Reference:** `docs/PRD.md` (Section 9 - Data Models)

## Stack Summary

- **ORM:** SQLModel 0.0.22+ (Pydantic + SQLAlchemy)
- **Database:** SQLite (MVP), PostgreSQL upgrade path
- **Migrations:** Alembic 1.14.x (auto-generate from models)
- **Async Driver:** aiosqlite 0.20.x
- **Schema Generation:** datamodel-code-generator (JSON Schema → Pydantic)

## Schema-First Workflow

```
┌─────────────────────────────────────────────────────────────────┐
│  1. Define JSON Schema    →   schemas/reservation.json          │
│  2. Generate Pydantic     →   src/schemas/reservation.py        │
│  3. Extend to SQLModel    →   src/db/models.py                  │
│  4. Generate Migration    →   migrations/versions/*.py          │
└─────────────────────────────────────────────────────────────────┘
```

## File Structure

```
schemas/                         # JSON Schema (SOURCE OF TRUTH)
├── call_log.json
├── reservation.json
├── caller_preferences.json
├── whatsapp_followup.json
└── conversation_turn.json

src/schemas/                     # Generated Pydantic (DO NOT EDIT)
├── __init__.py
├── _generated.py               # Marker file
├── call_log.py
├── reservation.py
└── ...

src/db/
├── models.py                   # SQLModel tables (extend generated)
├── session.py                  # Async session factory
└── repositories/               # Data access layer
    ├── calls.py
    └── reservations.py

migrations/
├── alembic.ini
├── env.py
└── versions/                   # Auto-generated migrations
```

## Step 1: Create JSON Schema

**Location:** `schemas/<entity>.json`

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "Reservation",
  "description": "Restaurant table reservation",
  "type": "object",
  "required": ["business_id", "party_size", "reservation_date", "reservation_time"],
  "properties": {
    "id": {
      "type": "string",
      "format": "uuid",
      "description": "Unique identifier"
    },
    "business_id": {
      "type": "string"
    },
    "party_size": {
      "type": "integer",
      "minimum": 1,
      "maximum": 20
    },
    "reservation_date": {
      "type": "string",
      "format": "date"
    },
    "reservation_time": {
      "type": "string",
      "pattern": "^([01]?[0-9]|2[0-3]):[0-5][0-9]$"
    },
    "status": {
      "type": "string",
      "enum": ["confirmed", "cancelled", "completed", "no_show"],
      "default": "confirmed"
    },
    "created_at": {
      "type": "string",
      "format": "date-time"
    }
  }
}
```

### JSON Schema Tips

| JSON Schema Type | Python Type | Notes |
|------------------|-------------|-------|
| `"type": "string"` | `str` | |
| `"type": "integer"` | `int` | |
| `"type": "boolean"` | `bool` | |
| `"format": "uuid"` | `UUID` | |
| `"format": "date"` | `date` | |
| `"format": "date-time"` | `datetime` | |
| `"enum": [...]` | `Enum` | Auto-generates Python Enum |
| `"default": value` | Default value | |
| `"minimum"/"maximum"` | `Field(ge=, le=)` | |
| `"maxLength"` | `Field(max_length=)` | |
| `"pattern"` | `Field(pattern=)` | Regex validation |

## Step 2: Generate Pydantic

**Command:**
```bash
./scripts/generate.sh
# Or manually:
uv run datamodel-codegen \
    --input schemas/reservation.json \
    --output src/schemas/reservation.py \
    --output-model-type pydantic_v2.BaseModel \
    --use-annotated \
    --field-constraints \
    --target-python-version 3.12
```

**Generated Output:** `src/schemas/reservation.py`
```python
# AUTO-GENERATED - DO NOT EDIT
from datetime import date, datetime
from enum import Enum
from typing import Annotated
from uuid import UUID
from pydantic import BaseModel, Field

class ReservationStatus(str, Enum):
    confirmed = "confirmed"
    cancelled = "cancelled"
    completed = "completed"
    no_show = "no_show"

class Reservation(BaseModel):
    """Restaurant table reservation"""
    id: UUID | None = None
    business_id: str
    party_size: Annotated[int, Field(ge=1, le=20)]
    reservation_date: date
    reservation_time: Annotated[str, Field(pattern=r"^([01]?[0-9]|2[0-3]):[0-5][0-9]$")]
    status: ReservationStatus = ReservationStatus.confirmed
    created_at: datetime | None = None
```

## Step 3: Extend to SQLModel

**Location:** `src/db/models.py`

```python
from sqlmodel import SQLModel, Field
from src.schemas.reservation import Reservation as ReservationSchema, ReservationStatus
from uuid import uuid4
from datetime import datetime

class Reservation(ReservationSchema, SQLModel, table=True):
    """SQLModel table extending generated Pydantic schema."""
    __tablename__ = "reservations"

    # Override id to be primary key with auto-generation
    id: str = Field(default_factory=lambda: str(uuid4()), primary_key=True)

    # SQLite-specific: TEXT for timestamps with defaults
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Add indexes (not expressible in JSON Schema)
    class Config:
        # Indexes defined in Alembic migration
        pass
```

### SQLite Compatibility Notes

| SQLModel Type | SQLite Storage | Notes |
|---------------|----------------|-------|
| `str` | TEXT | |
| `int` | INTEGER | |
| `bool` | INTEGER | 0/1 |
| `datetime` | TEXT | ISO8601 format |
| `date` | TEXT | YYYY-MM-DD |
| `UUID` | TEXT | Store as string |
| `dict/list` | TEXT | JSON serialized |

## Step 4: Generate Migration

**Command:**
```bash
uv run alembic revision --autogenerate -m "add reservation table"
```

**Review and apply:**
```bash
# Review generated migration
cat migrations/versions/*_add_reservation_table.py

# Apply migration
uv run alembic upgrade head
```

### Migration Template
```python
# migrations/versions/xxxx_add_reservation_table.py
from alembic import op
import sqlalchemy as sa

def upgrade():
    op.create_table(
        'reservations',
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('business_id', sa.Text(), nullable=False),
        sa.Column('party_size', sa.Integer(), nullable=False),
        # ...
    )
    op.create_index('idx_reservations_datetime', 'reservations',
                    ['business_id', 'reservation_date', 'reservation_time'])

def downgrade():
    op.drop_table('reservations')
```

## Current Data Models (from PRD Section 9)

| Table | Purpose | Key Fields |
|-------|---------|------------|
| `call_logs` | Call records | id, business_id, caller_id_hash, transcript, outcome |
| `reservations` | Table bookings | id, party_size, date, time, status, phone_encrypted |
| `caller_preferences` | Opt-out tracking | caller_id_hash (PK), whatsapp_opt_out |
| `whatsapp_followups` | Callback requests | id, phone_encrypted, reason, status |
| `audit_logs` | Admin actions | id, action, admin_user, details |

## Phone Number Handling

**CRITICAL:** See PRD Section 9.4

| Field | Storage | Purpose |
|-------|---------|---------|
| `caller_id_hash` | HMAC-SHA256 | Deduplication, opt-out lookup |
| `customer_phone_encrypted` | AES-256-GCM | WhatsApp delivery |

```python
# In models.py - phone fields are just strings (encrypted/hashed externally)
caller_id_hash: str | None = Field(default=None, index=True)
customer_phone_encrypted: str | None = None  # Encrypted by crypto.py
```

## Repository Pattern

```python
# src/db/repositories/reservations.py
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

class ReservationRepository:
    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_by_id(self, id: str) -> Reservation | None:
        return await self.session.get(Reservation, id)

    async def get_by_date_range(
        self, business_id: str, start: date, end: date
    ) -> list[Reservation]:
        stmt = select(Reservation).where(
            Reservation.business_id == business_id,
            Reservation.reservation_date >= start,
            Reservation.reservation_date <= end,
            Reservation.status == "confirmed",
        )
        result = await self.session.exec(stmt)
        return result.all()

    async def check_availability(
        self, business_id: str, date: str, time: str, party_size: int
    ) -> bool:
        """Check availability per PRD Section 8.5 rules."""
        # Implementation follows business rules
        pass
```

## Commands Summary

```bash
# Generate Pydantic from JSON Schema
./scripts/generate.sh

# Create new migration after model changes
uv run alembic revision --autogenerate -m "description"

# Apply migrations
uv run alembic upgrade head

# Rollback last migration
uv run alembic downgrade -1

# Show current migration state
uv run alembic current

# Generate ER diagram
uv run python -c "from eralchemy2 import render_er; from src.db.models import SQLModel; render_er(SQLModel.metadata, 'docs/er_diagram.png')"
```

## Checklist for New Entity

- [ ] JSON Schema created in `schemas/<entity>.json`
- [ ] `./scripts/generate.sh` run
- [ ] SQLModel class added to `src/db/models.py`
- [ ] Alembic migration generated and reviewed
- [ ] Migration applied to dev database
- [ ] Repository class created in `src/db/repositories/`
- [ ] Indexes added for query patterns
