import unittest
from types import SimpleNamespace

from app.services import firebase as firebase_service


class FirebaseNotificationPayloadTests(unittest.TestCase):
    def test_build_multicast_message_includes_notification_payload(self):
        class FakeMessaging:
            def Notification(self, title, body):
                return {"title": title, "body": body}

            def AndroidNotification(self, **kwargs):
                return kwargs

            def AndroidConfig(self, **kwargs):
                return kwargs

            class MulticastMessage:
                def __init__(self, **kwargs):
                    self.kwargs = kwargs

        messaging = FakeMessaging()
        message = firebase_service._build_multicast_message(
            messaging,
            tokens=["token-1"],
            title="New message",
            body="Hello",
            data={"type": "social_message"},
        )

        self.assertEqual(message.kwargs["notification"]["title"], "New message")
        self.assertEqual(message.kwargs["notification"]["body"], "Hello")
        self.assertEqual(message.kwargs["data"]["type"], "social_message")
        self.assertEqual(message.kwargs["android"]["priority"], "high")
        self.assertNotIn("channel_id", message.kwargs["android"]["notification"])


if __name__ == "__main__":
    unittest.main()
