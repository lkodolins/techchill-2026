"""Debug script — test Google Chat API calls and show full errors."""

from cli.auth.google_oauth import authenticate, get_user_email
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json

creds = authenticate()
email = get_user_email(creds)
print(f"Authenticated as: {email}\n")

chat = build("chat", "v1", credentials=creds)

test_email = "lkodolins@gmail.com"

# Test 1: List existing spaces
print("=== Listing existing spaces ===")
try:
    spaces = chat.spaces().list(pageSize=10).execute()
    for s in spaces.get("spaces", []):
        print(f"  {s['name']} — type: {s.get('spaceType')} — {s.get('displayName', '(DM)')}")
    if not spaces.get("spaces"):
        print("  (no spaces found)")
except HttpError as e:
    print(f"  ERROR: {e.status_code} {e.reason}")
    print(f"  {e.error_details}")

# Test 2: findDirectMessage
print(f"\n=== findDirectMessage for {test_email} ===")
try:
    dm = chat.spaces().findDirectMessage(name=f"users/{test_email}").execute()
    print(f"  Found: {json.dumps(dm, indent=2)}")
except HttpError as e:
    print(f"  ERROR: {e.status_code} {e.reason}")
    print(f"  {json.dumps(json.loads(e.content), indent=2)}")

# Test 3: spaces.setup
print(f"\n=== spaces.setup DM with {test_email} ===")
try:
    space = chat.spaces().setup(body={
        "space": {"spaceType": "DIRECT_MESSAGE"},
        "memberships": [{
            "member": {"name": f"users/{test_email}", "type": "HUMAN"},
        }],
    }).execute()
    print(f"  Created: {json.dumps(space, indent=2)}")
except HttpError as e:
    print(f"  ERROR: {e.status_code} {e.reason}")
    print(f"  {json.dumps(json.loads(e.content), indent=2)}")
