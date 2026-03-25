"""Microsoft Teams — send DMs via Graph API using device code flow."""

import json
import time
import webbrowser
from pathlib import Path

import msal
import requests

from rich.console import Console

console = Console()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Chat.ReadWrite", "Chat.Create", "User.ReadBasic.All"]
TOKEN_CACHE = Path.home() / ".forgechannels" / "teams_token.json"


def _load_token_cache() -> msal.SerializableTokenCache:
    cache = msal.SerializableTokenCache()
    if TOKEN_CACHE.exists():
        cache.deserialize(TOKEN_CACHE.read_text())
    return cache


def _save_token_cache(cache: msal.SerializableTokenCache):
    TOKEN_CACHE.parent.mkdir(parents=True, exist_ok=True)
    TOKEN_CACHE.write_text(cache.serialize())


def authenticate_teams(client_id: str) -> str:
    """Authenticate with Microsoft using device code flow. Returns access token."""
    cache = _load_token_cache()
    app = msal.PublicClientApplication(
        client_id,
        authority="https://login.microsoftonline.com/common",
        token_cache=cache,
    )

    # Try cached token first
    accounts = app.get_accounts()
    if accounts:
        result = app.acquire_token_silent(SCOPES, account=accounts[0])
        if result and "access_token" in result:
            _save_token_cache(cache)
            return result["access_token"]

    # Device code flow
    flow = app.initiate_device_flow(scopes=SCOPES)
    if "user_code" not in flow:
        raise RuntimeError(f"Device flow failed: {flow}")

    console.print(f"  [yellow]Go to:[/yellow] [cyan]{flow['verification_uri']}[/cyan]")
    console.print(f"  [yellow]Enter code:[/yellow] [bold]{flow['user_code']}[/bold]")
    webbrowser.open(flow["verification_uri"])

    result = app.acquire_token_by_device_flow(flow)
    if "access_token" not in result:
        raise RuntimeError(f"Auth failed: {result.get('error_description', result)}")

    _save_token_cache(cache)
    return result["access_token"]


def _headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


def _find_or_create_chat(token: str, recipient_email: str) -> str:
    """Find existing 1:1 chat or create one. Returns chat ID."""
    # Search existing chats
    resp = requests.get(
        f"{GRAPH_BASE}/me/chats?$filter=chatType eq 'oneOnOne'&$expand=members&$top=50",
        headers=_headers(token),
    )
    if resp.ok:
        for chat in resp.json().get("value", []):
            members = chat.get("members@odata.context") and chat.get("members", [])
            if not members:
                members = chat.get("members", [])
            for m in members:
                if m.get("email", "").lower() == recipient_email.lower():
                    return chat["id"]

    # Create new 1:1 chat
    body = {
        "chatType": "oneOnOne",
        "members": [
            {
                "@odata.type": "#microsoft.graph.aadUserConversationMember",
                "roles": ["owner"],
                "user@odata.bind": f"https://graph.microsoft.com/v1.0/users('{recipient_email}')",
            },
            # Self is added automatically
        ],
    }
    resp = requests.post(f"{GRAPH_BASE}/me/chats", headers=_headers(token), json=body)
    resp.raise_for_status()
    return resp.json()["id"]


def send_teams_message(token: str, recipient_email: str, text: str) -> dict:
    """Send a Teams DM to a user by email. Returns the API response."""
    chat_id = _find_or_create_chat(token, recipient_email)

    resp = requests.post(
        f"{GRAPH_BASE}/me/chats/{chat_id}/messages",
        headers=_headers(token),
        json={"body": {"content": text}},
    )
    resp.raise_for_status()
    return resp.json()
