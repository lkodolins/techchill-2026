#!/usr/bin/env python3
"""
Send a Microsoft Teams direct message to contacts detected as Outlook/M365 users.

Requires an Azure app registration with:
  - Delegated permission: Chat.ReadWrite, Chat.Create
  - Auth: Device code flow (no web server needed)

Setup:
  1. Go to portal.azure.com → App registrations → New registration
  2. Add redirect URI: https://login.microsoftonline.com/common/oauth2/nativeclient
  3. Under API permissions → Add: Chat.ReadWrite, Chat.Create (Delegated)
  4. Copy the Application (client) ID

Usage:
  python send_teams_message.py --csv demo_contacts.csv --client-id <azure-app-client-id>
  python send_teams_message.py --csv demo_contacts.csv --client-id <id> --message "Hey {first_name}, ..."
  python send_teams_message.py --csv demo_contacts.csv --client-id <id> --dry-run
"""

import argparse
import csv
import json
import pathlib
import sys
import time
import webbrowser

import requests

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
DEVICE_CODE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/devicecode"
TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
SCOPES = "Chat.ReadWrite Chat.Create User.ReadBasic.All offline_access"

TOKEN_CACHE = pathlib.Path.home() / ".forgechannels" / "teams_token.json"

DEFAULT_MESSAGE = (
    "Hey {first_name}, hope this finds you well! "
    "I came across your work at {company} and wanted to reach out directly. "
    "We're helping teams like yours with AI-powered outreach — would love to show you what we've built. "
    "Open to a quick 15-min chat this week?"
)

OUTLOOK_PROVIDERS = {"Microsoft 365 / Outlook"}


# ── Auth ──────────────────────────────────────────────────────────────────────

def load_cached_token() -> dict | None:
    if TOKEN_CACHE.exists():
        data = json.loads(TOKEN_CACHE.read_text())
        if time.time() < data.get("expires_at", 0) - 60:
            return data
        # Try refresh
        if "refresh_token" in data:
            return refresh_token(data["refresh_token"], data.get("client_id"))
    return None


def save_token(data: dict, client_id: str) -> None:
    data["expires_at"] = time.time() + data.get("expires_in", 3600)
    data["client_id"] = client_id
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(json.dumps(data, indent=2))


def refresh_token(refresh_tok: str, client_id: str) -> dict | None:
    resp = requests.post(TOKEN_URL, data={
        "client_id": client_id,
        "grant_type": "refresh_token",
        "refresh_token": refresh_tok,
        "scope": SCOPES,
    })
    if resp.ok:
        data = resp.json()
        save_token(data, client_id)
        return data
    return None


def authenticate(client_id: str) -> str:
    """Device code flow — prints a URL+code, polls until user authenticates."""
    cached = load_cached_token()
    if cached:
        print("  Using cached Teams auth token.")
        return cached["access_token"]

    resp = requests.post(DEVICE_CODE_URL, data={
        "client_id": client_id,
        "scope": SCOPES,
    })
    resp.raise_for_status()
    data = resp.json()

    print(f"\n  Open this URL in your browser:\n  {data['verification_uri']}")
    print(f"\n  Enter code: {data['user_code']}\n")
    webbrowser.open(data["verification_uri"])

    interval = data.get("interval", 5)
    expires_in = data.get("expires_in", 300)
    deadline = time.time() + expires_in

    while time.time() < deadline:
        time.sleep(interval)
        token_resp = requests.post(TOKEN_URL, data={
            "client_id": client_id,
            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
            "device_code": data["device_code"],
        })
        token_data = token_resp.json()
        if "access_token" in token_data:
            save_token(token_data, client_id)
            print("  Authenticated successfully.\n")
            return token_data["access_token"]
        if token_data.get("error") not in ("authorization_pending", "slow_down"):
            print(f"  Auth error: {token_data.get('error_description')}", file=sys.stderr)
            sys.exit(1)

    print("  Authentication timed out.", file=sys.stderr)
    sys.exit(1)


# ── Graph API helpers ─────────────────────────────────────────────────────────

def graph_get(token: str, path: str) -> dict | None:
    resp = requests.get(f"{GRAPH_BASE}{path}", headers={"Authorization": f"Bearer {token}"})
    if resp.ok:
        return resp.json()
    return None


def graph_post(token: str, path: str, body: dict) -> dict | None:
    resp = requests.post(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        json=body,
    )
    if resp.ok:
        return resp.json()
    print(f"    Graph error {resp.status_code}: {resp.text}", file=sys.stderr)
    return None


def resolve_user_id(token: str, email: str) -> str | None:
    """Look up the M365 user ID for an email address."""
    data = graph_get(token, f"/users/{email}")
    if data and "id" in data:
        return data["id"]
    return None


def get_my_user_id(token: str) -> str:
    data = graph_get(token, "/me")
    return data["id"]


def create_or_get_chat(token: str, my_id: str, their_id: str) -> str | None:
    """Create a 1:1 Teams chat and return the chat ID."""
    body = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{my_id}')",
            },
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{their_id}')",
            },
        ],
    }
    data = graph_post(token, "/chats", body)
    return data["id"] if data else None


def send_message(token: str, chat_id: str, text: str) -> bool:
    data = graph_post(token, f"/chats/{chat_id}/messages", {
        "body": {"content": text}
    })
    return data is not None


# ── CSV processing ────────────────────────────────────────────────────────────

def load_outlook_contacts(csv_path: str) -> list[dict]:
    p = pathlib.Path(csv_path)
    if not p.exists():
        print(f"Error: {csv_path} not found", file=sys.stderr)
        sys.exit(1)
    with open(p, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    provider_col = next((h for h in (rows[0].keys() if rows else []) if "provider" in h.lower()), None)
    if not provider_col:
        print("Warning: no 'email_provider' column found — processing all rows.", file=sys.stderr)
        return rows

    return [r for r in rows if r.get(provider_col, "") in OUTLOOK_PROVIDERS]


def format_message(template: str, row: dict) -> str:
    """Fill {first_name}, {last_name}, {company}, {email} placeholders."""
    fields = {k.lower().replace(" ", "_"): v for k, v in row.items()}
    # common aliases
    fields.setdefault("first_name", fields.get("first name", fields.get("name", "there").split()[0]))
    fields.setdefault("last_name", fields.get("last name", ""))
    fields.setdefault("company", fields.get("company", "your company"))
    fields.setdefault("email", fields.get("email", ""))
    try:
        return template.format(**fields)
    except KeyError:
        return template


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Send Teams DMs to Outlook contacts from a CSV.")
    parser.add_argument("--csv", required=True, help="Path to contacts CSV (with email_provider column)")
    parser.add_argument("--client-id", required=True, help="Azure app client ID")
    parser.add_argument("--message", default=DEFAULT_MESSAGE, help="Message template (supports {first_name}, {company}, etc.)")
    parser.add_argument("--dry-run", action="store_true", help="Preview messages without sending")
    args = parser.parse_args()

    contacts = load_outlook_contacts(args.csv)
    if not contacts:
        print("No Outlook/M365 contacts found in CSV. Run detect_email_provider.py first.")
        sys.exit(0)

    print(f"Found {len(contacts)} Microsoft 365 / Outlook contact(s).\n")

    if args.dry_run:
        print("DRY RUN — messages that would be sent:\n")
        for row in contacts:
            email = row.get("email", "")
            msg = format_message(args.message, row)
            print(f"  To: {email}")
            print(f"  Message: {msg}\n")
        return

    print("Authenticating with Microsoft...")
    token = authenticate(args.client_id)
    my_id = get_my_user_id(token)

    sent, failed = 0, 0
    for row in contacts:
        email = row.get("email", "").strip()
        if not email:
            continue

        msg = format_message(args.message, row)
        print(f"  → {email}")

        user_id = resolve_user_id(token, email)
        if not user_id:
            print(f"    Could not resolve M365 user ID — skipping.")
            failed += 1
            continue

        chat_id = create_or_get_chat(token, my_id, user_id)
        if not chat_id:
            print(f"    Could not create chat — skipping.")
            failed += 1
            continue

        ok = send_message(token, chat_id, msg)
        if ok:
            print(f"    Sent.")
            sent += 1
        else:
            print(f"    Failed to send.")
            failed += 1

    print(f"\nDone. Sent: {sent}  Failed: {failed}")


if __name__ == "__main__":
    main()
