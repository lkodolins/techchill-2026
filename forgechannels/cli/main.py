"""ForgeChannels CLI — detect email provider, route to Google Chat or Teams."""

import csv
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt

from cli.auth.google_oauth import authenticate, get_user_email
from cli.auth.config_store import load_config, set_config_value, get_config_value
from cli.services.google_chat_service import get_chat_service, send_message
from cli.services.teams_service import authenticate_teams, send_teams_message
from cli.services.email_provider import detect_provider, provider_display_name
from cli.services.ai_service import create_client as create_ai_client
from cli.services.conversation import Conversation, poll_and_respond
from cli.models import Contact, MessageResult

app = typer.Typer(rich_markup_mode="rich")
console = Console()

MESSAGE_TEMPLATE = (
    "Hey {first_name} — saw {company} {signal}, pretty cool. "
    "Would you be up for a quick 15 min call sometime this week?"
)


# ── Helpers ──────────────────────────────────────────────────────────────────


def load_contacts(csv_path: str) -> list[Contact]:
    """Load contacts from a CSV file."""
    contacts = []
    with open(csv_path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            contacts.append(
                Contact(
                    email=row["email"],
                    first_name=row["first_name"],
                    last_name=row["last_name"],
                    company=row["company"],
                    title=row["title"],
                    signal=row.get("signal", ""),
                )
            )
    return contacts


def detect_providers(contacts: list[Contact]) -> None:
    """Detect email provider for each contact via MX lookup."""
    cache: dict[str, str] = {}
    for c in contacts:
        domain = c.email.split("@", 1)[1].lower()
        if domain not in cache:
            cache[domain] = detect_provider(c.email)
        c.provider = cache[domain]


def generate_message(contact: Contact) -> str:
    """Generate the outreach message for a contact."""
    return MESSAGE_TEMPLATE.format(
        first_name=contact.first_name,
        company=contact.company,
        signal=contact.signal.lower(),
    )


def step(n: int, title: str) -> None:
    """Print a formatted step header."""
    console.print(f"\n  [bold bright_blue]({n})[/bold bright_blue] [bold]{title}[/bold]")


# ── Setup / Auth ─────────────────────────────────────────────────────────────


def setup_anthropic() -> str | None:
    """Set up Anthropic API key. Returns the key or None."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY") or get_config_value("anthropic_api_key")
    if key:
        console.print(f"      [green]✓[/green] Anthropic API key found")
        return key

    console.print("\n      [bold]Anthropic API key needed[/bold] for AI-powered conversations.")
    console.print("      Get one at [cyan]https://console.anthropic.com/settings/keys[/cyan]\n")
    key = Prompt.ask("      API key (Enter to skip)", default="")
    if not key:
        console.print("      [dim]Skipping AI — no auto-replies.[/dim]")
        return None
    set_config_value("anthropic_api_key", key)
    console.print(f"      [green]✓[/green] Saved")
    return key


def setup_teams_auth() -> str | None:
    """Set up Teams authentication if needed. Returns access token or None."""
    client_id = get_config_value("microsoft_client_id")

    if not client_id:
        console.print("\n      [bold yellow]Microsoft Teams setup needed[/bold yellow]")
        console.print("      1. [cyan]https://portal.azure.com[/cyan] → App registrations → New")
        console.print("      2. Redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient")
        console.print("      3. Permissions: Chat.ReadWrite, Chat.Create (Delegated)")
        console.print("      4. Copy the Application (client) ID\n")

        client_id = Prompt.ask("      Client ID (Enter to skip Teams)", default="")
        if not client_id:
            return None
        set_config_value("microsoft_client_id", client_id)

    console.print("      Authenticating with Microsoft Teams...")
    try:
        token = authenticate_teams(client_id)
        console.print("      [green]✓[/green] Teams authenticated")
        return token
    except Exception as e:
        console.print(f"      [red]✗[/red] Teams auth failed: {e}")
        return None


# ── Display ──────────────────────────────────────────────────────────────────


def display_contacts(contacts: list[Contact]) -> None:
    """Show a rich table of loaded contacts with detected channels."""
    table = Table(show_lines=False, padding=(0, 1))
    table.add_column("#", style="dim", justify="right", width=3)
    table.add_column("Name", style="white")
    table.add_column("Email", style="cyan")
    table.add_column("Company", style="green")
    table.add_column("Channel", style="bold")

    for i, c in enumerate(contacts, 1):
        channel = provider_display_name(c.provider)
        if c.provider == "google":
            ch = f"[blue]{channel}[/blue]"
        elif c.provider == "microsoft":
            ch = f"[magenta]{channel}[/magenta]"
        else:
            ch = f"[dim]{channel}[/dim]"
        table.add_row(str(i), c.full_name, c.email, c.company, ch)

    console.print()
    console.print(table)


def display_channel_summary(
    google: list[Contact], teams: list[Contact], unknown: list[Contact],
) -> None:
    """Show channel breakdown inline."""
    parts = []
    if google:
        parts.append(f"[blue]{len(google)} Google Chat[/blue]")
    if teams:
        parts.append(f"[magenta]{len(teams)} Teams[/magenta]")
    if unknown:
        parts.append(f"[yellow]{len(unknown)} Unknown[/yellow] [dim](fallback: Chat → Teams)[/dim]")
    console.print("      " + "  ·  ".join(parts))


def preview_message(contacts: list[Contact]) -> None:
    """Show one example message preview."""
    if not contacts:
        return
    sample = contacts[0]
    msg = generate_message(sample)
    console.print()
    console.print(
        Panel(
            msg,
            title=f"[dim]Example →[/dim] [cyan]{sample.first_name} {sample.last_name}[/cyan] [dim]at[/dim] [green]{sample.company}[/green]",
            subtitle=f"[dim]{sample.title} · {provider_display_name(sample.provider)}[/dim]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )
    if len(contacts) > 1:
        console.print(f"      [dim]+{len(contacts) - 1} more personalized messages[/dim]")


def display_results(results: list[MessageResult]) -> tuple[int, int]:
    """Show send results table. Returns (sent, failed)."""
    table = Table(show_lines=False, padding=(0, 1))
    table.add_column("Name", style="white")
    table.add_column("Email", style="cyan")
    table.add_column("Channel")
    table.add_column("Status")

    sent = 0
    failed = 0
    for r in results:
        ch = "[blue]Chat[/blue]" if r.channel == "google_chat" else "[magenta]Teams[/magenta]"
        name = r.contact.full_name
        if r.success:
            sent += 1
            table.add_row(name, r.contact.email, ch, "[green]✓ Sent[/green]")
        else:
            failed += 1
            err = (r.error or "")[:40]
            table.add_row(name, r.contact.email, ch, f"[red]✗ {err}[/red]")

    console.print()
    console.print(table)
    console.print(f"\n      [bold green]{sent} sent[/bold green]  ·  [bold red]{failed} failed[/bold red]")
    return sent, failed


# ── Main Command ─────────────────────────────────────────────────────────────


@app.command()
def run(
    csv_file: str = typer.Option(
        "demo_contacts.csv", "--csv", "-c", help="Path to contacts CSV"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Preview everything without sending"
    ),
    no_ai: bool = typer.Option(
        False, "--no-ai", help="Skip AI conversation monitoring"
    ),
    client_secret: str = typer.Option(
        None, "--credentials", help="Path to Google OAuth client secret JSON"
    ),
):
    """Send personalized outreach via Google Chat & Microsoft Teams."""

    # ── Banner ──
    console.print()
    console.print(
        Panel(
            "[bold bright_blue]ForgeChannels[/bold bright_blue]\n"
            "[dim]Reach B2B prospects where they work — Google Chat & Microsoft Teams[/dim]",
            border_style="bright_blue",
            padding=(1, 2),
        )
    )

    # ── (1) Load contacts ──
    step(1, "Loading contacts")

    csv_path = Path(csv_file)
    if not csv_path.exists():
        console.print(f"      [red]✗[/red] File not found: [cyan]{csv_file}[/cyan]")
        console.print(f"      [dim]Expected columns: email, first_name, last_name, company, title, signal[/dim]")
        raise typer.Exit(1)

    contacts = load_contacts(str(csv_path))
    if not contacts:
        console.print(f"      [yellow]No contacts in {csv_file}.[/yellow]")
        raise typer.Exit(0)

    console.print(f"      [green]✓[/green] {len(contacts)} contacts loaded")

    # ── (2) Detect providers ──
    step(2, "Detecting email providers")

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as progress:
        progress.add_task("      Checking MX records...", total=None)
        detect_providers(contacts)

    google_contacts = [c for c in contacts if c.provider == "google"]
    teams_contacts = [c for c in contacts if c.provider == "microsoft"]
    unknown_contacts = [c for c in contacts if c.provider == "unknown"]

    display_channel_summary(google_contacts, teams_contacts, unknown_contacts)
    display_contacts(contacts)

    # ── (3) Preview ──
    step(3, "Message preview")
    sendable = contacts
    preview_message(sendable)

    if dry_run:
        console.print("\n      [yellow]Dry run — no messages sent.[/yellow]\n")
        raise typer.Exit(0)

    # ── (4) Authenticate ──
    step(4, "Authenticating")

    chat_service = None
    teams_token = None
    creds = None

    needs_google = bool(google_contacts or unknown_contacts)
    needs_teams = bool(teams_contacts or unknown_contacts)

    if needs_google:
        console.print("      [blue]Google Chat[/blue] — signing in...")
        try:
            creds = authenticate(client_secret)
            email = get_user_email(creds)
            console.print(f"      [green]✓[/green] Signed in as [cyan]{email}[/cyan]")
            chat_service = get_chat_service(creds)
        except Exception as e:
            console.print(f"      [red]✗[/red] Google auth failed: {e}")

    if needs_teams:
        teams_token = setup_teams_auth()

    ai_client = None
    if not no_ai:
        console.print("      [dim]AI conversation engine...[/dim]")
        anthropic_key = setup_anthropic()
        ai_client = create_ai_client(anthropic_key) if anthropic_key else None

    if not chat_service and not teams_token:
        console.print("\n      [red]No channels authenticated — cannot send.[/red]\n")
        raise typer.Exit(1)

    # ── (5) Send ──
    step(5, "Sending messages")

    results: list[MessageResult] = []

    def try_google_chat(contact: Contact, msg_text: str) -> MessageResult:
        result = MessageResult(contact=contact, channel="google_chat")
        response = send_message(chat_service, contact.email, msg_text)
        result.success = True
        result.message_id = response.get("name")
        result.space_name = response.get("space", {}).get("name")
        return result

    def try_teams(contact: Contact, msg_text: str) -> MessageResult:
        result = MessageResult(contact=contact, channel="teams")
        response = send_teams_message(teams_token, contact.email, msg_text)
        result.success = True
        result.message_id = response.get("id")
        return result

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console, transient=True) as progress:
        task = progress.add_task("      Sending...", total=len(sendable))

        for contact in sendable:
            msg_text = generate_message(contact)

            if contact.provider == "google":
                progress.update(task, description=f"      [blue]Chat[/blue] → {contact.first_name}")
                try:
                    results.append(try_google_chat(contact, msg_text))
                except Exception as e:
                    results.append(MessageResult(contact=contact, channel="google_chat", error=str(e)))

            elif contact.provider == "microsoft":
                progress.update(task, description=f"      [magenta]Teams[/magenta] → {contact.first_name}")
                try:
                    results.append(try_teams(contact, msg_text))
                except Exception as e:
                    results.append(MessageResult(contact=contact, channel="teams", error=str(e)))

            else:
                progress.update(task, description=f"      [yellow]Chat?[/yellow] → {contact.first_name}")
                sent = False
                if chat_service:
                    try:
                        results.append(try_google_chat(contact, msg_text))
                        sent = True
                    except Exception:
                        pass

                if not sent and teams_token:
                    progress.update(task, description=f"      [yellow]Teams?[/yellow] → {contact.first_name}")
                    try:
                        results.append(try_teams(contact, msg_text))
                        sent = True
                    except Exception as e:
                        results.append(MessageResult(contact=contact, channel="teams", error=f"Both failed: {e}"))

                if not sent and not teams_token:
                    results.append(MessageResult(contact=contact, channel="google_chat", error="Chat failed, no Teams fallback"))

            progress.advance(task)

    # ── (6) Results ──
    step(6, "Results")
    sent_count, failed_count = display_results(results)

    # ── (7) Conversation monitor ──
    successful_chat_results = [r for r in results if r.success and r.channel == "google_chat" and r.space_name]

    if successful_chat_results and ai_client and chat_service:
        step(7, "Conversation monitor")
        console.print(f"      [dim]Watching {len(successful_chat_results)} conversations for replies...[/dim]")

        sender_email = get_user_email(creds)

        from datetime import datetime, timezone
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

        conversations = []
        for r in successful_chat_results:
            conv = Conversation(
                contact=r.contact,
                space_name=r.space_name,
                booking_url="",
                last_seen_time=now_iso,
            )
            conv.history.append({
                "role": "assistant",
                "content": generate_message(r.contact),
            })
            conversations.append(conv)

        from googleapiclient.discovery import build
        oauth_service = build("oauth2", "v2", credentials=creds)
        user_info = oauth_service.userinfo().get().execute()
        sender_id = user_info.get("id", "")

        poll_and_respond(
            chat_service=chat_service,
            ai_client=ai_client,
            conversations=conversations,
            sender_name=sender_email.split("@")[0],
            sender_id=sender_id,
            creds=creds,
            sender_email=sender_email,
        )
    elif not ai_client and sent_count > 0:
        console.print("\n      [dim]AI disabled — no conversation monitoring.[/dim]")

    console.print()


if __name__ == "__main__":
    app()
