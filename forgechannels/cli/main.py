"""ForgeChannels CLI — detect email provider, route to Google Chat or Teams."""

import csv
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from rich.prompt import Prompt, Confirm

from cli.auth.google_oauth import authenticate, get_user_email
from cli.auth.config_store import load_config, set_config_value, get_config_value
from cli.services.google_chat_service import get_chat_service, send_message
from cli.services.teams_service import authenticate_teams, send_teams_message
from cli.services.email_provider import detect_provider, provider_display_name
from cli.services.calendar_service import create_meet_event
from cli.services.ai_service import create_client as create_ai_client
from cli.services.conversation import Conversation, poll_and_respond
from cli.models import Contact, MessageResult

app = typer.Typer()
console = Console()

MESSAGE_TEMPLATE = (
    "Hey {first_name}, I saw {company} recently {signal} — nice work. "
    "Would love to chat about how we could help you grow even faster. "
    "If you're open to it, here's a quick link to grab a time: {booking_url}"
)


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
    # Cache by domain so we don't re-lookup
    cache: dict[str, str] = {}
    for c in contacts:
        domain = c.email.split("@", 1)[1].lower()
        if domain not in cache:
            cache[domain] = detect_provider(c.email)
        c.provider = cache[domain]


def display_contacts(contacts: list[Contact]) -> None:
    """Show a rich table of loaded contacts with detected channels."""
    table = Table(title="Contacts & Detected Channels")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Company", style="green")
    table.add_column("Channel", style="bold")

    for c in contacts:
        channel = provider_display_name(c.provider)
        if c.provider == "google":
            style = "[blue]"
        elif c.provider == "microsoft":
            style = "[magenta]"
        else:
            style = "[dim]"
        table.add_row(c.email, c.full_name, c.company, f"{style}{channel}")

    console.print(table)


def generate_message(contact: Contact, booking_url: str = "") -> str:
    """Generate the outreach message for a contact."""
    return MESSAGE_TEMPLATE.format(
        first_name=contact.first_name,
        company=contact.company,
        signal=contact.signal.lower(),
        booking_url=booking_url or "https://www.google.com",
    )


def preview_messages(contacts: list[Contact]) -> None:
    """Show message previews grouped by channel."""
    console.print("\n[bold]Message Previews:[/bold]\n")
    for contact in contacts:
        msg = generate_message(contact)
        channel = provider_display_name(contact.provider)
        border = "blue" if contact.provider == "google" else "magenta" if contact.provider == "microsoft" else "dim"
        console.print(
            Panel(
                msg,
                title=f"[cyan]{contact.email}[/cyan]  →  [{border}]{channel}[/{border}]",
                subtitle=f"{contact.full_name} — {contact.title} at {contact.company}",
                border_style=border,
            )
        )


def setup_anthropic() -> str | None:
    """Set up Anthropic API key. Returns the key or None."""
    import os
    key = os.environ.get("ANTHROPIC_API_KEY") or get_config_value("anthropic_api_key")
    if key:
        console.print(f"  [green]✓[/green] Anthropic API key found")
        return key

    console.print("\n[bold]Anthropic API key needed[/bold] for AI-powered conversation.")
    console.print("  Get one at [cyan]https://console.anthropic.com/settings/keys[/cyan]\n")
    key = Prompt.ask("Anthropic API key (or Enter to skip AI)", default="")
    if not key:
        return None
    set_config_value("anthropic_api_key", key)
    console.print(f"  [green]✓[/green] Saved\n")
    return key


def setup_teams_auth() -> str | None:
    """Set up Teams authentication if needed. Returns access token or None."""
    client_id = get_config_value("microsoft_client_id")

    if not client_id:
        console.print("\n[bold yellow]Microsoft Teams setup needed[/bold yellow]")
        console.print("To send Teams messages, you need an Azure app registration.")
        console.print("  1. Go to [cyan]https://portal.azure.com[/cyan] → App registrations → New")
        console.print("  2. Add redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient")
        console.print("  3. API permissions: Chat.ReadWrite, Chat.Create (Delegated)")
        console.print("  4. Copy the Application (client) ID\n")

        client_id = Prompt.ask("Azure App Client ID (or Enter to skip Teams)", default="")
        if not client_id:
            return None
        set_config_value("microsoft_client_id", client_id)

    console.print("  Authenticating with Microsoft Teams...")
    try:
        token = authenticate_teams(client_id)
        console.print("  [green]✓[/green] Teams authenticated\n")
        return token
    except Exception as e:
        console.print(f"  [red]✗[/red] Teams auth failed: {e}\n")
        return None


@app.command()
def run(
    csv_file: str = typer.Option(
        "demo_contacts.csv", "--csv", "-c", help="Path to contacts CSV file"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", "-d", help="Preview messages without sending"
    ),
    client_secret: str = typer.Option(
        None, "--credentials", help="Path to Google OAuth client secret JSON"
    ),
):
    """ForgeChannels — cold outreach via Google Chat & Teams."""

    console.print(
        Panel(
            "[bold white]ForgeChannels[/bold white]\n"
            "Cold outreach via Google Chat & Microsoft Teams — reach prospects where they work.",
            border_style="bright_blue",
        )
    )

    # Step 1: Load contacts & detect providers
    console.print(f"\n[bold]Step 1:[/bold] Loading contacts from [cyan]{csv_file}[/cyan]")
    csv_path = Path(csv_file)
    if not csv_path.exists():
        console.print(f"  [red]✗[/red] File not found: {csv_file}")
        raise typer.Exit(1)

    contacts = load_contacts(str(csv_path))
    console.print(f"  [green]✓[/green] {len(contacts)} contacts loaded\n")

    # Step 2: Detect email providers
    console.print("[bold]Step 2:[/bold] Detecting email providers (MX lookup)...")
    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Checking MX records...", total=None)
        detect_providers(contacts)
        progress.update(task, description="Done")

    google_contacts = [c for c in contacts if c.provider == "google"]
    teams_contacts = [c for c in contacts if c.provider == "microsoft"]
    unknown_contacts = [c for c in contacts if c.provider == "unknown"]

    console.print(f"  [blue]Google Chat:[/blue] {len(google_contacts)} contacts")
    console.print(f"  [magenta]Teams:[/magenta]       {len(teams_contacts)} contacts")
    if unknown_contacts:
        console.print(f"  [yellow]Unknown:[/yellow]     {len(unknown_contacts)} contacts (will try Google Chat → Teams fallback)")
    console.print()

    display_contacts(contacts)

    # Step 3: Preview messages
    console.print("\n[bold]Step 3:[/bold] Message previews")
    sendable = contacts  # all contacts are sendable now (unknown = fallback)
    preview_messages(sendable)

    if dry_run:
        console.print("\n[yellow]Dry run — no messages sent.[/yellow]")
        raise typer.Exit(0)

    if not sendable:
        console.print("\n[yellow]No contacts to send to.[/yellow]")
        raise typer.Exit(0)

    # Step 4: Authenticate for each channel that has contacts
    # Always auth Google Chat (needed for unknown fallback too)
    console.print(f"\n[bold]Step 4:[/bold] Authentication\n")

    chat_service = None
    teams_token = None
    creds = None

    needs_google = bool(google_contacts or unknown_contacts)
    needs_teams = bool(teams_contacts or unknown_contacts)

    if needs_google:
        console.print("[blue]Google Chat:[/blue] Signing in...")
        try:
            creds = authenticate(client_secret)
            email = get_user_email(creds)
            console.print(f"  [green]✓[/green] Authenticated as [cyan]{email}[/cyan]")
            chat_service = get_chat_service(creds)
        except Exception as e:
            console.print(f"  [red]✗[/red] Google auth failed: {e}")

    if needs_teams:
        teams_token = setup_teams_auth()

    # Anthropic API key for conversation AI
    console.print("[bold]AI:[/bold] Setting up conversation engine...")
    anthropic_key = setup_anthropic()
    ai_client = create_ai_client(anthropic_key) if anthropic_key else None

    # Step 5: Confirm and send
    if not chat_service and not teams_token:
        console.print("\n[red]No channels authenticated. Nothing to send.[/red]")
        raise typer.Exit(1)

    total = len(sendable)
    console.print()
    if not Confirm.ask(f"[bold]Send {total} messages?[/bold]"):
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    # Step 5a: Create Google Meet links for each contact
    console.print(f"\n[bold]Step 5:[/bold] Creating calendar events + Meet links\n")
    meet_links: dict[str, str] = {}  # email -> meet link

    if creds:
        sender_email = get_user_email(creds)
        with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
            cal_task = progress.add_task("Scheduling...", total=len(sendable))
            for contact in sendable:
                progress.update(cal_task, description=f"Creating event for {contact.email}...")
                try:
                    event = create_meet_event(
                        creds,
                        attendee_email=contact.email,
                        sender_email=sender_email,
                        summary=f"Quick chat — {contact.company}",
                    )
                    meet_links[contact.email] = event["meet_link"]
                    # Parse and display the event time
                    from datetime import datetime as dt
                    start_dt = dt.fromisoformat(event["start_time"])
                    time_str = start_dt.strftime("%b %d, %H:%M UTC")
                    console.print(f"  [green]✓[/green] {contact.email} → {event['meet_link']}  [dim]({time_str})[/dim]")
                except Exception as e:
                    console.print(f"  [yellow]![/yellow] {contact.email} — calendar failed: {e}")
                progress.advance(cal_task)
    console.print()

    # Step 5b: Send messages
    console.print(f"[bold]Step 6:[/bold] Sending messages\n")
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

    with Progress(SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console) as progress:
        task = progress.add_task("Sending...", total=total)

        for contact in sendable:
            booking_url = meet_links.get(contact.email, "https://www.google.com")
            msg_text = generate_message(contact, booking_url=booking_url)

            if contact.provider == "google":
                # Google Chat only
                progress.update(task, description=f"[blue]Chat[/blue] → {contact.email}")
                try:
                    results.append(try_google_chat(contact, msg_text))
                except Exception as e:
                    results.append(MessageResult(contact=contact, channel="google_chat", error=str(e)))

            elif contact.provider == "microsoft":
                # Teams only
                progress.update(task, description=f"[magenta]Teams[/magenta] → {contact.email}")
                try:
                    results.append(try_teams(contact, msg_text))
                except Exception as e:
                    results.append(MessageResult(contact=contact, channel="teams", error=str(e)))

            else:
                # Unknown: try Google Chat first, fall back to Teams
                progress.update(task, description=f"[yellow]Chat?[/yellow] → {contact.email}")
                sent = False
                if chat_service:
                    try:
                        results.append(try_google_chat(contact, msg_text))
                        sent = True
                    except Exception:
                        pass  # fall through to Teams

                if not sent and teams_token:
                    progress.update(task, description=f"[yellow]Teams?[/yellow] → {contact.email}")
                    try:
                        results.append(try_teams(contact, msg_text))
                        sent = True
                    except Exception as e:
                        results.append(MessageResult(contact=contact, channel="teams", error=f"Both channels failed: {e}"))

                if not sent and not teams_token:
                    results.append(MessageResult(contact=contact, channel="google_chat", error="Google Chat failed, no Teams auth to fall back"))

            progress.advance(task)

    # Step 6: Summary
    console.print("\n[bold]Results:[/bold]\n")

    summary = Table(title="Send Summary")
    summary.add_column("Email", style="cyan")
    summary.add_column("Channel")
    summary.add_column("Status")
    summary.add_column("Details", style="dim")

    sent = 0
    failed = 0
    for r in results:
        ch = "[blue]Chat[/blue]" if r.channel == "google_chat" else "[magenta]Teams[/magenta]"
        if r.success:
            sent += 1
            summary.add_row(r.contact.email, ch, "[green]✓ Sent[/green]", r.message_id or "")
        else:
            failed += 1
            summary.add_row(r.contact.email, ch, "[red]✗ Failed[/red]", (r.error or "")[:60])

    console.print(summary)
    console.print(
        f"\n[bold green]{sent} sent[/bold green] / [bold red]{failed} failed[/bold red]"
    )

    # Step 7: Conversation monitoring (Google Chat only, needs AI)
    successful_chat_results = [r for r in results if r.success and r.channel == "google_chat" and r.space_name]

    if successful_chat_results and ai_client and chat_service:
        console.print()
        console.print("[bold]Starting conversation monitor...[/bold]\n")

        sender_email = get_user_email(creds)

        # Build conversation objects
        conversations = []
        for r in successful_chat_results:
            booking_url = meet_links.get(r.contact.email, "https://www.google.com")
            conv = Conversation(
                contact=r.contact,
                space_name=r.space_name,
                booking_url=booking_url,
            )
            # Add the opener we sent as first message in history
            conv.history.append({
                "role": "assistant",
                "content": generate_message(r.contact, booking_url=booking_url),
            })
            conversations.append(conv)

        # Get our sender user ID for filtering our own messages
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
        )


if __name__ == "__main__":
    app()
