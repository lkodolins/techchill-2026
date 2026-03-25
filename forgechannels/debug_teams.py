"""Debug Teams Graph API — test each step."""

import json
import sys
from cli.auth.config_store import get_config_value
from cli.services.teams_service import authenticate_teams
import requests

client_id = get_config_value("microsoft_client_id")
if not client_id:
    print("No microsoft_client_id in config. Run the CLI first.")
    sys.exit(1)

print(f"Client ID: {client_id}")
token = authenticate_teams(client_id)
print(f"Token: {token[:20]}...\n")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

test_email = sys.argv[1] if len(sys.argv) > 1 else "aksels.bermanis@tilde.ai"
print(f"Target: {test_email}\n")

# 1. Check /me
print("=== 1. /me ===")
r = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers)
print(f"  Status: {r.status_code}")
print(f"  Response: {json.dumps(r.json(), indent=2)[:500]}\n")

# 2. List existing chats
print("=== 2. List my chats ===")
r = requests.get("https://graph.microsoft.com/v1.0/me/chats?$top=5", headers=headers)
print(f"  Status: {r.status_code}")
if r.ok:
    chats = r.json().get("value", [])
    print(f"  Found {len(chats)} chats")
    for c in chats[:3]:
        print(f"    - {c['id'][:30]}... type={c.get('chatType')}")
else:
    print(f"  Error: {r.text[:300]}\n")

# 3. Try to create a 1:1 chat
print(f"\n=== 3. Create 1:1 chat with {test_email} ===")
body = {
    "chatType": "oneOnOne",
    "members": [
        {
            "@odata.type": "#microsoft.graph.aadUserConversationMember",
            "roles": ["owner"],
            "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{test_email}')",
        }
    ],
}
r = requests.post("https://graph.microsoft.com/v1.0/me/chats", headers=headers, json=body)
print(f"  Status: {r.status_code}")
print(f"  Response: {json.dumps(r.json(), indent=2)[:500]}")

if r.ok:
    chat_id = r.json()["id"]
    print(f"\n=== 4. Send message to chat {chat_id[:30]}... ===")
    r2 = requests.post(
        f"https://graph.microsoft.com/v1.0/me/chats/{chat_id}/messages",
        headers=headers,
        json={"body": {"content": "Test message from ForgeChannels debug script."}},
    )
    print(f"  Status: {r2.status_code}")
    print(f"  Response: {json.dumps(r2.json(), indent=2)[:500]}")
else:
    # Try /chats endpoint directly
    print(f"\n=== 4. Try POST /chats (without /me) ===")
    r2 = requests.post("https://graph.microsoft.com/v1.0/chats", headers=headers, json=body)
    print(f"  Status: {r2.status_code}")
    print(f"  Response: {json.dumps(r2.json(), indent=2)[:500]}")

print("\nDone.")
