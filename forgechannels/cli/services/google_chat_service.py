"""Google Chat API — send DMs and read replies."""

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError


def get_chat_service(creds: Credentials):
    """Build the Google Chat API service client."""
    return build("chat", "v1", credentials=creds)


def find_or_create_dm(service, recipient_email: str) -> str:
    """Find an existing DM space with a user, or create one.

    Returns the space name (e.g. 'spaces/AAAA1234').
    """
    # Try to find existing DM
    try:
        dm = service.spaces().findDirectMessage(
            name=f"users/{recipient_email}"
        ).execute()
        return dm["name"]
    except HttpError:
        pass

    # Create new DM space via spaces.setup
    setup_body = {
        "space": {"spaceType": "DIRECT_MESSAGE"},
        "memberships": [
            {
                "member": {"name": f"users/{recipient_email}", "type": "HUMAN"},
            }
        ],
    }
    try:
        space = service.spaces().setup(body=setup_body).execute()
        return space["name"]
    except HttpError:
        pass

    # Fallback: create a regular DM space then add member
    space = service.spaces().create(
        body={
            "spaceType": "DIRECT_MESSAGE",
            "singleUserBotDm": False,
        },
        requestId=f"dm-{recipient_email}",
    ).execute()
    return space["name"]


def send_message(service, recipient_email: str, text: str) -> dict:
    """Send a DM to a user by email. Creates the DM space if needed.

    Returns the API response with message details.
    """
    space_name = find_or_create_dm(service, recipient_email)

    response = (
        service.spaces()
        .messages()
        .create(parent=space_name, body={"text": text})
        .execute()
    )
    return response


def list_messages(service, space_name: str, page_size: int = 25) -> list[dict]:
    """List recent messages in a space (newest first)."""
    response = (
        service.spaces()
        .messages()
        .list(
            parent=space_name,
            pageSize=page_size,
            orderBy="createTime desc",
        )
        .execute()
    )
    return response.get("messages", [])
