"""Interactive setup wizard for ForgeChannels."""

import os
import sys
from pathlib import Path

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt

from cli.auth.config_store import (
    CONFIG_DIR,
    CONFIG_PATH,
    get_config_value,
    set_config_value,
)
from cli.auth.google_oauth import (
    CREDENTIALS_PATH,
    CREDENTIALS_DIR,
    TOKEN_PATH,
    _find_client_secret,
    authenticate,
    get_user_email,
)

console = Console()

CHECK = "[green]✓[/green]"
CROSS = "[red]✗[/red]"
SKIP = "[dim]–[/dim]"


def _header():
    console.print()
    console.print(
        Panel(
            "[bold bright_blue]ForgeChannels Setup[/bold bright_blue]\n"
            "[dim]Let's get everything configured so you can start sending.[/dim]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )


def _step(n: int, title: str):
    console.print(f"\n  [bold bright_blue]({n})[/bold bright_blue] [bold]{title}[/bold]")


# ── Step 1: Google Cloud credentials ────────────────────────────────────────


def _do_google_signin(client_secret_path: str) -> bool:
    """Run the Google OAuth flow now so the user is signed in."""
    console.print("      Signing in via browser...")
    try:
        creds = authenticate(client_secret_path)
        email = get_user_email(creds)
        console.print(f"      {CHECK} Signed in as [cyan]{email}[/cyan]")
        return True
    except Exception as e:
        console.print(f"      {CROSS} Sign-in failed: {e}")
        console.print(f"      [dim]You can retry with [bold]make setup[/bold] later.[/dim]")
        return False


def _setup_google() -> bool:
    _step(1, "Google Chat credentials")

    # Already have a token?
    if TOKEN_PATH.exists():
        console.print(f"      {CHECK} Google OAuth token found at [dim]{TOKEN_PATH}[/dim]")
        console.print(f"      [dim]Delete {TOKEN_PATH} to re-authenticate.[/dim]")
        return True

    found = _find_client_secret()
    if found:
        console.print(f"      {CHECK} Client secret found at [dim]{found}[/dim]")
        return _do_google_signin(found)

    console.print(f"      {CROSS} No Google client secret found.")
    console.print()
    console.print("      To send messages via Google Chat, you need an OAuth client secret.")
    console.print("      [bold]Quick setup (~2 min):[/bold]")
    console.print("        1. Go to [cyan]https://console.cloud.google.com[/cyan]")
    console.print("        2. Create a project → Enable [bold]Google Chat API[/bold] + [bold]Google Calendar API[/bold]")
    console.print("        3. OAuth consent screen → External → fill in app name & email")
    console.print("        4. Credentials → Create OAuth client ID → [bold]Desktop app[/bold]")
    console.print("        5. Download the JSON file")
    console.print()
    console.print("      [dim]Then drag the file here, paste the path, or paste the JSON contents.[/dim]")
    console.print()

    value = Prompt.ask(
        "      File path or JSON (Enter to skip)",
        default="",
    )

    if not value:
        console.print(f"      {SKIP} Skipping Google Chat — you can set this up later.")
        return False

    value = value.strip().strip("'\"")  # strip quotes from drag-and-drop

    import json as _json

    # Check if they pasted raw JSON
    if value.startswith("{"):
        try:
            data = _json.loads(value)
            # Validate it looks like a client secret
            if "installed" not in data and "web" not in data:
                console.print(f"      {CROSS} Doesn't look like a Google client secret JSON (missing 'installed' or 'web' key).")
                return False
            CREDENTIALS_DIR.mkdir(exist_ok=True)
            with open(CREDENTIALS_PATH, "w") as f:
                _json.dump(data, f, indent=2)
            console.print(f"      {CHECK} Saved to [dim]{CREDENTIALS_PATH}[/dim]")
            return _do_google_signin(str(CREDENTIALS_PATH))
        except _json.JSONDecodeError:
            console.print(f"      {CROSS} Invalid JSON. Try pasting the file path instead.")
            return False

    # Otherwise treat as file path
    path = os.path.expanduser(value)
    if not os.path.isfile(path):
        console.print(f"      {CROSS} File not found: {path}")
        return False

    # Validate it's actual JSON
    try:
        with open(path) as f:
            data = _json.load(f)
        if "installed" not in data and "web" not in data:
            console.print(f"      {CROSS} Doesn't look like a Google client secret JSON.")
            return False
    except (_json.JSONDecodeError, OSError) as e:
        console.print(f"      {CROSS} Can't read file: {e}")
        return False

    CREDENTIALS_DIR.mkdir(exist_ok=True)
    import shutil
    shutil.copy2(path, CREDENTIALS_PATH)
    console.print(f"      {CHECK} Saved to [dim]{CREDENTIALS_PATH}[/dim]")
    return _do_google_signin(str(CREDENTIALS_PATH))


# ── Step 2: Microsoft Teams ─────────────────────────────────────────────────


def _setup_teams() -> bool:
    _step(2, "Microsoft Teams credentials")

    client_id = get_config_value("microsoft_client_id")
    if client_id:
        console.print(f"      {CHECK} Teams client ID configured: [dim]{client_id[:8]}...[/dim]")
        teams_token = Path.home() / ".forgechannels" / "teams_token.json"
        if teams_token.exists():
            console.print(f"      {CHECK} Teams token cache found")
        else:
            console.print(f"      [dim]You'll authenticate via device code on first [bold]make run[/bold].[/dim]")
        return True

    console.print(f"      {CROSS} No Microsoft Teams client ID found.")
    console.print()
    console.print("      To send messages via Microsoft Teams, you need an Azure app registration.")
    console.print("      [bold]Quick setup (~2 min):[/bold]")
    console.print("        1. Go to [cyan]https://portal.azure.com[/cyan] → App registrations → New")
    console.print("        2. Name: anything (e.g. ForgeChannels)")
    console.print("        3. Supported account types: [bold]Accounts in any organizational directory[/bold]")
    console.print("        4. Redirect URI: [cyan]https://login.microsoftonline.com/common/oauth2/nativeclient[/cyan]")
    console.print("        5. API permissions → Add: [bold]Chat.ReadWrite, Chat.Create, User.ReadBasic.All[/bold] (Delegated)")
    console.print("        6. Copy the [bold]Application (client) ID[/bold]")
    console.print()

    client_id = Prompt.ask(
        "      Client ID (Enter to skip)",
        default="",
    )

    if not client_id:
        console.print(f"      {SKIP} Skipping Teams — you can set this up later.")
        return False

    set_config_value("microsoft_client_id", client_id.strip())
    console.print(f"      {CHECK} Saved to [dim]{CONFIG_PATH}[/dim]")
    console.print(f"      [dim]You'll authenticate via device code on first [bold]make run[/bold].[/dim]")
    return True


# ── Step 3: Anthropic API ───────────────────────────────────────────────────


def _setup_anthropic() -> bool:
    _step(3, "Anthropic API key (for AI conversations)")

    key = os.environ.get("ANTHROPIC_API_KEY") or get_config_value("anthropic_api_key")
    if key:
        console.print(f"      {CHECK} Anthropic API key found")
        return True

    console.print(f"      {CROSS} No Anthropic API key found.")
    console.print()
    console.print("      The AI engine auto-replies to prospect messages and books meetings.")
    console.print("      Get a key at [cyan]https://console.anthropic.com/settings/keys[/cyan]")
    console.print()

    key = Prompt.ask(
        "      API key (Enter to skip)",
        default="",
    )

    if not key:
        console.print(f"      {SKIP} Skipping AI — you can add this later.")
        return False

    set_config_value("anthropic_api_key", key.strip())
    console.print(f"      {CHECK} Saved to [dim]{CONFIG_PATH}[/dim]")
    return True


# ── Step 4: Contacts CSV ────────────────────────────────────────────────────

CSV_PATH = Path("demo_contacts.csv")
CSV_HEADER = "email,first_name,last_name,company,title,signal"
CSV_FIELDS = CSV_HEADER.split(",")

EXAMPLE_CONTACTS = [
    {
        "email": "jane.doe@example.com",
        "first_name": "Jane",
        "last_name": "Doe",
        "company": "Acme Corp",
        "title": "VP of Sales",
        "signal": "just raised a series b and is scaling their sales team",
    },
    {
        "email": "john.smith@example.com",
        "first_name": "John",
        "last_name": "Smith",
        "company": "Globex Inc",
        "title": "Head of Growth",
        "signal": "expanding into European markets",
    },
]


def _write_csv(rows: list[dict]) -> None:
    import csv as _csv
    with open(CSV_PATH, "w", newline="", encoding="utf-8") as f:
        writer = _csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def _add_contact_interactive(rows: list[dict]) -> bool:
    """Prompt for one contact. Returns True if added, False if skipped."""
    console.print("      [yellow]⚠  Use a different email than your sender account — you can't message yourself![/yellow]")
    console.print()

    email = Prompt.ask("      Email (Enter to skip)", default="")
    if not email:
        return False

    email = email.strip()
    first_name = Prompt.ask("      First name", default=email.split("@")[0].split(".")[0].capitalize())
    last_name = Prompt.ask("      Last name", default="Test")
    company = Prompt.ask("      Company", default="TestCorp")
    title = Prompt.ask("      Title", default="Founder")
    signal = Prompt.ask("      Signal (what they're up to)", default="scaling their sales team")

    rows.append({
        "email": email,
        "first_name": first_name,
        "last_name": last_name,
        "company": company,
        "title": title,
        "signal": signal,
    })
    console.print(f"      {CHECK} Added {first_name} {last_name} <{email}>")
    return True


def _check_contacts() -> bool:
    _step(4, "Contacts CSV")

    import csv as _csv

    # Load existing rows (if any)
    rows = []
    if CSV_PATH.exists():
        with open(CSV_PATH, newline="", encoding="utf-8") as f:
            rows = list(_csv.DictReader(f))

    if rows:
        console.print(f"      {CHECK} {CSV_PATH} — {len(rows)} contact(s)")
        for r in rows:
            console.print(f"         [dim]{r.get('first_name', '?')} {r.get('last_name', '?')} <{r.get('email', '?')}>[/dim]")
        console.print()

        choice = Prompt.ask(
            "      [bold](a)[/bold]dd contact, [bold](o)[/bold]verwrite, or [bold](k)[/bold]eep?",
            choices=["a", "o", "k"],
            default="k",
        )
        if choice == "k":
            return True
        if choice == "o":
            rows = []
        # "a" falls through to add more
        if choice == "a":
            console.print()
            while _add_contact_interactive(rows):
                console.print()
            _write_csv(rows)
            console.print(f"      {CHECK} Saved {len(rows)} contact(s) to [dim]{CSV_PATH}[/dim]")
            return True

    # No contacts yet — offer choices
    console.print(f"      No contacts configured yet.")
    console.print()
    console.print("      [bold](a)[/bold] Add your own test contact")
    console.print("      [bold](d)[/bold] Load demo contacts (fake @example.com data)")
    console.print("      [bold](s)[/bold] Skip for now")
    console.print()

    choice = Prompt.ask(
        "      Choose",
        choices=["a", "d", "s"],
        default="a",
    )

    if choice == "s":
        console.print(f"      {SKIP} Skipping — edit [bold]{CSV_PATH}[/bold] later.")
        _write_csv([])
        return False

    if choice == "d":
        _write_csv(EXAMPLE_CONTACTS)
        console.print(f"      {CHECK} Loaded {len(EXAMPLE_CONTACTS)} demo contacts")
        for r in EXAMPLE_CONTACTS:
            console.print(f"         [dim]{r['first_name']} {r['last_name']} <{r['email']}>[/dim]")
        console.print(f"      [dim]Note: @example.com emails won't actually deliver — replace with real ones to test.[/dim]")
        return True

    # choice == "a"
    console.print()
    while _add_contact_interactive(rows):
        console.print()

    if not rows:
        console.print(f"      {SKIP} No contacts added — edit [bold]{CSV_PATH}[/bold] later.")
        _write_csv([])
        return False

    _write_csv(rows)
    console.print(f"      {CHECK} Saved {len(rows)} contact(s) to [dim]{CSV_PATH}[/dim]")
    return True


# ── Summary ─────────────────────────────────────────────────────────────────


def run_setup():
    _header()

    CONFIG_DIR.mkdir(exist_ok=True)

    google = _setup_google()
    teams = _setup_teams()
    anthropic = _setup_anthropic()
    contacts = _check_contacts()

    # Summary
    console.print(f"\n  [bold]{'─' * 50}[/bold]")
    console.print(f"  [bold]Setup summary[/bold]\n")
    console.print(f"      Google Chat     {CHECK if google else CROSS}")
    console.print(f"      Microsoft Teams {CHECK if teams else CROSS}")
    console.print(f"      Anthropic AI    {CHECK if anthropic else CROSS}")
    console.print(f"      Contacts CSV    {CHECK if contacts else CROSS}")

    if google or teams:
        console.print(f"\n  [bold green]Ready to go![/bold green] Run [bold]make run[/bold] to start sending.")
        if not google and not teams:
            pass
        elif not google:
            console.print(f"  [dim]Google Chat skipped — only Teams will work.[/dim]")
        elif not teams:
            console.print(f"  [dim]Teams skipped — only Google Chat will work.[/dim]")
    else:
        console.print(f"\n  [yellow]You need at least one channel (Google Chat or Teams) to send messages.[/yellow]")
        console.print(f"  [dim]Re-run [bold]make setup[/bold] when you have credentials ready.[/dim]")

    console.print()


if __name__ == "__main__":
    run_setup()
