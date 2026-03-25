# ForgeChannels — Hackathon Build Plan

> Salesforge owns email. ForgeChannels owns the inbox everyone forgot about.
> Cold outreach via Google Chat, Microsoft Teams, and Slack — the three most
> untapped B2B messaging channels. GDPR-compliant, whitelabelable, AI-personalized.

---

## What We're Building

A plug-in orchestration layer for Salesforge that:
1. Takes a CSV of contacts (or accepts them via Salesforge webhook)
2. Detects which untapped chat channel each contact is reachable on (Google Chat, Teams, Slack)
3. Scores and selects the optimal channel per contact
4. Uses Claude AI to generate a personalized message tuned to that channel's norms and constraints
5. Shows a live dashboard with previews, then launches with one click
6. Tracks GDPR consent, opt-outs, and data retention automatically

**The core insight:**
- Email inboxes: saturated, spam-filtered, ignored
- LinkedIn: everyone's doing it, connection limits, message requests buried
- Google Chat / Teams / Slack: near-zero cold outreach today, native to how people work, no promotional tab

**Demo flow (48h goal):**
Upload CSV → Detect chat channels → AI writes channel-native messages → Preview dashboard → Launch sequence

---

## Channel Strategy

### Google Chat
- **Mechanism:** External messaging via Google Workspace (admin must enable)
- **Detection:** Attempt DM initiation via Google Chat API — success = external messaging open
- **Constraint:** Rolling out tighter controls (Dec 2025 update) — filter to orgs where it's confirmed open
- **Tone:** Professional but conversational. Short. Feels like an internal ping.
- **Best for:** Startups, tech-forward SMBs on Google Workspace

### Microsoft Teams
- **Mechanism:** External access via Teams federation (enabled by default in many M365 tenants)
- **Detection:** Microsoft Graph API — check if email is an active M365 user + whether Teams external access is on
- **Constraint:** Large enterprise IT teams often restrict it; SMB and mid-market most open
- **Tone:** More formal than Slack, shorter than email. Subject-line style opener.
- **Best for:** Mid-market and enterprise M365 orgs

### Slack
- **Mechanism:** Slack Connect (cross-org DMs) OR outreach via public/open communities
- **Detection:** Slack Web API — check if email maps to a Slack user in known workspaces; community membership check
- **Constraint:** Slack ToS prohibits bulk cold DMs via API — focus on community-based outreach and warm Slack Connect requests
- **Tone:** Fully casual. Community-aware. One emoji max. Never a pitch.
- **Best for:** Tech, SaaS, developer, growth, marketing personas

---

## Tech Stack

| Layer | Choice | Why |
|---|---|---|
| Frontend | React + Vite + TailwindCSS + shadcn/ui | Fast to build, beautiful out of the box |
| Backend | Python FastAPI | Best async support, minimal boilerplate |
| Database | PostgreSQL via Supabase (free tier) | Instant setup, built-in realtime websockets |
| Queue | Redis + RQ | Simple background jobs, no infra overhead |
| AI | Anthropic Claude API (`claude-sonnet-4-6`) | Best quality, structured JSON output |
| Google Chat detection | Google Chat API + Workspace Admin SDK | External messaging probe |
| Teams detection | Microsoft Graph API | M365 user lookup + Teams presence |
| Slack detection | Slack Web API | Email → workspace member match |
| Containers | Docker Compose | Local dev only |

---

## Folder Structure

```
forgechannels/
├── frontend/
│   ├── src/
│   │   ├── components/
│   │   │   ├── ui/                         # shadcn/ui primitives
│   │   │   ├── ContactTable.tsx            # contact list with channel badges
│   │   │   ├── ChannelBadge.tsx            # Google/Teams/Slack icon per contact
│   │   │   ├── MessagePreviewCard.tsx      # AI message previews per channel
│   │   │   ├── SequenceLauncher.tsx        # one-click launch button
│   │   │   └── StatusFeed.tsx              # realtime event stream
│   │   ├── pages/
│   │   │   ├── Dashboard.tsx               # main view
│   │   │   ├── Upload.tsx                  # drag-and-drop CSV
│   │   │   └── Settings.tsx                # whitelabel config
│   │   ├── hooks/
│   │   │   ├── useContacts.ts
│   │   │   ├── useChannelDetection.ts
│   │   │   └── useRealtime.ts              # Supabase realtime
│   │   ├── lib/
│   │   │   ├── api.ts                      # typed API client
│   │   │   ├── theme.ts                    # CSS var injection for whitelabel
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
│   │   │   ├── contacts.py                 # CRUD + CSV import
│   │   │   ├── sequences.py                # sequence management
│   │   │   ├── channels.py                 # detection trigger
│   │   │   ├── messages.py                 # AI message gen
│   │   │   ├── gdpr.py                     # opt-out, consent, erasure
│   │   │   └── webhooks.py                 # Salesforge inbound
│   │   ├── api/deps.py                     # FastAPI DI
│   │   ├── core/
│   │   │   ├── config.py                   # pydantic-settings env vars
│   │   │   ├── auth.py                     # X-API-Key middleware
│   │   │   └── database.py                 # SQLAlchemy async
│   │   ├── services/
│   │   │   ├── channel_detector.py         # scoring orchestrator
│   │   │   ├── google_chat_service.py      # Google Chat API probe
│   │   │   ├── teams_service.py            # Microsoft Graph API calls
│   │   │   ├── slack_service.py            # Slack Web API calls
│   │   │   ├── ai_service.py               # Claude API calls
│   │   │   ├── gdpr_service.py             # consent/opt-out logic
│   │   │   └── queue_service.py            # RQ job enqueue
│   │   ├── models/
│   │   │   ├── contact.py
│   │   │   ├── sequence.py
│   │   │   ├── channel_profile.py
│   │   │   ├── message.py
│   │   │   └── gdpr_log.py
│   │   ├── workers/
│   │   │   ├── detection_worker.py         # runs channel detection jobs
│   │   │   └── message_worker.py           # runs AI generation jobs
│   │   ├── prompts/
│   │   │   ├── google_chat.py
│   │   │   ├── teams.py
│   │   │   └── slack.py
│   │   └── main.py
│   ├── migrations/
│   ├── requirements.txt
│   └── Dockerfile
│
├── shared/types/                           # shared TS types
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
-- channel: 'google_chat' | 'teams' | 'slack'
CREATE TABLE channel_profiles (
  id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  contact_id          UUID REFERENCES contacts(id),
  channel             TEXT NOT NULL,          -- 'google_chat' | 'teams' | 'slack'
  reachable           BOOLEAN DEFAULT FALSE,
  confidence_score    FLOAT,                  -- 0.0–1.0
  weighted_score      FLOAT,                  -- confidence × channel_weight
  channel_identifier  TEXT,                   -- workspace user ID / Teams UPN / Chat user ID
  external_enabled    BOOLEAN,                -- whether org has external messaging open
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
  channel               TEXT NOT NULL,        -- 'google_chat' | 'teams' | 'slack'
  body                  TEXT NOT NULL,        -- all channels use body only (no email subject)
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
  method        TEXT                          -- 'reply' | 'api' | 'manual'
);
```

---

## API Endpoints

```
# Contacts
POST   /api/contacts/import-csv              Upload CSV → returns job_id
GET    /api/contacts                         List all contacts for tenant
GET    /api/contacts/{id}
DELETE /api/contacts/{id}                    Triggers GDPR deletion

# Channel Detection
POST   /api/channels/detect/{contact_id}     Enqueue detection for one contact
POST   /api/channels/detect-batch            Enqueue for all contacts in sequence
GET    /api/channels/status/{job_id}         Poll job status
GET    /api/contacts/{id}/channels           Get detection results

# AI Messages
POST   /api/messages/generate/{contact_id}   Generate for contact's winning channel
POST   /api/messages/generate-batch          Generate for all contacts in sequence
GET    /api/messages/{contact_id}
PUT    /api/messages/{id}/approve

# Sequences
POST   /api/sequences
GET    /api/sequences
POST   /api/sequences/{id}/launch            One-click launch
GET    /api/sequences/{id}/status

# GDPR
POST   /api/gdpr/opt-out
GET    /api/gdpr/contact/{id}                Audit log for one contact
POST   /api/gdpr/delete/{id}                 Right to erasure
GET    /api/gdpr/export/{id}                 Data export

# Salesforge Webhooks (inbound)
POST   /webhooks/salesforge/contact          Contact pushed from Salesforge
POST   /webhooks/salesforge/sequence         Sequence trigger from Salesforge

# Whitelabel
GET    /api/tenant/theme
PUT    /api/tenant/theme
```

---

## Channel Detection Algorithm

**Principle:** Run all 3 detections in parallel, score each by `channel_weight × confidence`, sort descending, pick winner.

```python
CHANNEL_WEIGHTS = {
    "slack":        0.40,   # highest signal — Slack Connect or community context
    "teams":        0.35,   # strong M365 signal — federated external access
    "google_chat":  0.25,   # good signal but tightening controls post-Dec 2025
}

async def detect_channels(contact) -> list[ChannelScore]:
    # Run all lookups concurrently
    chat_result, teams_result, slack_result = await asyncio.gather(
        google_chat_service.probe_external(contact.email),
        teams_service.lookup_user(contact.email),
        slack_service.find_member(contact.email),
    )

    scores = []

    # Google Chat — probe whether external messaging is open
    if chat_result.reachable:
        scores.append(ChannelScore(
            "google_chat", True, chat_result.confidence, chat_result.chat_user_id
        ))

    # Microsoft Teams — check M365 user + Teams federation
    if teams_result.found and teams_result.external_access_enabled:
        scores.append(ChannelScore(
            "teams", True, teams_result.confidence, teams_result.upn
        ))

    # Slack — Slack Connect probe or community membership
    if slack_result.found:
        scores.append(ChannelScore(
            "slack", True, slack_result.confidence, slack_result.user_id
        ))

    for s in scores:
        s.weighted_score = CHANNEL_WEIGHTS[s.channel] * s.confidence

    return sorted(scores, key=lambda x: x.weighted_score, reverse=True)
```

**Fallback chain:** Slack → Teams → Google Chat → flag as email-only (hand off to Salesforge)

**Detection logic per channel:**

| Channel | Method | Positive Signal |
|---|---|---|
| Google Chat | `POST spaces.messages` with target email — catch success vs. PERMISSION_DENIED | External messaging enabled on their Workspace |
| Teams | Graph API `GET /users/{email}` + check `teamsAppInstallations` + federation policy | Active M365 user, external access not blocked |
| Slack | `users.lookupByEmail` across known workspaces + `conversations.members` for public communities | Active Slack user reachable via Connect |

---

## AI Prompt Templates

### Google Chat (50–80 words, casual professional)
```
SYSTEM: You write Google Chat direct messages for B2B cold outreach.
Tone: Professional but human. Like a message from a trusted peer, not a vendor.
Length: 50-80 words. No formatting, no bullet points — it's a chat message.
Structure: context-aware opener → one clear value point → low-friction CTA.
Never say "I hope this message finds you well." Never use exclamation points.
Output JSON: {"body": "..."}

USER:
Contact: {first_name} {last_name}, {title} at {company}
Signal: {signal}
Sender: {sender_name} from {sender_company}
Value prop: {value_prop}
```

### Microsoft Teams (60–90 words, semi-formal)
```
SYSTEM: You write Microsoft Teams direct messages for B2B cold outreach.
Tone: Business-professional. Like a warm intro from a colleague's network.
Length: 60-90 words. Can use one line break for readability. No bullet points.
Structure: direct opener with context → why relevant to their role → single CTA.
This lands in their work comms tool — respect that. Be direct, not clever.
Output JSON: {"body": "..."}

USER:
Contact: {first_name} {last_name}, {title} at {company}
Their stack signal: {signal}
Sender: {sender_name} from {sender_company}
Value prop: {value_prop}
```

### Slack (2–3 sentences, community-native)
```
SYSTEM: You write Slack DMs for community-based B2B outreach.
Tone: Fully casual. Community member talking to community member. Zero corporate.
Length: 2-3 short sentences. Max 1 emoji. Never pitch.
Open with something specific to their work/community context.
The goal is a reply, not a demo. Ask one low-stakes question.
Output JSON: {"body": "..."}

USER:
Contact: {first_name}, {title} at {company}
Shared community or context: {shared_context}
Signal: {signal}
Sender: {sender_name}
```

---

## GDPR Compliance Design

| Requirement | Implementation |
|---|---|
| Lawful basis | Legitimate interest logged per contact at CSV import time |
| Opt-out | `opt_outs` table; checked before every send job; reply-based opt-out detected by keyword matching |
| Right to erasure | Cascade delete contact + profiles + messages; gdpr_log tombstone retained |
| Audit trail | All events written to `gdpr_logs` with timestamp + IP |
| Data retention | Cron deletes inactive contacts after 24 months (configurable per tenant) |
| Opt-out instruction | Appended to every generated message: "Reply STOP to opt out" |
| Channel-specific | Opt-out on one channel does not auto-opt-out others unless contact requests all-channel removal |

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
  "contact": {
    "email": "...",
    "firstName": "...",
    "lastName": "...",
    "company": "...",
    "title": "..."
  }
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
GOOGLE_CHAT_SERVICE_ACCOUNT_JSON=    # Google Workspace service account
GOOGLE_WORKSPACE_DOMAIN=             # e.g. yourcompany.com

MICROSOFT_CLIENT_ID=                 # Azure AD app registration
MICROSOFT_CLIENT_SECRET=
MICROSOFT_TENANT_ID=

SLACK_BOT_TOKEN=                     # Bot token with users:read.email scope
SLACK_COMMUNITY_WORKSPACES=          # Comma-separated workspace IDs to probe

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
| Google API | `google-auth` + `google-api-python-client` |
| Microsoft Graph | `msal` + `httpx` |
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
- [ ] Contact table with channel status columns (Google Chat / Teams / Slack badges)

### Hours 10–18: Channel Detection ← *Core demo value*
- [ ] Microsoft Teams detection via Graph API — most reliable for demo
- [ ] Slack detection via `users.lookupByEmail` — high visual impact
- [ ] Google Chat probe — mock fallback if API access blocked during hackathon
- [ ] Scoring algorithm with fallback chain
- [ ] RQ worker queue
- [ ] Supabase Realtime → frontend badge updates live
- [ ] Channel badge UI: Google Chat (blue G), Teams (purple), Slack (rainbow hash)

### Hours 18–28: AI Message Generation ← *Second biggest wow*
- [ ] Claude API + all 3 channel prompt templates
- [ ] Hardcode 2–3 realistic signals per demo contact
- [ ] `POST /api/messages/generate-batch`
- [ ] Message preview cards showing same contact, different channel tones side-by-side
- [ ] Approve/edit inline

### Hours 28–36: Sequence Launch + Dashboard
- [ ] "Launch Sequence" button
- [ ] Sequence status tracking
- [ ] Channel breakdown chart — pie showing Google Chat vs Teams vs Slack split (recharts)
- [ ] Realtime status feed showing send events

### Hours 36–42: GDPR + Whitelabel
- [ ] Opt-out endpoint + "Reply STOP" detection stub
- [ ] CSS var theme engine + live preview
- [ ] Salesforge webhook endpoint

### Hours 42–48: Polish + Demo Prep
- [ ] 10 realistic demo contacts seeded — mix of Workspace, M365, and Slack users
- [ ] Demo script rehearsed
- [ ] Mobile responsive cleanup
- [ ] README + `.env.example` finalized
- [ ] Fallback demo video recorded

---

## Demo Script (for judges / Salesforge)

1. Open `http://localhost:5173`
2. Drag in `demo_contacts.csv` — 10 contacts from different company types
3. Click **Detect Channels** → watch Google Chat / Teams / Slack badges populate in realtime
4. Show the channel breakdown chart — "60% of your prospects are reachable on channels no one else is using"
5. Click **Generate Messages** → Claude writes messages tuned to each channel's norms
6. Show message preview cards side by side — Teams message is formal, Slack is casual, Google Chat is somewhere in between — same contact, totally different voice
7. Click **Launch Sequence** → realtime status feed
8. Switch to GDPR tab → show legitimate interest log, opt-out trail
9. Switch to Settings → swap logo + primary color → UI rebrands live as "Salesforge Channels"

**The pitch line:** *"Email is full. LinkedIn is saturated. Your buyers are sitting in Google Chat, Teams, and Slack all day — and nobody is reaching them there. ForgeChannels changes that."*