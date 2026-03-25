"""Google OAuth 2.0 installed app flow for Google Chat API."""

import json
import os
import webbrowser
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

console = Console()

SCOPES = [
    "openid",
    "https://www.googleapis.com/auth/chat.messages.create",
    "https://www.googleapis.com/auth/chat.messages",
    "https://www.googleapis.com/auth/chat.spaces",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/calendar.events",
]

CONFIG_DIR = Path.home() / ".forgechannels"
TOKEN_PATH = CONFIG_DIR / "token.json"
CREDENTIALS_DIR = Path("credentials")
CREDENTIALS_PATH = CREDENTIALS_DIR / "google_client_secret.json"

SETUP_GUIDE = """[bold yellow]Google Cloud credentials not found.[/bold yellow]

You need a Google Cloud OAuth client secret. Here's how (takes ~2 min):

[bold]1.[/bold] Go to [cyan]https://console.cloud.google.com[/cyan]
   - Create a new project (or use an existing one)

[bold]2.[/bold] Enable the [bold]Google Chat API[/bold]:
   - APIs & Services > Library > search "Google Chat API" > Enable

[bold]3.[/bold] Configure OAuth consent screen:
   - APIs & Services > OAuth consent screen
   - User type: [bold]External[/bold] (or Internal if Workspace)
   - Fill in app name, email — skip the rest

[bold]4.[/bold] Create OAuth credentials:
   - APIs & Services > Credentials > Create Credentials > OAuth client ID
   - Application type: [bold]Desktop app[/bold]
   - Download the JSON file

[bold]5.[/bold] Place the downloaded file at:
   [green]credentials/google_client_secret.json[/green]"""

GCP_CONSOLE_URL = "https://console.cloud.google.com/apis/credentials"


def _find_client_secret(override_path: str | None = None) -> str | None:
    """Look for the client secret JSON in common locations."""
    candidates = [
        override_path,
        str(CREDENTIALS_PATH),
        "google_client_secret.json",
        "credentials.json",
        str(CONFIG_DIR / "google_client_secret.json"),
    ]
    for path in candidates:
        if path and os.path.exists(path):
            return path
    return None


def _guide_setup() -> str:
    """Interactive guide to set up Google Cloud credentials. Returns the path."""
    console.print(Panel(SETUP_GUIDE, title="Setup Required", border_style="yellow"))

    if Prompt.ask(
        "\nOpen Google Cloud Console in your browser?",
        choices=["y", "n"],
        default="y",
    ) == "y":
        webbrowser.open(GCP_CONSOLE_URL)

    console.print(
        "\nOnce you have the JSON file, drop it in the [green]credentials/[/green] folder."
    )

    # Let user paste a custom path if they saved it elsewhere
    custom = Prompt.ask(
        "Path to client secret JSON (Enter to use credentials/google_client_secret.json)",
        default=str(CREDENTIALS_PATH),
    )

    if not os.path.exists(custom):
        console.print(f"[red]File not found:[/red] {custom}")
        console.print("Re-run once you've placed the file there.")
        raise SystemExit(1)

    # Copy to standard location if it's elsewhere
    if custom != str(CREDENTIALS_PATH):
        CREDENTIALS_DIR.mkdir(exist_ok=True)
        import shutil
        shutil.copy2(custom, CREDENTIALS_PATH)
        console.print(f"  [green]Copied to {CREDENTIALS_PATH}[/green]")

    return str(CREDENTIALS_PATH)


def authenticate(client_secret_path: str | None = None) -> Credentials:
    """Authenticate with Google OAuth. Opens browser on first run.

    If no credentials file is found, walks the user through setup.
    """
    CONFIG_DIR.mkdir(exist_ok=True)

    creds = None

    # Load existing token
    if TOKEN_PATH.exists():
        creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)

    # Refresh or run new flow
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            found = _find_client_secret(client_secret_path)
            if not found:
                found = _guide_setup()

            flow = InstalledAppFlow.from_client_secrets_file(found, SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next time
        with open(TOKEN_PATH, "w") as f:
            f.write(creds.to_json())

    return creds


def get_user_email(creds: Credentials) -> str:
    """Get the authenticated user's email address."""
    from googleapiclient.discovery import build

    service = build("oauth2", "v2", credentials=creds)
    user_info = service.userinfo().get().execute()
    return user_info.get("email", "unknown")
