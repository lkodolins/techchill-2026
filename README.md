# ForgeChannels

**Reach B2B prospects where they work — Google Chat & Microsoft Teams.**

ForgeChannels is an AI-powered outreach CLI tool that sends personalized messages to prospects via Google Chat and Microsoft Teams instead of crowded email inboxes. It automatically detects which platform each contact uses, sends tailored openers, and uses Claude AI to handle the full conversation — from first message to booked demo call.

Built for the [Salesforge](https://salesforge.ai) challenge at TechChill 2026.

---

## How It Works

1. **Load contacts** from a CSV file
2. **Detect email provider** via MX record lookup (Google Workspace → Google Chat, Microsoft 365 → Teams)
3. **Send personalized messages** through the appropriate chat platform
4. **AI conversation engine** monitors replies and auto-responds using Claude, steering toward a booked demo
5. **Calendar integration** automatically creates Google Calendar events with Meet links when a time is agreed

## Features

- **Multi-channel routing** — automatic Google Chat / Teams detection per contact
- **AI-powered conversations** — Claude handles objections, scheduling, and follow-ups
- **Calendar + Meet integration** — creates calendar events with video links when a meeting time is agreed
- **Interactive setup** — guided first-run flow for all API credentials
- **Rich CLI** — colorful terminal UI with progress indicators, tables, and status panels

---

## Prerequisites

- **Python 3.12+**
- **Google Cloud project** with Google Chat API, Calendar API, and OAuth consent screen configured
- **Microsoft Azure app registration** (optional, for Teams support)
- **Anthropic API key** (optional, for AI conversation monitoring)

---

## Quick Start

```bash
git clone <repo-url>
cd techchill/forgechannels
./start.sh
```

That's it. `start.sh` automatically creates a Python virtual environment, installs all dependencies, and launches the CLI. On the first run it will walk you through setting up API credentials interactively.

### CLI flags

```bash
./start.sh --dry-run          # preview everything without sending
./start.sh --no-ai            # skip AI conversation monitoring
./start.sh --csv my_leads.csv # use a custom contacts file
./start.sh --credentials path/to/secret.json  # custom Google OAuth file
```

### Manual setup (alternative)

If you prefer to manage the environment yourself:

```bash
cd techchill/forgechannels
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python3 -m cli.main
```

---

## Configuration

All credentials are stored locally at `~/.forgechannels/config.json`. Nothing is committed to the repo — you set everything up through the CLI on first run.

### Google Chat (required for Google Workspace contacts)

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create a new project (or use an existing one)
3. Enable the **Google Chat API** and **Google Calendar API**:
   - APIs & Services → Library → search and enable both
4. Configure **OAuth consent screen**:
   - APIs & Services → OAuth consent screen
   - User type: External (or Internal if using Google Workspace)
   - Fill in app name and email, skip the rest
5. Create **OAuth credentials**:
   - APIs & Services → Credentials → Create Credentials → OAuth client ID
   - Application type: **Desktop app**
   - Download the JSON file
6. Place the downloaded file at `forgechannels/credentials/google_client_secret.json`

On first run, ForgeChannels will open a browser window for you to authorize access. The token is cached at `~/.forgechannels/token.json` for subsequent runs.

### Microsoft Teams (required for Microsoft 365 contacts)

1. Go to [Azure Portal — App Registrations](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
2. Click **New registration**
3. Set redirect URI to: `https://login.microsoftonline.com/common/oauth2/nativeclient`
4. Under API Permissions, add **Delegated** permissions:
   - `Chat.ReadWrite`
   - `Chat.Create`
   - `User.ReadBasic.All`
5. Copy the **Application (client) ID**

The CLI will prompt you for this Client ID on first run and save it to config. Authentication uses the device code flow — you'll see a code to enter at `https://microsoft.com/devicelogin`.

#### External / federated Teams users

If your recipient is in a different Microsoft tenant, Graph API can't resolve them by email alone. Add their details to `~/.forgechannels/config.json`:

```json
{
  "microsoft_client_id": "your-client-id",
  "microsoft_external_users": {
    "user@external-company.com": {
      "user_id": "their-azure-ad-object-id",
      "tenant_id": "their-tenant-id"
    }
  }
}
```

### Anthropic API Key (optional — enables AI auto-replies)

1. Get an API key at [console.anthropic.com](https://console.anthropic.com/settings/keys)
2. Either set `ANTHROPIC_API_KEY` as an environment variable, or enter it when prompted on first run

The AI engine uses Claude to:
- Classify prospect replies (interested / neutral / not interested)
- Generate natural follow-up messages
- Detect when a meeting time is agreed and trigger calendar event creation

---

## Contacts CSV Format

Prepare a CSV file with these columns:

| Column | Required | Description |
|---|---|---|
| `email` | Yes | Prospect's work email |
| `first_name` | Yes | First name |
| `last_name` | Yes | Last name |
| `company` | Yes | Company name |
| `title` | Yes | Job title |
| `signal` | No | Recent activity / news to reference in the message |

Example (`demo_contacts.csv`):

```csv
email,first_name,last_name,company,title,signal
jane.doe@acme.com,Jane,Doe,Acme Corp,VP of Sales,just raised a Series B and is scaling their sales team
john.smith@globex.com,John,Smith,Globex Inc,Head of Growth,launched a new product line and is hiring SDRs
```

---

## CLI Options

```
forgechannels [OPTIONS]

Options:
  -c, --csv TEXT          Path to contacts CSV (default: demo_contacts.csv)
  -d, --dry-run           Preview everything without sending messages
  --no-ai                 Skip AI conversation monitoring
  --credentials TEXT       Path to Google OAuth client secret JSON
  --help                  Show this help message
```

---

## Architecture

```
forgechannels/
├── cli/
│   ├── main.py                  # CLI entry point — orchestrates the full flow
│   ├── models.py                # Contact and MessageResult data classes
│   ├── auth/
│   │   ├── config_store.py      # JSON config at ~/.forgechannels/config.json
│   │   └── google_oauth.py      # Google OAuth 2.0 flow with guided setup
│   └── services/
│       ├── ai_service.py        # Claude AI — reply generation & interest classification
│       ├── calendar_service.py  # Google Calendar + Meet link creation
│       ├── conversation.py      # Conversation monitor — polls & auto-responds
│       ├── email_provider.py    # MX record lookup for provider detection
│       ├── google_chat_service.py  # Google Chat API — DMs & message listing
│       └── teams_service.py     # Microsoft Teams Graph API — DMs via device code flow
├── agents.md                    # Product context fed to the AI for conversations
├── demo_contacts.csv            # Example contacts file
├── requirements.txt             # Python dependencies
├── setup.py                     # Package setup
└── start.sh                     # One-command launcher
```

---

## How the Conversation Engine Works

1. **Send openers** — personalized messages go out via Google Chat / Teams
2. **Poll for replies** — the monitor checks each conversation every 10 seconds
3. **Classify interest** — Claude categorizes each reply as interested, neutral, not interested, or booked
4. **Generate reply** — Claude writes a natural follow-up based on conversation history and product context
5. **Book meeting** — when a time is proposed, Claude extracts the date/time, creates a Google Calendar event with a Meet link, and shares it in the chat
6. **Close gracefully** — if the prospect declines, the AI sends a polite sign-off

---

## Running Tests

```bash
cd forgechannels
source .venv/bin/activate
python -m pytest tests/
```

---

## License

Built for the Salesforge challenge at TechChill 2026 hackathon.
