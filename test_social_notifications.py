import unittest
from types import SimpleNamespace
from unittest.mock import patch

from app.routes.social import _extract_mentioned_user_ids


class SocialNotificationParsingTests(unittest.TestCase):
    def test_extracts_mentions_from_post_content(self):
        content = "Hello @jane.doe and @john, please check this out"
        with patch("app.routes.social._resolve_user_by_identifier", side_effect=lambda db, identifier: {
            "jane.doe": SimpleNamespace(email="jane.doe@example.com"),
            "john": SimpleNamespace(email="john@example.com"),
        }.get(identifier)):
            self.assertEqual(
                _extract_mentioned_user_ids(content, db=object()),
                ["jane.doe", "john"],
            )

    def test_ignores_non_mentions_and_duplicates(self):
        content = "Hi jane.doe @jane.doe and @unknown and @john @john"
        with patch("app.routes.social._resolve_user_by_identifier", side_effect=lambda db, identifier: {
            "jane.doe": SimpleNamespace(email="jane.doe@example.com"),
            "john": SimpleNamespace(email="john@example.com"),
        }.get(identifier)):
            self.assertEqual(
                _extract_mentioned_user_ids(content, db=object()),
                ["jane.doe", "john"],
            )


if __name__ == "__main__":
    unittest.main()
