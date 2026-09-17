"""Tests for canonical registration email handling.

Run with: python -m unittest -v test_core_registration.py
"""
import unittest

from core_registration import email_index_key, normalize_email


class NormalizeEmailTests(unittest.TestCase):
    def test_strips_and_casefolds_email(self):
        self.assertEqual(
            normalize_email("  Resch.Kerstin@GMX.de  "),
            "resch.kerstin@gmx.de",
        )

    def test_rejects_non_string_and_empty_value(self):
        self.assertIsNone(normalize_email(None))
        self.assertIsNone(normalize_email("   "))

    def test_same_email_has_same_stable_index_key(self):
        self.assertEqual(
            email_index_key("Resch.Kerstin@GMX.de"),
            email_index_key(" resch.kerstin@gmx.de "),
        )

    def test_index_key_is_none_for_invalid_email(self):
        self.assertIsNone(email_index_key(""))


if __name__ == "__main__":
    unittest.main()
