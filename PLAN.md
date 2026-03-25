# ForgeChannels — Hackathon Build Plan

> Salesforge owns email. ForgeChannels owns the inbox everyone forgot about.
> Cold outreach via Google Chat, Microsoft Teams, and Slack — the three most
> untapped B2B messaging channels. GDPR-compliant, AI-personalized.

---

## What We're Building

A **terminal CLI tool** that:
1. Walks the user through setup: configure sender email (Google Sign-in via OAuth), input API keys
2. Takes a CSV of contacts (ships with a `demo_contacts.csv` for testing)
3. Detects which untapped chat channel each contact is reachable on (Google Chat, Teams, Slack)
4. Scores and selects the optimal channel per contact
5. Sends an AI-generated personalized opener via Google Chat
6. Handles the ongoing conversation with a free LLM (Gemini Flash / Llama via Groq) to keep it natural
7. Steers the conversation toward booking a demo call (generates a scheduling link)

**The core insight:**
- Email inboxes: saturated, spam-filtered, ignored
- LinkedIn: everyone's doing it, connection limits, message requests buried
- Google Chat / Teams / Slack: near-zero cold outreach today, native to how people work, no promotional tab

**Demo flow (48h goal):**
```
$ forgechannels

Welcome to ForgeChannels 🚀

Step 1: Configure your sender email
  → Sign in with Google (opens browser for OAuth)
  ✓ Authenticated as you@company.com

Step 2: API Keys
  Google Chat API: ✓ (configured via Google OAuth)
  Anthropic API key: ________
  Microsoft Client ID (optional): ________
  Slack Bot Token (optional): ________

Step 3: Load contacts
  → Using demo_contacts.csv (15 contacts)
  → Or specify path: ________

Step 4: Detecting channels...
  ✓ alice@startup.io     → Google Chat (confidence: 0.92)
  ✓ bob@enterprise.com   → Teams (confidence: 0.87)
  ✓ carol@devtools.co    → Slack (confidence: 0.95)
  ...

Step 5: Generating AI messages...
  Preview:
  ┌─ Google Chat → alice@startup.io ─────────────┐
  │ Hey Alice, saw Startup.io just shipped the    │
  │ new onboarding flow — nice work. We've been   │
  │ helping similar teams cut churn by 30%...      │
  └───────────────────────────────────────────────┘

  Send all? [y/n/edit]
```

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
| CLI Framework | Python + `rich` + `typer` | Beautiful terminal UI, progress bars, tables, prompts |
| Auth | Google OAuth 2.0 (installed app flow) | Opens browser, returns token — configures Google Chat API automatically |
| Config storage | `~/.forgechannels/config.json` | Persists API keys + OAuth tokens between runs |
| AI (opener) | Anthropic Claude API (`claude-sonnet-4-6`) | Best quality for first impression message |
| AI (conversation) | Gemini 2.0 Flash (free tier) OR Groq Llama 3 | Free, fast — handles ongoing back-and-forth replies |
| Scheduling | Calendly / Cal.com link generation | Drop a booking link when prospect is warm |
| Google Chat detection | Google Chat API (via OAuth token) | External messaging probe |
| Teams detection | Microsoft Graph API | M365 user lookup + Teams presence |
| Slack detection | Slack Web API | Email → workspace member match |
| CSV parsing | `pandas` | Robust CSV handling |

---

## Folder Structure

```
forgechannels/
├── cli/
│   ├── __init__.py
│   ├── main.py                     # typer app, main entry point
│   ├── auth/
│   │   ├── google_oauth.py         # Google OAuth installed app flow
│   │   └── config_store.py         # read/write ~/.forgechannels/config.json
│   ├── services/
│   │   ├── channel_detector.py     # scoring orchestrator
│   │   ├── google_chat_service.py  # Google Chat API: detect + send + read replies
│   │   ├── teams_service.py        # Microsoft Graph API calls
│   │   ├── slack_service.py        # Slack Web API calls
│   │   ├── ai_opener.py           # Claude API — generates first message
│   │   ├── ai_conversation.py     # Free LLM — handles ongoing replies
│   │   └── scheduler.py           # booking link injection + interest detection
│   ├── prompts/
│   │   ├── opener.py              # channel-specific opener prompts (Claude)
│   │   └── conversation.py        # ongoing conversation system prompt (free LLM)
│   ├── models.py                   # dataclasses for Contact, ChannelScore, Message
│   └── display.py                  # rich tables, panels, progress bars
│
├── demo_contacts.csv               # 15 realistic test contacts
├── credentials/
│   └── google_client_secret.json   # Google OAuth client ID (checked in, public client)
├── requirements.txt
├── setup.py                        # `pip install -e .` → `forgechannels` command
├── .env.example
└── README.md
```

---

## Config Storage

No database needed. Config is stored locally at `~/.forgechannels/config.json`:

```json
{
  "google_oauth_token": { "access_token": "...", "refresh_token": "...", "expiry": "..." },
  "sender_email": "you@company.com",
  "anthropic_api_key": "sk-ant-...",
  "microsoft_client_id": "...",
  "microsoft_client_secret": "...",
  "microsoft_tenant_id": "...",
  "slack_bot_token": "xoxb-...",
  "slack_community_workspaces": ["T01234", "T56789"]
}
```

### Google OAuth Setup

- Use **Google OAuth 2.0 for Installed Applications** (Desktop app flow)
- On first run: opens browser → user signs in with Google → grants Chat API + Gmail scopes
- Token is saved to config — subsequent runs reuse it (auto-refresh)
- This single sign-in configures both the sender identity AND the Google Chat API credentials
- Scopes needed: `https://www.googleapis.com/auth/chat.messages.create`, `https://www.googleapis.com/auth/userinfo.email`

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

## Conversation Flow (Free LLM)

After the initial opener is sent, the tool needs to handle replies automatically to keep the conversation going naturally and steer toward a booked call.

**Why a free LLM:** The opener uses Claude for quality, but ongoing conversation could be dozens of back-and-forth messages across many contacts. A free model keeps costs at zero.

**Options (pick one):**
| Model | Free Tier | Speed | How |
|---|---|---|---|
| **Gemini 2.0 Flash** | 15 RPM / 1M tokens/day free | Very fast | `google-generativeai` Python SDK |
| **Groq (Llama 3.3 70B)** | 30 RPM free | Extremely fast | `groq` Python SDK |
| **Ollama (local)** | Unlimited, runs locally | Depends on hardware | `ollama` CLI + API |

**Conversation system prompt:**
```
You are a friendly sales rep having a Google Chat conversation.
Your goal: build rapport → understand their needs → book a demo call.
Keep messages short (1-3 sentences). Sound human, not like a bot.
When the prospect shows interest, naturally suggest a quick call and share the booking link: {booking_url}
Never be pushy. If they say no, be gracious and leave the door open.
Match their energy and tone.
```

**Reply detection:** Poll Google Chat API for new messages in active conversations, or use a webhook/push notification if available.

---

## Schedule Call / Demo Booking

The end goal of every conversation is booking a call. The tool needs to:

1. **Detect buying signals** — LLM classifies each reply as: `interested` / `neutral` / `not_interested` / `already_booking`
2. **Drop the booking link** — when interest is detected, the LLM naturally weaves in a scheduling link
3. **Booking link options:**
   - **Calendly:** user provides their Calendly link in setup (simplest for demo)
   - **Cal.com:** same approach, user provides link
   - **Google Calendar API:** generate a proposed time directly (more impressive but harder)
4. **Confirmation tracking** — detect when prospect confirms a time or clicks the link

**Example conversation flow:**
```
[Opener — Claude]
Hey Alice, saw TechStartup just shipped the new onboarding flow — nice work.
We've been helping similar teams cut churn by 30% with channel-based outreach.
Worth a quick look?

[Reply from Alice]
Oh interesting, how does that work exactly?

[Free LLM reply]
In short — instead of email, we reach people on the tools they already have open
(Chat, Teams, Slack). Response rates are 3-5x higher. Happy to walk you through
a quick 15-min demo if you're curious? Here's my calendar: https://cal.com/you/15min

[Reply from Alice]
Sure, Thursday works

[Free LLM reply]
Booked! Looking forward to it 🙌
```

---

## Demo Contacts CSV

Ship a `demo_contacts.csv` with 15 realistic test contacts spanning different company types:

```csv
email,first_name,last_name,company,title,signal
alice.chen@techstartup.io,Alice,Chen,TechStartup,Head of Growth,"Just launched v2.0 of their onboarding flow"
bob.mueller@enterprise-corp.com,Bob,Mueller,EnterpriseCorp,VP Sales,"Expanding into EMEA market Q1 2026"
carol.davis@devtools.co,Carol,Davis,DevTools,CTO,"Active in #product-led-growth Slack community"
dave.kim@saas-platform.com,Dave,Kim,SaaSPlatform,Head of Partnerships,"Spoke at SaaStr on partner ecosystems"
elena.volkov@fintech-eu.de,Elena,Volkov,FintechEU,COO,"Series B announced last month"
frank.osei@cloudops.io,Frank,Osei,CloudOps,Director of Engineering,"Hiring 5 backend engineers"
grace.nakamura@retailtech.com,Grace,Nakamura,RetailTech,CMO,"Rebranded and launched new positioning"
hassan.ahmed@dataflow.ai,Hassan,Ahmed,DataFlow,Founder & CEO,"Y Combinator W26 batch"
iris.johnson@consulting-group.com,Iris,Johnson,ConsultingGroup,Managing Partner,"Published report on AI adoption in enterprise"
jake.torres@marketstack.io,Jake,Torres,MarketStack,Growth Lead,"3x ARR growth last year"
kate.wright@securenet.com,Kate,Wright,SecureNet,CISO,"Speaking at RSA Conference 2026"
liam.brennan@edtech.co,Liam,Brennan,EdTech,VP Product,"Just shipped AI tutoring feature"
maya.patel@healthbridge.io,Maya,Patel,HealthBridge,CEO,"Won TechCrunch Disrupt Health track"
noah.silva@logistix.com,Noah,Silva,Logistix,Head of Operations,"Expanding warehouse network to 12 cities"
olivia.zhang@creativeai.co,Olivia,Zhang,CreativeAI,Head of Design,"Open source design system has 5k GitHub stars"
```

This CSV includes a `signal` column — used by Claude to personalize each message with a relevant, specific opener.

---

## Key Libraries

| Purpose | Library |
|---|---|
| CLI framework | `typer` |
| Terminal UI | `rich` (tables, panels, progress bars, prompts) |
| Async HTTP | `httpx` |
| CSV parsing | `pandas` |
| Google OAuth | `google-auth-oauthlib` + `google-auth` |
| Google Chat API | `google-api-python-client` |
| Microsoft Graph | `msal` + `httpx` |
| Slack API | `slack_sdk` |
| AI (opener) | `anthropic` |
| AI (conversation) | `google-generativeai` or `groq` |

---

## 48h Build Order

### Hours 0–4: Foundation + Setup Flow
- [ ] Python project scaffold: `setup.py`, `requirements.txt`, typer app
- [ ] Config store: `~/.forgechannels/config.json` read/write
- [ ] Google OAuth installed app flow (opens browser, saves token)
- [ ] Setup wizard: prompt for API keys + booking link
- [ ] `demo_contacts.csv` created with 15 realistic contacts

### Hours 4–12: Channel Detection + Google Chat API
- [ ] CSV parser with validation (pandas)
- [ ] Rich table display of loaded contacts
- [ ] Google Chat detection via OAuth token (can we send? → reachable)
- [ ] Teams detection via Graph API (if keys provided)
- [ ] Slack detection via `users.lookupByEmail` (if token provided)
- [ ] Scoring algorithm with fallback chain
- [ ] Google Chat send message via API (real sends)
- [ ] Google Chat read replies (poll for new messages)

### Hours 12–20: AI — Opener + Conversation
- [ ] Claude API integration for personalized openers
- [ ] Free LLM setup (Gemini Flash or Groq) for conversation
- [ ] Conversation system prompt with booking link injection
- [ ] Interest detection: classify replies as interested/neutral/not_interested
- [ ] Auto-reply loop: read reply → generate response → send → repeat
- [ ] Rich panels showing conversation threads per contact

### Hours 20–28: Schedule Call Flow
- [ ] Booking link configuration in setup (Calendly/Cal.com URL)
- [ ] LLM naturally suggests call when interest detected
- [ ] Track conversation state per contact (opener_sent → in_conversation → call_proposed → booked)
- [ ] Summary dashboard: how many contacted / replied / booked

### Hours 28–36: Integration + Error Handling
- [ ] End-to-end flow: detect → send opener → converse → book call
- [ ] Graceful handling when APIs are unavailable
- [ ] Token refresh for expired Google OAuth
- [ ] `--dry-run` flag to preview without sending
- [ ] Mock mode with realistic delays for demo fallback

### Hours 36–48: Demo Prep + Polish
- [ ] `README.md` with setup instructions
- [ ] Demo script rehearsed end-to-end
- [ ] Fallback demo video recorded
- [ ] Edge case cleanup

---

## Demo Script (for judges / Salesforge)

1. Open terminal, run `forgechannels`
2. **Setup:** Sign in with Google (browser opens, one click) → "Authenticated as demo@company.com"
3. Paste API keys, set booking link → saved
4. **Load contacts:** `Using demo_contacts.csv — 15 contacts loaded`
5. **Detect channels** → live progress bar, channels light up per contact:
   - "alice@techstartup.io → Google Chat ✓"
   - "bob@enterprise-corp.com → Teams ✓"
   - "carol@devtools.co → Slack ✓"
6. **Summary table** — "60% reachable on channels no one else is using"
7. **Send openers** → Claude writes personalized first messages → sends via Google Chat
8. **Live conversation** → show a reply coming in → free LLM auto-responds naturally
9. **Booking moment** → prospect shows interest → LLM drops the calendar link → call booked
10. **Dashboard** — "5 contacted / 3 replied / 1 call booked"

**The pitch line:** *"Email is full. LinkedIn is saturated. Your buyers are sitting in Google Chat all day — and nobody is reaching them there. One command starts the conversation. AI keeps it going. You just show up to the call."*