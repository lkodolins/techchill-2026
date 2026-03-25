"""Microsoft Teams — send DMs via Graph API using device code flow."""

import json
import time
import webbrowser
from pathlib import Path
from urllib.parse import quote

import msal
import requests

from cli.auth.config_store import get_config_value
from rich.console import Console

console = Console()

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SCOPES = ["Chat.ReadWrite", "Chat.Create", "User.ReadBasic.All"]
TOKEN_CACHE = Path.home() / ".forgechannels" / "teams_token.json"
EXTERNAL_USERS_KEY = "microsoft_external_users"


class TeamsRecipientResolutionError(RuntimeError):
    """Raised when a Teams recipient cannot be resolved for chat creation."""


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


def _get_my_user_id(token: str) -> str:
    resp = requests.get(f"{GRAPH_BASE}/me?$select=id", headers=_headers(token))
    resp.raise_for_status()
    return resp.json()["id"]


def _build_member(user_id: str, *, role: str, tenant_id: str | None = None) -> dict:
    member = {
        "@odata.type": "#microsoft.graph.aadUserConversationMember",
        "roles": [role],
        "user@odata.bind": f"{GRAPH_BASE}/users('{user_id}')",
    }
    if tenant_id:
        member["tenantId"] = tenant_id
    return member


def _get_external_recipient_mapping(recipient_email: str) -> dict | None:
    external_users = get_config_value(EXTERNAL_USERS_KEY, {}) or {}
    return external_users.get(recipient_email.lower()) or external_users.get(recipient_email)


def _resolve_recipient(token: str, recipient_email: str) -> dict:
    recipient_email = recipient_email.strip().lower()

    external_mapping = _get_external_recipient_mapping(recipient_email)
    if external_mapping:
        user_id = external_mapping.get("user_id")
        tenant_id = external_mapping.get("tenant_id")
        if user_id and tenant_id:
            return {
                "user_id": user_id,
                "role": "owner",
                "tenant_id": tenant_id,
                "email": recipient_email,
            }

    resp = requests.get(
        f"{GRAPH_BASE}/users/{quote(recipient_email, safe='')}",
        headers=_headers(token),
    )
    if resp.ok:
        payload = resp.json()
        return {
            "user_id": payload["id"],
            "role": "guest" if payload.get("userType") == "Guest" else "owner",
            "tenant_id": None,
            "email": (payload.get("mail") or payload.get("userPrincipalName") or recipient_email).lower(),
        }

    if resp.status_code == 404:
        raise TeamsRecipientResolutionError(
            "Graph could not resolve this email to a user in your Entra tenant. "
            "For an external Teams user, add "
            f"'{EXTERNAL_USERS_KEY}' to ~/.forgechannels/config.json with their "
            "'user_id' and 'tenant_id', or invite them as a guest first."
        )

    resp.raise_for_status()
    raise TeamsRecipientResolutionError(f"Unable to resolve Teams recipient: {recipient_email}")


def _find_or_create_chat(token: str, recipient_email: str) -> str:
    """Find existing 1:1 chat or create one. Returns chat ID."""
    recipient_email = recipient_email.strip().lower()

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

    me_id = _get_my_user_id(token)
    recipient = _resolve_recipient(token, recipient_email)

    body = {
        "chatType": "oneOnOne",
        "members": [
            _build_member(me_id, role="owner"),
            _build_member(
                recipient["user_id"],
                role=recipient["role"],
                tenant_id=recipient["tenant_id"],
            ),
        ],
    }
    resp = requests.post(f"{GRAPH_BASE}/chats", headers=_headers(token), json=body)
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
