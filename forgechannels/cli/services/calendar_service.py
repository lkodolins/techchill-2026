"""Google Calendar — create events with Google Meet links."""

from datetime import datetime, timedelta, timezone

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


def get_calendar_service(creds: Credentials):
    """Build the Google Calendar API service client."""
    return build("calendar", "v3", credentials=creds)


def create_meet_event(
    creds: Credentials,
    attendee_email: str,
    sender_email: str,
    summary: str = "Quick intro call — ForgeChannels",
    description: str = "Looking forward to connecting!",
    duration_minutes: int = 15,
    days_from_now: int = 2,
    hour: int = 10,
) -> dict:
    """Create a Google Calendar event with a Google Meet link.

    Returns dict with: event_link, meet_link, start_time, event_id
    """
    service = get_calendar_service(creds)

    # Schedule for `days_from_now` at `hour`:00 UTC
    start = datetime.now(timezone.utc).replace(
        hour=hour, minute=0, second=0, microsecond=0
    ) + timedelta(days=days_from_now)
    end = start + timedelta(minutes=duration_minutes)

    event_body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start.isoformat(),
            "timeZone": "UTC",
        },
        "end": {
            "dateTime": end.isoformat(),
            "timeZone": "UTC",
        },
        "attendees": [
            {"email": attendee_email},
            {"email": sender_email},
        ],
        "conferenceData": {
            "createRequest": {
                "requestId": f"forge-{attendee_email}-{int(start.timestamp())}",
                "conferenceSolutionKey": {"type": "hangoutsMeet"},
            }
        },
        "reminders": {
            "useDefault": False,
            "overrides": [
                {"method": "popup", "minutes": 10},
            ],
        },
    }

    event = service.events().insert(
        calendarId="primary",
        body=event_body,
        conferenceDataVersion=1,
        sendUpdates="all",  # sends invite email to attendee
    ).execute()

    meet_link = ""
    if event.get("conferenceData", {}).get("entryPoints"):
        for ep in event["conferenceData"]["entryPoints"]:
            if ep.get("entryPointType") == "video":
                meet_link = ep["uri"]
                break

    return {
        "event_id": event["id"],
        "event_link": event.get("htmlLink", ""),
        "meet_link": meet_link,
        "start_time": start.isoformat(),
        "summary": summary,
    }


def generate_meet_link(creds: Credentials, attendee_email: str, sender_email: str) -> str:
    """Quick helper — create event and return just the Meet link."""
    result = create_meet_event(creds, attendee_email, sender_email)
    return result.get("meet_link") or result.get("event_link", "")
