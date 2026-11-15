"""Tests for the structured helpline data (Prompt D §2.1, §5)."""

from __future__ import annotations

import unittest

from mindpulse.resources import (
    CRISIS_RESOURCES,
    PRIMARY_LIFELINE_ID,
    WEB_HELPLINE_ID,
    resource_by_id,
    resource_line,
    resources_in_display_order,
    sms_uri,
    tel_uri,
)

#: Canonical ``(name, action_text)`` pairs from Prompt D §2.1, in display order.
CANONICAL_RESOURCE_TEXT = (
    ("988 Suicide & Crisis Lifeline", "Call or text 988 (US)"),
    ("Crisis Text Line", "Text HOME to 741741 (US)"),
    ("Find A Helpline", "findahelpline.com for help outside the US"),
    ("Emergency services", "Call 911 (US) / 112 (EU) if you are in immediate danger"),
)


class ResourceDataTests(unittest.TestCase):
    def test_all_four_resources_present_and_ordered(self) -> None:
        resources = resources_in_display_order()
        self.assertEqual(len(resources), 4)
        self.assertEqual(
            tuple((item.name, item.action_text) for item in resources),
            CANONICAL_RESOURCE_TEXT,
        )

    def test_display_order_values_are_unique_and_ascending(self) -> None:
        orders = tuple(item.display_order for item in resources_in_display_order())
        self.assertEqual(len(set(orders)), len(orders))
        self.assertEqual(orders, tuple(sorted(orders)))

    def test_each_resource_has_a_phone_or_a_url(self) -> None:
        for resource in CRISIS_RESOURCES:
            with self.subTest(resource=resource.id):
                self.assertTrue(resource.phone or resource.url)

    def test_sms_text_only_on_crisis_text_line(self) -> None:
        with_sms = tuple(item.id for item in CRISIS_RESOURCES if item.sms_text)
        self.assertEqual(with_sms, ("crisis_text_line",))
        self.assertEqual(resource_by_id("crisis_text_line").sms_text, "HOME")

    def test_988_has_short_code_and_no_sms_body(self) -> None:
        lifeline = resource_by_id(PRIMARY_LIFELINE_ID)
        self.assertEqual(lifeline.phone, "988")
        self.assertIsNone(lifeline.sms_text)

    def test_find_a_helpline_has_url_and_no_phone(self) -> None:
        helpline = resource_by_id(WEB_HELPLINE_ID)
        self.assertEqual(helpline.url, "https://findahelpline.com")
        self.assertIsNone(helpline.phone)

    def test_ids_are_unique_and_stable(self) -> None:
        ids = tuple(item.id for item in CRISIS_RESOURCES)
        self.assertEqual(len(set(ids)), len(ids))

    def test_unknown_resource_id_raises(self) -> None:
        with self.assertRaises(KeyError):
            resource_by_id("not_a_resource")


class ResourceUriTests(unittest.TestCase):
    def test_tel_uri_exists_only_for_resources_with_a_phone(self) -> None:
        self.assertEqual(tel_uri(resource_by_id("988_lifeline")), "tel:988")
        self.assertIsNone(tel_uri(resource_by_id("find_a_helpline")))

    def test_sms_uri_includes_body_when_present(self) -> None:
        self.assertEqual(sms_uri(resource_by_id("crisis_text_line")), "sms:741741?body=HOME")
        self.assertEqual(sms_uri(resource_by_id("988_lifeline")), "sms:988")

    def test_resource_line_format(self) -> None:
        self.assertEqual(
            resource_line(resource_by_id("emergency_services")),
            "Emergency services — Call 911 (US) / 112 (EU) if you are in immediate danger",
        )


if __name__ == "__main__":
    unittest.main()
