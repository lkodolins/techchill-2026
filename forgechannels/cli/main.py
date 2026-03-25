"""ForgeChannels CLI — send Google Chat outreach from a CSV of contacts."""

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
from cli.auth.config_store import load_config, set_config_value
from cli.services.google_chat_service import get_chat_service, send_message
from cli.models import Contact, MessageResult

app = typer.Typer()
console = Console()

BOOKING_URL = "https://www.google.com"

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


def display_contacts(contacts: list[Contact]) -> None:
    """Show a rich table of loaded contacts."""
    table = Table(title="Loaded Contacts")
    table.add_column("Email", style="cyan")
    table.add_column("Name", style="white")
    table.add_column("Company", style="green")
    table.add_column("Title", style="yellow")
    table.add_column("Signal", style="dim")

    for c in contacts:
        table.add_row(c.email, c.full_name, c.company, c.title, c.signal[:50])

    console.print(table)


def generate_message(contact: Contact) -> str:
    """Generate the outreach message for a contact."""
    return MESSAGE_TEMPLATE.format(
        first_name=contact.first_name,
        company=contact.company,
        signal=contact.signal.lower(),
        booking_url=BOOKING_URL,
    )


def preview_messages(contacts: list[Contact]) -> None:
    """Show message previews in rich panels."""
    console.print("\n[bold]Message Previews:[/bold]\n")
    for contact in contacts:
        msg = generate_message(contact)
        console.print(
            Panel(
                msg,
                title=f"[cyan]{contact.email}[/cyan]",
                subtitle=f"{contact.full_name} — {contact.title} at {contact.company}",
                border_style="blue",
            )
        )


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
    """ForgeChannels — cold outreach via Google Chat."""

    console.print(
        Panel(
            "[bold white]ForgeChannels[/bold white]\n"
            "Cold outreach via Google Chat — one command to start the conversation.",
            border_style="bright_blue",
        )
    )

    # Step 1: Authenticate with Google
    console.print("\n[bold]Step 1:[/bold] Sign in with Google")
    try:
        creds = authenticate(client_secret)
        email = get_user_email(creds)
        console.print(f"  [green]✓[/green] Authenticated as [cyan]{email}[/cyan]\n")
    except FileNotFoundError as e:
        console.print(f"  [red]✗[/red] {e}")
        raise typer.Exit(1)
    except Exception as e:
        console.print(f"  [red]✗[/red] Authentication failed: {e}")
        raise typer.Exit(1)

    # Step 2: Load contacts
    console.print(f"[bold]Step 2:[/bold] Loading contacts from [cyan]{csv_file}[/cyan]")
    csv_path = Path(csv_file)
    if not csv_path.exists():
        console.print(f"  [red]✗[/red] File not found: {csv_file}")
        raise typer.Exit(1)

    contacts = load_contacts(str(csv_path))
    console.print(f"  [green]✓[/green] {len(contacts)} contacts loaded\n")
    display_contacts(contacts)

    # Step 3: Preview messages
    console.print("\n[bold]Step 3:[/bold] Message previews")
    preview_messages(contacts)

    if dry_run:
        console.print("\n[yellow]Dry run — no messages sent.[/yellow]")
        raise typer.Exit(0)

    # Step 4: Confirm and send
    console.print()
    if not Confirm.ask(
        f"[bold]Send {len(contacts)} messages via Google Chat?[/bold]"
    ):
        console.print("[yellow]Cancelled.[/yellow]")
        raise typer.Exit(0)

    console.print(f"\n[bold]Step 4:[/bold] Sending messages\n")
    chat_service = get_chat_service(creds)
    results: list[MessageResult] = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Sending...", total=len(contacts))

        for contact in contacts:
            progress.update(task, description=f"Sending to {contact.email}...")
            msg_text = generate_message(contact)

            result = MessageResult(contact=contact)
            try:
                response = send_message(chat_service, contact.email, msg_text)
                result.success = True
                result.message_id = response.get("name")
                result.space_name = response.get("space", {}).get("name")
            except Exception as e:
                result.error = str(e)

            results.append(result)
            progress.advance(task)

    # Step 5: Summary
    console.print("\n[bold]Results:[/bold]\n")

    summary = Table(title="Send Summary")
    summary.add_column("Email", style="cyan")
    summary.add_column("Status")
    summary.add_column("Details", style="dim")

    sent = 0
    failed = 0
    for r in results:
        if r.success:
            sent += 1
            summary.add_row(r.contact.email, "[green]✓ Sent[/green]", r.message_id or "")
        else:
            failed += 1
            summary.add_row(
                r.contact.email, "[red]✗ Failed[/red]", (r.error or "")[:60]
            )

    console.print(summary)
    console.print(
        f"\n[bold green]{sent} sent[/bold green] / [bold red]{failed} failed[/bold red]"
    )


if __name__ == "__main__":
    app()
