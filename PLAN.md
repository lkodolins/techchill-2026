# ForgeChannels — Hackathon Build Plan

> Salesforge owns email. ForgeChannels adds every other channel on top.
> GDPR-compliant, whitelabelable, AI-personalized multi-channel outreach.

---

## What We're Building

A plug-in orchestration layer for Salesforge that:
1. Takes a CSV of contacts (or accepts them via Salesforge webhook)
2. Detects which outreach channels each contact is reachable on (Slack, LinkedIn, Email)
3. Scores and selects the optimal channel per contact
4. Uses Claude AI to generate a personalized message tuned to that channel's norms
5. Shows a live dashboard with previews, then launches with one click
6. Tracks GDPR consent, opt-outs, and data retention automatically

**Demo flow (48h goal):**
Upload CSV → Detect channels → AI writes messages → Preview dashboard → Launch sequence

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TailwindCSS + shadcn/ui | Fast to build, beautiful out of the box |
| Backend | Python FastAPI | Best async support, minimal boilerplate |
| Database | PostgreSQL via Supabase (free tier) | Instant setup, built-in realtime websockets |
| Queue | Redis + RQ | Simple background jobs, no infra overhead |
| AI | Anthropic Claude API (`claude-sonnet-4-6`) | Best quality, structured JSON output |
| LinkedIn lookup | Proxycurl API | Email → LinkedIn profile match |
| M365 detection | Microsoft Graph API | Check if email is an active Outlook/M365 user |
| Slack detection | Slack Web API | Check workspace membership by email |
| Containers | Docker Compose | Local dev only |

---

## Folder Structure

```
forgechannels/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/                     # shadcn/ui primitives
│   │   │   ├── ContactTable.tsx        # contact list with channel badges
│   │   │   ├── ChannelBadge.tsx        # colored icon per channel
│   │   │   ├── MessagePreviewCard.tsx  # AI message previews
│   │   │   ├── SequenceLauncher.tsx    # one-click launch button
│   │   │   └── StatusFeed.tsx          # realtime event stream
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx           # main view
│   │   │   ├── Upload.tsx              # drag-and-drop CSV
│   │   │   └── Settings.tsx            # whitelabel config
│   │   ├── hooks/
│   │   │   ├── useContacts.ts
│   │   │   ├── useChannelDetection.ts
│   │   │   └── useRealtime.ts          # Supabase realtime
│   │   ├── lib/
│   │   │   ├── api.ts                  # typed API client
│   │   │   ├── theme.ts                # CSS var injection for whitelabel
│   │   │   └── supabase.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── public/logo.svg
│   ├── index.html
│   ├── tailwind.config.ts
│   └── vite.config.ts
│
├── backend/
│   ├── app/
│   │   ├── api/routes/
│   │   │   ├── contacts.py             # CRUD + CSV import
│   │   │   ├── sequences.py            # sequence management
│   │   │   ├── channels.py             # detection trigger
│   │   │   ├── messages.py             # AI message gen
│   │   │   ├── gdpr.py                 # opt-out, consent, erasure
│   │   │   └── webhooks.py             # Salesforge inbound
│   │   ├── api/deps.py                 # FastAPI DI
│   │   ├── core/
│   │   │   ├── config.py               # pydantic-settings env vars
│   │   │   ├── auth.py                 # X-API-Key middleware
│   │   │   └── database.py             # SQLAlchemy async
│   │   ├── services/
│   │   │   ├── channel_detector.py     # scoring orchestrator
│   │   │   ├── graph_service.py        # Microsoft Graph calls
│   │   │   ├── linkedin_service.py     # Proxycurl calls
│   │   │   ├── slack_service.py        # Slack Web API calls
│   │   │   ├── ai_service.py           # Claude API calls
│   │   │   ├── gdpr_service.py         # consent/opt-out logic
│   │   │   └── queue_service.py        # RQ job enqueue
│   │   ├── models/
│   │   │   ├── contact.py
│   │   │   ├── sequence.py
│   │   │   ├── channel_profile.py
│   │   │   ├── message.py
│   │   │   └── gdpr_log.py
│   │   ├── workers/
│   │   │   ├── detection_worker.py     # runs channel detection jobs
│   │   │   └── message_worker.py       # runs AI generation jobs
│   │   ├── prompts/
│   │   │   ├── email.py
│   │   │   ├── linkedin.py
│   │   │   └── slack.py
│   │   └── main.py
│   ├── migrations/
│   ├── requirements.txt
│   └── Dockerfile
│
├── shared/types/                       # shared TS types
├── docker-compose.yml
├── .env.example
└── README.md
```

---

## Database Schema

```sql
-- Tenants (whitelabel clients, e.g. Salesforge)
CREATE TABLE tenants (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  name        TEXT NOT NULL,
  api_key     TEXT UNIQUE NOT NULL,
  theme       JSONB DEFAULT '{}',   -- { primaryColor, logoUrl, companyName, domain }
  created_at  TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts imported via CSV or Salesforge webhook
CREATE TABLE contacts (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id    UUID REFERENCES tenants(id),
  email        TEXT NOT NULL,
  first_name   TEXT,
  last_name    TEXT,
  company      TEXT,
  title        TEXT,
  raw_csv_data JSONB,
  created_at   TIMESTAMPTZ DEFAULT NOW(),
  UNIQUE(tenant_id, email)
);

-- Channel detection results per contact
CREATE TABLE channel_profiles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id          UUID REFERENCES contacts(id),
  channel             TEXT NOT NULL,          -- 'email' | 'linkedin' | 'slack'
  reachable           BOOLEAN DEFAULT FALSE,
  confidence_score    FLOAT,                  -- 0.0–1.0
  weighted_score      FLOAT,                  -- confidence × channel_weight
  channel_identifier  TEXT,                   -- email addr / linkedin URL / slack user ID
  detected_at         TIMESTAMPTZ DEFAULT NOW(),
  raw_api_response    JSONB
);

-- Outreach sequences
CREATE TABLE sequences (
  id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  tenant_id  UUID REFERENCES tenants(id),
  name       TEXT NOT NULL,
  status     TEXT DEFAULT 'draft',            -- draft | active | paused | completed
  created_at TIMESTAMPTZ DEFAULT NOW()
);

-- Contacts enrolled in a sequence
CREATE TABLE sequence_contacts (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sequence_id      UUID REFERENCES sequences(id),
  contact_id       UUID REFERENCES contacts(id),
  assigned_channel TEXT,                      -- winning channel
  status           TEXT DEFAULT 'pending',    -- pending | sent | replied | bounced | opted_out
  scheduled_at     TIMESTAMPTZ,
  sent_at          TIMESTAMPTZ
);

-- AI-generated messages
CREATE TABLE messages (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  sequence_contact_id   UUID REFERENCES sequence_contacts(id),
  channel               TEXT NOT NULL,
  subject               TEXT,                 -- email only
  body                  TEXT NOT NULL,
  generated_at          TIMESTAMPTZ DEFAULT NOW(),
  approved              BOOLEAN DEFAULT FALSE,
  sent                  BOOLEAN DEFAULT FALSE
);

-- GDPR audit trail
CREATE TABLE gdpr_logs (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id  UUID REFERENCES contacts(id),
  event_type  TEXT NOT NULL,  -- 'opt_out' | 'consent_recorded' | 'data_deleted' | 'legitimate_interest'
  channel     TEXT,
  basis       TEXT,           -- legal basis description
  ip_address  TEXT,
  timestamp   TIMESTAMPTZ DEFAULT NOW(),
  metadata    JSONB
);

CREATE TABLE opt_outs (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id    UUID REFERENCES contacts(id),
  channel       TEXT,                         -- NULL = all channels
  opted_out_at  TIMESTAMPTZ DEFAULT NOW(),
  method        TEXT                          -- 'link' | 'api' | 'manual'
);
```

---

## API Endpoints

```
# Contacts
POST   /api/contacts/import-csv            Upload CSV → returns job_id
GET    /api/contacts                       List all contacts for tenant
GET    /api/contacts/{id}
DELETE /api/contacts/{id}                  Triggers GDPR deletion

# Channel Detection
POST   /api/channels/detect/{contact_id}   Enqueue detection for one contact
POST   /api/channels/detect-batch          Enqueue for all contacts in sequence
GET    /api/channels/status/{job_id}       Poll job status
GET    /api/contacts/{id}/channels         Get detection results

# AI Messages
POST   /api/messages/generate/{contact_id} Generate for contact's winning channel
POST   /api/messages/generate-batch        Generate for all contacts in sequence
GET    /api/messages/{contact_id}
PUT    /api/messages/{id}/approve

# Sequences
POST   /api/sequences
GET    /api/sequences
POST   /api/sequences/{id}/launch          One-click launch
GET    /api/sequences/{id}/status

# GDPR
POST   /api/gdpr/opt-out
GET    /api/gdpr/contact/{id}              Audit log for one contact
POST   /api/gdpr/delete/{id}               Right to erasure
GET    /api/gdpr/export/{id}               Data export

# Salesforge Webhooks (inbound)
POST   /webhooks/salesforge/contact        Contact pushed from Salesforge
POST   /webhooks/salesforge/sequence       Sequence trigger from Salesforge

# Whitelabel
GET    /api/tenant/theme
PUT    /api/tenant/theme
```

---

## Channel Detection Algorithm

**Principle:** Run all 3 detections in parallel, score each by `channel_weight × confidence`, sort descending, pick winner.

```python
CHANNEL_WEIGHTS = {
    "slack":    0.40,   # strongest intent signal: community context, async
    "linkedin": 0.35,   # strong professional signal
    "email":    0.25,   # always reachable, lowest differentiation
}

async def detect_channels(contact) -> list[ChannelScore]:
    # Run all lookups concurrently
    graph_result, li_result, slack_result = await asyncio.gather(
        graph_service.lookup_user(contact.email),
        linkedin_service.find_by_email(contact.email),
        slack_service.find_member(contact.email),
    )

    scores = []

    # Email — always reachable; boost if M365 active
    email_conf = 0.85 if graph_result.found else 0.60
    scores.append(ChannelScore("email", True, email_conf, contact.email))

    # LinkedIn
    if li_result.found:
        scores.append(ChannelScore("linkedin", True, li_result.confidence, li_result.profile_url))

    # Slack — highest signal if present
    if slack_result.found:
        scores.append(ChannelScore("slack", True, 0.95, slack_result.user_id))

    for s in scores:
        s.weighted_score = CHANNEL_WEIGHTS[s.channel] * s.confidence

    return sorted(scores, key=lambda x: x.weighted_score, reverse=True)
```

**Fallback chain:** Slack → LinkedIn → M365 Email → Basic Email

---

## AI Prompt Templates

### Email (80–120 words, JSON output)
```
SYSTEM: You are an expert B2B sales copywriter. Write a cold outreach email.
Tone: Professional, concise, consultative. NOT salesy.
Length: 80-120 words body. Clear subject line.
Structure: personalized opener → value prop (1-2 sentences) → soft CTA.
Output JSON: {"subject": "...", "body": "..."}

USER:
Contact: {first_name} {last_name}, {title} at {company}
Signal: {signal}
Sender: {sender_name} from {sender_company}
Value prop: {value_prop}
```

### LinkedIn (max 300 chars, connection request)
```
SYSTEM: You write LinkedIn connection request messages.
Tone: Warm, human, peer-to-peer. Never corporate.
Length: MAX 300 characters.
No pitch. Curiosity hook + reason to connect.
Output JSON: {"body": "..."}

USER:
Contact: {first_name}, {title} at {company}
Signal: {signal}
Shared context: {shared_context}
```

### Slack (2-3 sentences, community DM)
```
SYSTEM: You write Slack DMs for community outreach.
Tone: Conversational, community-member-to-community-member. Never a pitch.
Length: 2-3 short sentences. Casual. Max 1 emoji.
Open with something community-specific.
Output JSON: {"body": "..."}

USER:
Contact: {first_name}, {title} at {company}
Slack workspace: {workspace_name}
Their context: {signal}
Shared interest: {shared_interest}
```

---

## GDPR Compliance Design

| Requirement | Implementation |
|---|---|
| Lawful basis | Legitimate interest logged per contact at CSV import time |
| Opt-out | `opt_outs` table; checked before every send job |
| Right to erasure | Cascade delete contact + profiles + messages; gdpr_log tombstone retained |
| Audit trail | All events written to `gdpr_logs` with timestamp + IP |
| Data retention | Cron deletes inactive contacts after 24 months (configurable per tenant) |
| Opt-out link | Appended to every generated message automatically |

---

## Whitelabel System

Theme stored as JSONB per tenant:
```json
{
  "primaryColor": "#6366f1",
  "logoUrl": "https://...",
  "companyName": "Salesforge",
  "domain": "channels.salesforge.ai",
  "fontFamily": "Inter"
}
```

On frontend load: fetch `/api/tenant/theme` → inject as CSS variables into `:root` → shadcn/ui picks them up automatically. Logo swapped via `theme.logoUrl`. Live preview in Settings page.

---

## Salesforge Webhook Payloads

```json
// POST /webhooks/salesforge/contact
{
  "event": "contact.created",
  "api_key": "sf_...",
  "contact": { "email": "...", "firstName": "...", "lastName": "...", "company": "...", "title": "..." }
}

// POST /webhooks/salesforge/sequence
{
  "event": "sequence.triggered",
  "api_key": "sf_...",
  "sequence_id": "...",
  "contact_ids": ["...", "..."]
}
```

---

## Docker Compose

```yaml
services:
  backend:
    build: ./backend
    ports: ["8000:8000"]
    env_file: .env
    depends_on: [redis]

  worker:
    build: ./backend
    command: rq worker --with-scheduler
    env_file: .env
    depends_on: [redis]

  frontend:
    build: ./frontend
    ports: ["5173:5173"]
    env_file: .env

  redis:
    image: redis:7-alpine
    ports: ["6379:6379"]
```

PostgreSQL is hosted on Supabase — no local container required.

---

## Environment Variables

```bash
# Supabase
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_KEY=
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/db

# AI
ANTHROPIC_API_KEY=

# Channel APIs
PROXYCURL_API_KEY=           # LinkedIn email → profile
MICROSOFT_CLIENT_ID=
MICROSOFT_CLIENT_SECRET=
SLACK_BOT_TOKEN=

# App
API_KEY_SECRET=
REDIS_URL=redis://localhost:6379

# Frontend (Vite)
VITE_API_URL=http://localhost:8000
VITE_SUPABASE_URL=
VITE_SUPABASE_ANON_KEY=
```

---

## Key Libraries

| Purpose | Library |
|---|---|
| Async HTTP (backend) | `httpx` |
| Job queue | `rq` + `redis` |
| ORM + migrations | `sqlalchemy[asyncio]` + `alembic` |
| Env config | `pydantic-settings` |
| CSV parsing | `pandas` |
| Charts | `recharts` |
| Data tables | `@tanstack/react-table` |
| Icons | `lucide-react` |
| Toast / notifications | `sonner` |
| File upload | `react-dropzone` |

---

## 48h Build Order

### Hours 0–4: Foundation
- [ ] Supabase project + run schema SQL
- [ ] FastAPI scaffold: `main.py`, auth middleware, `/health`
- [ ] Vite + React + Tailwind + shadcn/ui scaffold
- [ ] Docker Compose wired

### Hours 4–10: CSV Import + Contact Display
- [ ] `POST /api/contacts/import-csv`
- [ ] Upload page (drag-and-drop)
- [ ] Contact table with status columns

### Hours 10–18: Channel Detection ← *Core demo value*
- [ ] Proxycurl (LinkedIn) integration — most visual impact
- [ ] Mock Microsoft Graph + Slack (realistic fallbacks for demo)
- [ ] Scoring algorithm
- [ ] RQ worker queue
- [ ] Supabase Realtime → frontend badge updates live
- [ ] Channel badge UI (colored icons)

### Hours 18–28: AI Message Generation ← *Second biggest wow*
- [ ] Claude API + all 3 prompt templates
- [ ] Hardcode 2–3 realistic signals per demo contact
- [ ] `POST /api/messages/generate-batch`
- [ ] Message preview cards (side-by-side channel comparison)
- [ ] Approve/edit inline

### Hours 28–36: Sequence Launch + Dashboard
- [ ] "Launch Sequence" button
- [ ] Sequence status tracking
- [ ] Channel breakdown pie chart (recharts)
- [ ] Realtime status feed

### Hours 36–42: GDPR + Whitelabel
- [ ] Opt-out endpoint + unsubscribe page
- [ ] CSS var theme engine + live preview
- [ ] Salesforge webhook endpoint

### Hours 42–48: Polish + Demo Prep
- [ ] 10 realistic demo contacts with good signals seeded
- [ ] Demo script rehearsed
- [ ] Mobile responsive cleanup
- [ ] README + `.env.example` finalized
- [ ] Fallback demo video recorded

---

## Demo Script (for judges)

1. Open `http://localhost:5173`
2. Drag in `demo_contacts.csv`
3. Click **Detect Channels** → watch badges populate in realtime (Slack/LinkedIn/Email icons)
4. Click **Generate Messages** → Claude writes personalized messages per contact
5. Show message preview cards — different tone per channel, same contact
6. Click **Launch Sequence** → status feed shows sent events
7. Switch to GDPR tab → show legitimate interest log, opt-out trail
8. Switch to Settings → swap logo + primary color → UI rebrands live
