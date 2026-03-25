"""Debug script — test each step of Google Chat sending."""

import json
import sys
from cli.auth.google_oauth import authenticate, get_user_email
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

creds = authenticate()
email = get_user_email(creds)
print(f"Authenticated as: {email}\n")

chat = build("chat", "v1", credentials=creds)

# Use first arg as test email, or default
test_email = sys.argv[1] if len(sys.argv) > 1 else email

print(f"=== Testing with: {test_email} ===\n")

# 1. List spaces to see if API works at all
print("1. Listing spaces...")
try:
    spaces = chat.spaces().list(pageSize=10).execute()
    print(f"   Found {len(spaces.get('spaces', []))} spaces:")
    for s in spaces.get("spaces", []):
        print(f"   - {s['name']} (type: {s.get('spaceType', '?')}, display: {s.get('displayName', 'DM')})")
except HttpError as e:
    print(f"   ERROR: {e.error_details}")

# 2. Try findDirectMessage
print(f"\n2. findDirectMessage for {test_email}...")
try:
    dm = chat.spaces().findDirectMessage(name=f"users/{test_email}").execute()
    print(f"   Found DM space: {json.dumps(dm, indent=2)}")
except HttpError as e:
    print(f"   ERROR {e.resp.status}: {e._get_reason()}")

# 3. Try spaces.setup to create DM
print(f"\n3. spaces.setup to create DM with {test_email}...")
try:
    setup_body = {
        "space": {"spaceType": "DIRECT_MESSAGE"},
        "memberships": [
            {"member": {"name": f"users/{test_email}", "type": "HUMAN"}}
        ],
    }
    space = chat.spaces().setup(body=setup_body).execute()
    print(f"   Created space: {json.dumps(space, indent=2)}")
    space_name = space["name"]
except HttpError as e:
    print(f"   ERROR {e.resp.status}: {e._get_reason()}")
    print(f"   Full error: {e.content.decode()}")
    space_name = None

# 4. Try sending a message if we got a space
if space_name:
    print(f"\n4. Sending test message to space {space_name}...")
    try:
        msg = chat.spaces().messages().create(
            parent=space_name,
            body={"text": "Test message from ForgeChannels debug script."},
        ).execute()
        print(f"   Message sent: {json.dumps(msg, indent=2)}")
    except HttpError as e:
        print(f"   ERROR {e.resp.status}: {e._get_reason()}")
        print(f"   Full error: {e.content.decode()}")
else:
    print("\n4. Skipped sending — no space created.")

print("\nDone.")
