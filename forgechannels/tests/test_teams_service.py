import unittest
from unittest.mock import patch

from cli.services import teams_service


class FakeResponse:
    def __init__(self, *, ok=True, status_code=200, payload=None):
        self.ok = ok
        self.status_code = status_code
        self._payload = payload or {}
        self.text = str(self._payload)

    def json(self):
        return self._payload

    def raise_for_status(self):
        if not self.ok:
            raise RuntimeError(f"HTTP {self.status_code}: {self.text}")


class TeamsServiceTests(unittest.TestCase):
    @patch("cli.services.teams_service.requests.post")
    @patch("cli.services.teams_service.requests.get")
    def test_creates_chat_via_chats_endpoint_with_both_members_for_same_tenant_user(
        self,
        mock_get,
        mock_post,
    ):
        mock_get.side_effect = [
            FakeResponse(payload={"value": []}),
            FakeResponse(payload={"id": "me-id"}),
            FakeResponse(
                payload={
                    "id": "recipient-id",
                    "userPrincipalName": "alice@example.com",
                    "mail": "alice@example.com",
                    "userType": "Member",
                }
            ),
        ]
        mock_post.return_value = FakeResponse(payload={"id": "chat-123"})

        chat_id = teams_service._find_or_create_chat("token", "alice@example.com")

        self.assertEqual(chat_id, "chat-123")
        mock_post.assert_called_once()
        self.assertEqual(mock_post.call_args.args[0], "https://graph.microsoft.com/v1.0/chats")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(body["chatType"], "oneOnOne")
        self.assertEqual(len(body["members"]), 2)
        self.assertEqual(
            body["members"][0]["user@odata.bind"],
            "https://graph.microsoft.com/v1.0/users('me-id')",
        )
        self.assertEqual(
            body["members"][1]["user@odata.bind"],
            "https://graph.microsoft.com/v1.0/users('recipient-id')",
        )

    @patch("cli.services.teams_service.get_config_value", return_value={}, create=True)
    @patch("cli.services.teams_service.requests.post")
    @patch("cli.services.teams_service.requests.get")
    def test_raises_clear_error_when_recipient_is_not_in_directory_and_has_no_external_mapping(
        self,
        mock_get,
        mock_post,
        _mock_get_config_value,
    ):
        mock_get.side_effect = [
            FakeResponse(payload={"value": []}),
            FakeResponse(payload={"id": "me-id"}),
            FakeResponse(
                ok=False,
                status_code=404,
                payload={"error": {"code": "Request_ResourceNotFound"}},
            ),
        ]
        mock_post.side_effect = AssertionError("chat creation should not be attempted")

        with self.assertRaisesRegex(RuntimeError, "external Teams user"):
            teams_service._find_or_create_chat("token", "aksels.bergmanis@tilde.com")

    @patch(
        "cli.services.teams_service.get_config_value",
        return_value={
            "aksels.bergmanis@tilde.com": {
                "user_id": "external-user-id",
                "tenant_id": "external-tenant-id",
            }
        },
        create=True,
    )
    @patch("cli.services.teams_service.requests.post")
    @patch("cli.services.teams_service.requests.get")
    def test_uses_external_mapping_for_federated_users(
        self,
        mock_get,
        mock_post,
        _mock_get_config_value,
    ):
        mock_get.side_effect = [
            FakeResponse(payload={"value": []}),
            FakeResponse(payload={"id": "me-id"}),
            FakeResponse(
                ok=False,
                status_code=404,
                payload={"error": {"code": "Request_ResourceNotFound"}},
            ),
        ]
        mock_post.return_value = FakeResponse(payload={"id": "chat-456"})

        chat_id = teams_service._find_or_create_chat("token", "aksels.bergmanis@tilde.com")

        self.assertEqual(chat_id, "chat-456")
        body = mock_post.call_args.kwargs["json"]
        self.assertEqual(
            body["members"][1]["user@odata.bind"],
            "https://graph.microsoft.com/v1.0/users('external-user-id')",
        )
        self.assertEqual(body["members"][1]["tenantId"], "external-tenant-id")


if __name__ == "__main__":
    unittest.main()
