"""Conversation monitor — poll for replies, generate AI responses, send them."""

import time
from dataclasses import dataclass, field

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.services.google_chat_service import list_messages, send_message
from cli.services.ai_service import generate_reply, classify_interest
from cli.models import Contact

console = Console()


@dataclass
class Conversation:
    contact: Contact
    space_name: str
    booking_url: str
    history: list[dict] = field(default_factory=list)  # {"role": ..., "content": ...}
    status: str = "opener_sent"  # opener_sent, in_conversation, call_proposed, booked, closed
    last_seen_time: str = ""  # ISO timestamp of last processed message
    our_sender_id: str = ""


def poll_and_respond(
    chat_service,
    ai_client,
    conversations: list[Conversation],
    sender_name: str,
    sender_id: str,
    poll_interval: int = 10,
    max_rounds: int = 50,
):
    """Main conversation loop. Polls for new messages and auto-responds.

    Runs until all conversations are booked/closed or max_rounds reached.
    """
    console.print(
        Panel(
            f"Monitoring {len(conversations)} conversations for replies...\n"
            f"Polling every {poll_interval}s. Press Ctrl+C to stop.",
            title="Conversation Monitor",
            border_style="green",
        )
    )

    for round_num in range(max_rounds):
        active = [c for c in conversations if c.status not in ("booked", "closed")]
        if not active:
            console.print("\n[green]All conversations resolved.[/green]")
            break

        for conv in active:
            try:
                _check_and_respond(chat_service, ai_client, conv, sender_name, sender_id)
            except Exception as e:
                console.print(f"  [red]Error[/red] {conv.contact.email}: {e}")

        # Show status table
        if round_num % 3 == 0:
            _show_status(conversations)

        try:
            time.sleep(poll_interval)
        except KeyboardInterrupt:
            console.print("\n[yellow]Stopped monitoring.[/yellow]")
            break

    _show_status(conversations)


def _check_and_respond(chat_service, ai_client, conv: Conversation, sender_name: str, sender_id: str):
    """Check for new messages in a conversation and respond if needed."""
    messages = list_messages(chat_service, conv.space_name, page_size=10)

    if not messages:
        return

    # Find new messages from the prospect (not from us), newer than last seen
    new_prospect_messages = []
    for msg in messages:
        sender = msg.get("sender", {})
        sender_name_id = sender.get("name", "")

        # Skip our own messages
        if sender_name_id == f"users/{sender_id}" or sender.get("type") == "BOT":
            continue

        # Use createTime for timestamp comparison
        create_time = msg.get("createTime", "")
        if conv.last_seen_time and create_time <= conv.last_seen_time:
            continue

        text = msg.get("text", "").strip()
        if text:
            new_prospect_messages.append({"time": create_time, "text": text})

    if not new_prospect_messages:
        return

    # Process each new message (sorted by time)
    new_prospect_messages.sort(key=lambda m: m["time"])
    for prospect_msg in new_prospect_messages:
        conv.last_seen_time = prospect_msg["time"]
        prospect_text = prospect_msg["text"]

        console.print(f"\n  [cyan]{conv.contact.email}[/cyan] replied: [white]{prospect_text}[/white]")

        # Add to history
        conv.history.append({"role": "user", "content": prospect_text})

        # Classify interest
        interest = classify_interest(ai_client, prospect_text)
        console.print(f"  [dim]Interest: {interest}[/dim]")

        if interest == "not_interested":
            conv.status = "not_interested"
            # Still reply graciously — leave the door open
            reply = generate_reply(
                ai_client,
                conv.history,
                sender_name=sender_name,
                contact_name=conv.contact.first_name,
                contact_title=conv.contact.title,
                contact_company=conv.contact.company,
                signal=conv.contact.signal,
                booking_url=conv.booking_url,
            )
            # After sending the gracious reply, mark as closed
            conv.history.append({"role": "assistant", "content": reply})
            console.print(f"  [green]→[/green] {reply}")
            send_message(chat_service, conv.contact.email, reply)
            conv.status = "closed"
            return  # done with this conversation
        elif interest == "booked":
            conv.status = "booked"
            reply = generate_reply(
                ai_client,
                conv.history,
                sender_name=sender_name,
                contact_name=conv.contact.first_name,
                contact_title=conv.contact.title,
                contact_company=conv.contact.company,
                signal=conv.contact.signal,
                booking_url=conv.booking_url,
            )
        else:
            if interest == "interested":
                conv.status = "call_proposed"
            else:
                conv.status = "in_conversation"

            reply = generate_reply(
                ai_client,
                conv.history,
                sender_name=sender_name,
                contact_name=conv.contact.first_name,
                contact_title=conv.contact.title,
                contact_company=conv.contact.company,
                signal=conv.contact.signal,
                booking_url=conv.booking_url,
            )

        # Send the reply
        conv.history.append({"role": "assistant", "content": reply})
        console.print(f"  [green]→[/green] {reply}")

        send_message(chat_service, conv.contact.email, reply)


def _show_status(conversations: list[Conversation]):
    """Display current conversation status table."""
    table = Table(title="Conversation Status")
    table.add_column("Contact", style="cyan")
    table.add_column("Status")
    table.add_column("Messages", justify="right")

    status_styles = {
        "opener_sent": "[dim]Waiting...[/dim]",
        "in_conversation": "[yellow]Chatting[/yellow]",
        "call_proposed": "[blue]Call proposed[/blue]",
        "booked": "[green]Booked![/green]",
        "not_interested": "[red]Not interested[/red]",
        "closed": "[red]Closed[/red]",
    }

    for conv in conversations:
        status = status_styles.get(conv.status, conv.status)
        msg_count = len(conv.history)
        table.add_row(conv.contact.email, status, str(msg_count))

    console.print()
    console.print(table)
