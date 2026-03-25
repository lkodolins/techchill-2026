"""Debug — test Google Calendar event creation with Meet link."""

import json
import sys
from cli.auth.google_oauth import authenticate, get_user_email
from cli.services.calendar_service import create_meet_event

creds = authenticate()
sender = get_user_email(creds)
print(f"Authenticated as: {sender}\n")

attendee = sys.argv[1] if len(sys.argv) > 1 else sender
print(f"Creating event with attendee: {attendee}\n")

result = create_meet_event(creds, attendee_email=attendee, sender_email=sender)
print(json.dumps(result, indent=2))
print(f"\nMeet link: {result['meet_link']}")
print(f"Calendar link: {result['event_link']}")
