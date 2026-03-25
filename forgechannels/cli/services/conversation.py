"""Conversation monitor — poll for replies, generate AI responses, send them."""

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from cli.services.google_chat_service import list_messages, send_message
from cli.services.ai_service import generate_reply, classify_interest
from cli.services.calendar_service import create_meet_event
from cli.models import Contact


def _normalize_timestamp(ts: str) -> str:
    """Normalize an ISO timestamp so all values use 'Z' suffix for consistent comparison."""
    # handles edge cases: missing tz, +00:00 vs Z, microsecond precision drift
    if not ts:
        return ts
    ts = ts.replace("+00:00", "Z")
    return ts

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
    meeting_created: bool = False  # whether we already created a calendar event


def _extract_meeting_time(ai_client, conversation_history: list[dict]) -> dict | None:
    """Ask the AI to extract a proposed meeting date/time from the conversation.

    Returns dict with 'days_from_now', 'hour' (UTC), and 'human_time', or None.
    """
    now = datetime.now(timezone.utc)
    response = ai_client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=80,
        system=f"""Extract the most recently proposed or agreed meeting time from this conversation.
Today is {now.strftime('%A, %Y-%m-%d')} UTC. The prospect is likely in European timezone (UTC+2/+3).

Reply in EXACTLY this format: DAYS_FROM_NOW,HOUR_UTC,DESCRIPTION
- DAYS_FROM_NOW: integer, how many days from today (0=today, 1=tomorrow, etc.). If they say "next Tuesday" and today is {now.strftime('%A')}, count the days.
- HOUR_UTC: integer 0-23, the meeting hour converted to UTC. If they say "6" or "6pm" assume they mean 6pm their local time (so 16 UTC for UTC+2).
- DESCRIPTION: short human-readable time like "Tuesday, Apr 1 at 6pm"

Examples:
- "tuesday about 6" (today is {now.strftime('%A %b %d')}) → count days to next Tuesday, assume 6pm local (16 UTC) → e.g. 7,16,Tuesday Apr 1 at 6pm
- "thursday 10am" → count days, 10am local = 8 UTC → e.g. 3,8,Thursday Mar 28 at 10am

If no specific time was mentioned at all, reply: NONE""",
        messages=conversation_history,
    )
    result = response.content[0].text.strip()
    console.print(f"  [dim]Time extraction: {result}[/dim]")

    if "NONE" in result.upper():
        return None

    match = re.match(r"(\d+),(\d+),(.+)", result)
    if not match:
        return None

    return {
        "days_from_now": int(match.group(1)),
        "hour": int(match.group(2)),
        "human_time": match.group(3).strip(),
    }


def poll_and_respond(
    chat_service,
    ai_client,
    conversations: list[Conversation],
    sender_name: str,
    sender_id: str,
    creds=None,
    sender_email: str = "",
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
                _check_and_respond(chat_service, ai_client, conv, sender_name, sender_id, creds, sender_email)
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


def _check_and_respond(chat_service, ai_client, conv: Conversation, sender_name: str, sender_id: str, creds=None, sender_email: str = ""):
    """Check for new messages in a conversation and respond if needed."""
    messages = list_messages(chat_service, conv.space_name, page_size=10)

    if not messages:
        return

    last_seen = _normalize_timestamp(conv.last_seen_time)

    # Find new messages from the prospect (not from us), newer than last seen
    new_prospect_messages = []
    for msg in messages:
        sender = msg.get("sender", {})
        sender_name_id = sender.get("name", "")
        create_time = _normalize_timestamp(msg.get("createTime", ""))
        text = msg.get("text", "").strip()

        if sender_name_id == f"users/{sender_id}" or sender.get("type") == "BOT":
            continue

        if last_seen and create_time <= last_seen:
            continue

        if text:
            new_prospect_messages.append({"time": create_time, "text": text})

    if not new_prospect_messages:
        return

    # Batch all new messages together — combine into one reply instead of replying to each
    new_prospect_messages.sort(key=lambda m: m["time"])

    # Update last_seen to the latest message
    conv.last_seen_time = _normalize_timestamp(new_prospect_messages[-1]["time"])

    # Add all prospect messages to history
    for prospect_msg in new_prospect_messages:
        console.print(f"\n  [cyan]{conv.contact.email}[/cyan] replied: [white]{prospect_msg['text']}[/white]")
        conv.history.append({"role": "user", "content": prospect_msg["text"]})

    # Classify based on the latest message
    latest_text = new_prospect_messages[-1]["text"]
    interest = classify_interest(ai_client, latest_text)
    console.print(f"  [dim]Interest: {interest}[/dim]")

    # Handle not interested
    if interest == "not_interested":
        conv.status = "not_interested"
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
        conv.history.append({"role": "assistant", "content": reply})
        console.print(f"  [green]→[/green] {reply}")
        send_message(chat_service, conv.contact.email, reply)
        conv.status = "closed"
        return

    # For interested/booked — try to create calendar event if a time is mentioned
    meeting_note = ""
    if interest in ("interested", "booked") and not conv.meeting_created:
        meeting_result = _maybe_create_meeting(ai_client, creds, sender_email, conv)
        if meeting_result:
            conv.booking_url = meeting_result["meet_link"]
            conv.meeting_created = True
            meeting_note = (
                f"\n\n[SYSTEM: A calendar invite has been sent to {conv.contact.email} for "
                f"{meeting_result['human_time']}. The Meet link is {meeting_result['meet_link']}. "
                f"Share the link AND the date/time — e.g. 'nice, booked for {meeting_result['human_time']}. here's the link: {meeting_result['meet_link']}. talk soon']"
            )

    if interest == "booked" or conv.meeting_created:
        conv.status = "booked"
    elif interest == "interested":
        conv.status = "call_proposed"
    else:
        conv.status = "in_conversation"

    # If we created a meeting, inject a system note so the AI knows
    history_for_reply = list(conv.history)
    if meeting_note:
        history_for_reply.append({"role": "user", "content": meeting_note})

    reply = generate_reply(
        ai_client,
        history_for_reply,
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


def _maybe_create_meeting(ai_client, creds, sender_email: str, conv: Conversation) -> dict | None:
    """Try to extract a meeting time from conversation and create a calendar event.

    Returns dict with 'meet_link' and 'human_time', or None.
    """
    if not creds or not sender_email:
        console.print(f"  [yellow]![/yellow] No calendar credentials — can't create event")
        return None

    time_info = _extract_meeting_time(ai_client, conv.history)
    if not time_info:
        console.print(f"  [dim]No specific meeting time extracted[/dim]")
        return None

    try:
        event = create_meet_event(
            creds,
            attendee_email=conv.contact.email,
            sender_email=sender_email,
            summary=f"15 min call — {conv.contact.company}",
            days_from_now=time_info["days_from_now"],
            hour=time_info["hour"],
            duration_minutes=15,
        )
        meet_link = event["meet_link"]
        start_dt = datetime.fromisoformat(event["start_time"])
        time_str = start_dt.strftime("%A, %b %d at %H:%M UTC")
        console.print(f"  [green]✓[/green] Calendar event created: {time_str} → {meet_link}")
        return {
            "meet_link": meet_link,
            "human_time": time_info["human_time"],
        }
    except Exception as e:
        console.print(f"  [yellow]![/yellow] Calendar event creation failed: {e}")
        return None


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
