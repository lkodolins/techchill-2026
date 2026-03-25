# ForgeChannels

ForgeChannels is a Python CLI for outbound prospecting over Google Chat and Microsoft Teams. It routes each contact to the likely platform, sends a personalized opener, and can use Claude to continue the conversation toward a booked meeting.

Built for the Salesforge challenge at TechChill 2026.

## Repo Layout

```text
.
├── docs/                  # challenge brief and supporting project notes
├── forgechannels/         # runnable application
│   ├── cli/               # CLI entry point, auth, services, models
│   ├── tests/             # automated tests
│   ├── agents.md          # prompt/context file used by the AI service
│   ├── demo_contacts.csv  # sample input data
│   ├── requirements.txt   # Python dependencies
│   ├── setup.py           # package metadata and console entrypoint
│   └── start.sh           # local bootstrap script
├── Makefile               # common repo-level commands
└── README.md
```

## What It Does

- Detects whether a prospect is more likely reachable via Google Workspace or Microsoft 365.
- Sends chat-based outreach instead of cold email.
- Monitors replies and generates follow-ups with Claude.
- Creates Google Calendar events with Meet links when a meeting is agreed.

## Quick Start

Clone the repo, move into the project folder, and start the app:

```bash
git clone <repo-url>
cd techchill
make run
```

`make run` enters `forgechannels/`, creates `.venv` if needed, installs dependencies, and starts the CLI.

Common variants:

```bash
make dry-run
make test
make install
```

If you prefer to run the app directly:

```bash
cd forgechannels
./start.sh --dry-run
```

## Requirements

- Python 3.12+
- Google Cloud project with Google Chat API and Google Calendar API enabled
- Azure app registration if you want Teams support
- Anthropic API key if you want AI reply handling

## Configuration Notes

- Local config is stored in `~/.forgechannels/config.json`
- Google OAuth credentials should not be committed
- The app will guide first-run auth setup interactively

## Contacts CSV

Expected columns:

| Column | Required | Description |
|---|---|---|
| `email` | Yes | Prospect work email |
| `first_name` | Yes | First name |
| `last_name` | Yes | Last name |
| `company` | Yes | Company name |
| `title` | Yes | Job title |
| `signal` | No | Relevant context for personalization |

Sample file: `forgechannels/demo_contacts.csv`

## Commands

From `forgechannels/`:

```bash
./start.sh --dry-run
./start.sh --no-ai
./start.sh --csv my_leads.csv
./start.sh --credentials path/to/google_client_secret.json
python -m pytest tests/
```

## Submission Notes

- Main application code lives under `forgechannels/cli/`
- Supporting docs live under `docs/`
- The current automated coverage is focused on Teams chat creation behavior

Built for the Salesforge challenge at TechChill 2026 hackathon.
