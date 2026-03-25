"""Debug Teams — try creating chat with both members explicitly."""

import json
import sys

import requests

from cli.auth.config_store import get_config_value
from cli.services.teams_service import (
    EXTERNAL_USERS_KEY,
    TeamsRecipientResolutionError,
    _find_or_create_chat,
    authenticate_teams,
)

client_id = get_config_value("microsoft_client_id")
token = authenticate_teams(client_id)
headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}

# Get my info
me = requests.get("https://graph.microsoft.com/v1.0/me", headers=headers).json()
my_id = me["id"]
my_email = me["userPrincipalName"]
print(f"Me: {my_email} ({my_id})\n")

test_email = sys.argv[1] if len(sys.argv) > 1 else "aksels.bergmanis@tilde.com"

# Check if Teams is actually provisioned
print("=== Check Teams service ===")
r = requests.get("https://graph.microsoft.com/v1.0/me/teamwork", headers=headers)
print(f"  Status: {r.status_code}")
print(f"  Response: {json.dumps(r.json(), indent=2)[:500]}\n")

# Check if target user exists in directory
print(f"=== Lookup {test_email} ===")
r = requests.get(f"https://graph.microsoft.com/v1.0/users/{test_email}", headers=headers)
print(f"  Status: {r.status_code}")
print(f"  Response: {json.dumps(r.json(), indent=2)[:500]}\n")

print("=== Create chat ===")
try:
    chat_id = _find_or_create_chat(token, test_email)
    print("  Status: OK")
    print(f"  Chat ID: {chat_id}")

    print("\n=== Send message ===")
    r2 = requests.post(
        f"https://graph.microsoft.com/v1.0/me/chats/{chat_id}/messages",
        headers=headers,
        json={"body": {"content": "Test from ForgeChannels!"}},
    )
    print(f"  Status: {r2.status_code}")
    print(f"  Response: {json.dumps(r2.json(), indent=2)[:500]}")
except TeamsRecipientResolutionError as exc:
    print("  Status: blocked before POST /chats")
    print(f"  Reason: {exc}")
    print("  Example config:")
    print(
        json.dumps(
            {
                EXTERNAL_USERS_KEY: {
                    test_email: {
                        "user_id": "<external-entra-object-id>",
                        "tenant_id": "<external-tenant-id>",
                    }
                }
            },
            indent=2,
        )
    )
except requests.HTTPError as exc:
    response = exc.response
    print(f"  Status: {response.status_code if response is not None else 'HTTP error'}")
    if response is not None:
        print(f"  Response: {response.text[:500]}")
    else:
        print(f"  Error: {exc}")

print("\nDone.")
