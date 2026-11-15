"""Storage tests against a temporary database file (Prompt A "Testing")."""

from __future__ import annotations

import json
import pathlib
import sqlite3
import tempfile
import unittest
from datetime import UTC, datetime

from mindpulse.models import ChatMessage, CheckIn, Instrument, Role, Screening, Severity
from mindpulse.storage import (
    SCHEMA_VERSION,
    SCHEMA_VERSION_KEY,
    append_chat_message,
    connect,
    delete_conversation,
    erase_all_data,
    export_all_data,
    get_meta,
    latest_check_in,
    latest_screening,
    list_check_ins,
    list_screenings,
    load_chat_messages,
    reset_database,
    run_migrations,
    save_check_in,
    save_screening,
    screening_risk_active,
    set_meta,
    to_utc_iso,
    utc_now_iso,
    validate_check_in,
)


def make_check_in(**overrides: object) -> CheckIn:
    """Return a valid check-in, with fields replaceable for edge-case tests."""
    values: dict[str, object] = {
        "created_at": "2026-10-18T09:30:00Z",
        "mood": 6,
        "stress": 4,
        "energy": 5,
        "sleep_hours": 7.5,
        "journal": "A steady day.",
    }
    values.update(overrides)
    return CheckIn(**values)  # type: ignore[arg-type]


def make_screening(**overrides: object) -> Screening:
    """Return a valid PHQ-9 screening record."""
    values: dict[str, object] = {
        "created_at": "2026-10-18T10:00:00Z",
        "instrument": Instrument.PHQ9,
        "answers": (1, 0, 2, 1, 0, 0, 0, 0, 0),
        "total": 4,
        "severity": Severity.MINIMAL,
        "risk_flag": False,
        "impairment": "not_difficult",
        "content_checksum": "abc123abc123abcd",
    }
    values.update(overrides)
    return Screening(**values)  # type: ignore[arg-type]


class TempDatabaseTest(unittest.TestCase):
    def setUp(self) -> None:
        self._directory = tempfile.TemporaryDirectory()
        self.addCleanup(self._directory.cleanup)
        self.path = pathlib.Path(self._directory.name) / "nested" / "mindpulse.db"
        self.conn = connect(self.path)
        self.addCleanup(self.conn.close)
        run_migrations(self.conn)


class SchemaTests(TempDatabaseTest):
    def test_connect_creates_the_directory_and_file(self) -> None:
        self.assertTrue(self.path.exists())

    def test_tables_exist_after_migration(self) -> None:
        names = {
            row["name"]
            for row in self.conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        }
        self.assertLessEqual({"check_ins", "screenings", "chat_messages", "app_meta"}, names)

    def test_migrations_are_idempotent(self) -> None:
        run_migrations(self.conn)
        run_migrations(self.conn)
        self.assertEqual(get_meta(self.conn, SCHEMA_VERSION_KEY), SCHEMA_VERSION)

    def test_foreign_keys_are_enabled(self) -> None:
        self.assertEqual(self.conn.execute("PRAGMA foreign_keys").fetchone()[0], 1)

    def test_check_constraint_rejects_out_of_range_mood(self) -> None:
        with self.assertRaises(sqlite3.IntegrityError):
            self.conn.execute(
                "INSERT INTO check_ins (created_at, mood, stress, energy, sleep_hours, journal) "
                "VALUES ('2026-10-18T09:30:00Z', 11, 5, 5, 7, '')"
            )

    def test_reset_database_removes_the_file(self) -> None:
        reset_database(self.path)
        self.assertFalse(self.path.exists())


class CheckInTests(TempDatabaseTest):
    def test_round_trip(self) -> None:
        check_in = make_check_in()
        row_id = save_check_in(self.conn, check_in)
        stored = list_check_ins(self.conn)
        self.assertEqual(len(stored), 1)
        self.assertEqual(stored[0].id, row_id)
        self.assertEqual(stored[0], CheckIn(**{**check_in.__dict__, "id": row_id}))

    def test_reads_are_sorted_oldest_first(self) -> None:
        for day in ("2026-10-18", "2026-10-16", "2026-10-17"):
            save_check_in(self.conn, make_check_in(created_at=f"{day}T08:00:00Z"))
        timestamps = [record.created_at for record in list_check_ins(self.conn)]
        self.assertEqual(timestamps, sorted(timestamps))

    def test_since_filter_is_inclusive(self) -> None:
        save_check_in(self.conn, make_check_in(created_at="2026-10-16T08:00:00Z"))
        save_check_in(self.conn, make_check_in(created_at="2026-10-17T08:00:00Z"))
        recent = list_check_ins(self.conn, since="2026-10-17T00:00:00Z")
        self.assertEqual([record.created_at for record in recent], ["2026-10-17T08:00:00Z"])

    def test_limit_keeps_the_newest_records(self) -> None:
        for day in range(1, 6):
            save_check_in(self.conn, make_check_in(created_at=f"2026-10-0{day}T08:00:00Z"))
        recent = list_check_ins(self.conn, limit=2)
        self.assertEqual(
            [record.created_at for record in recent],
            ["2026-10-04T08:00:00Z", "2026-10-05T08:00:00Z"],
        )

    def test_latest_check_in(self) -> None:
        self.assertIsNone(latest_check_in(self.conn))
        save_check_in(self.conn, make_check_in(created_at="2026-10-17T08:00:00Z"))
        save_check_in(self.conn, make_check_in(created_at="2026-10-18T08:00:00Z"))
        latest = latest_check_in(self.conn)
        assert latest is not None
        self.assertEqual(latest.created_at, "2026-10-18T08:00:00Z")

    def test_blank_created_at_is_filled_with_now(self) -> None:
        row_id = save_check_in(self.conn, make_check_in(created_at=""))
        self.assertGreater(row_id, 0)
        stored = latest_check_in(self.conn)
        assert stored is not None
        self.assertTrue(stored.created_at.endswith("Z"))

    def test_invalid_values_are_rejected(self) -> None:
        for overrides in (
            {"mood": 0},
            {"mood": 11},
            {"stress": 0},
            {"energy": 12},
            {"sleep_hours": -1.0},
            {"sleep_hours": 25.0},
            {"journal": "x" * 2001},
            {"mood": "6"},
        ):
            with self.subTest(overrides=overrides), self.assertRaises(ValueError):
                validate_check_in(make_check_in(**overrides))

    def test_corrupt_row_is_skipped_not_fatal(self) -> None:
        # Insert a row that violates the dataclass conversion but not the table's
        # NOT NULL columns, by telling SQLite to ignore the CHECK constraints.
        self.conn.execute("PRAGMA ignore_check_constraints = ON")
        self.conn.execute(
            "INSERT INTO check_ins (created_at, mood, stress, energy, sleep_hours, journal) "
            "VALUES ('2026-10-19T09:30:00Z', 'not-a-number', 5, 5, 7, '')"
        )
        self.conn.execute("PRAGMA ignore_check_constraints = OFF")
        self.conn.commit()
        with self.assertLogs("mindpulse.storage", level="WARNING"):
            records = list_check_ins(self.conn)
        self.assertEqual(records, ())


class ScreeningTests(TempDatabaseTest):
    def test_round_trip_preserves_enums_and_answers(self) -> None:
        row_id = save_screening(self.conn, make_screening())
        stored = list_screenings(self.conn)
        self.assertEqual(len(stored), 1)
        record = stored[0]
        self.assertEqual(record.id, row_id)
        self.assertIs(record.instrument, Instrument.PHQ9)
        self.assertIs(record.severity, Severity.MINIMAL)
        self.assertEqual(record.answers, (1, 0, 2, 1, 0, 0, 0, 0, 0))
        self.assertEqual(record.impairment, "not_difficult")
        self.assertEqual(record.content_checksum, "abc123abc123abcd")

    def test_answers_are_stored_as_a_json_array_in_item_order(self) -> None:
        save_screening(self.conn, make_screening(answers=(3, 2, 1, 0, 0, 0, 0, 0, 0)))
        raw = self.conn.execute("SELECT answers FROM screenings").fetchone()["answers"]
        self.assertEqual(json.loads(raw), [3, 2, 1, 0, 0, 0, 0, 0, 0])

    def test_impairment_may_be_null(self) -> None:
        save_screening(self.conn, make_screening(impairment=None))
        stored = latest_screening(self.conn)
        assert stored is not None
        self.assertIsNone(stored.impairment)

    def test_risk_flag_round_trips_as_bool(self) -> None:
        save_screening(self.conn, make_screening(risk_flag=True))
        stored = latest_screening(self.conn)
        assert stored is not None
        self.assertIs(stored.risk_flag, True)

    def test_screening_risk_active_uses_the_latest_screening(self) -> None:
        self.assertFalse(screening_risk_active(self.conn))
        save_screening(self.conn, make_screening(risk_flag=True))
        self.assertTrue(screening_risk_active(self.conn))
        save_screening(
            self.conn,
            make_screening(created_at="2026-10-19T10:00:00Z", risk_flag=False),
        )
        self.assertFalse(screening_risk_active(self.conn))

    def test_invalid_impairment_value_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            save_screening(self.conn, make_screening(impairment="slightly_difficult"))

    def test_corrupt_answers_json_is_skipped_not_fatal(self) -> None:
        save_screening(self.conn, make_screening())
        self.conn.execute("UPDATE screenings SET answers = 'not json'")
        self.conn.commit()
        with self.assertLogs("mindpulse.storage", level="WARNING"):
            self.assertEqual(list_screenings(self.conn), ())


class ChatTests(TempDatabaseTest):
    def test_round_trip_and_order(self) -> None:
        first = append_chat_message(
            self.conn, ChatMessage(Role.USER, "hi", created_at="2026-10-18T09:00:00Z")
        )
        second = append_chat_message(
            self.conn, ChatMessage(Role.ASSISTANT, "hello", created_at="2026-10-18T09:01:00Z")
        )
        messages = load_chat_messages(self.conn)
        self.assertEqual([message.id for message in messages], [first, second])
        self.assertIs(messages[0].role, Role.USER)
        self.assertEqual(messages[1].content, "hello")

    def test_load_limit_keeps_the_newest(self) -> None:
        for index in range(5):
            append_chat_message(
                self.conn,
                ChatMessage(Role.USER, f"m{index}", created_at=f"2026-10-18T09:0{index}:00Z"),
            )
        self.assertEqual(
            [message.content for message in load_chat_messages(self.conn, limit=2)],
            ["m3", "m4"],
        )

    def test_empty_message_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            append_chat_message(self.conn, ChatMessage(Role.USER, "   "))

    def test_delete_conversation_removes_every_message(self) -> None:
        append_chat_message(self.conn, ChatMessage(Role.USER, "hi"))
        append_chat_message(self.conn, ChatMessage(Role.ASSISTANT, "hello"))
        removed = delete_conversation(self.conn)
        self.assertEqual(removed, 2)
        self.assertEqual(load_chat_messages(self.conn), ())

    def test_system_role_is_allowed_by_the_schema(self) -> None:
        append_chat_message(self.conn, ChatMessage(Role.SYSTEM, "context"))
        self.assertEqual(len(load_chat_messages(self.conn)), 1)


class MetaAndExportTests(TempDatabaseTest):
    def test_meta_round_trip_and_default(self) -> None:
        self.assertIsNone(get_meta(self.conn, "missing"))
        self.assertEqual(get_meta(self.conn, "missing", "fallback"), "fallback")
        set_meta(self.conn, "theme", "light")
        self.assertEqual(get_meta(self.conn, "theme"), "light")
        set_meta(self.conn, "theme", "contrast")
        self.assertEqual(get_meta(self.conn, "theme"), "contrast")

    def test_export_contains_every_section(self) -> None:
        save_check_in(self.conn, make_check_in())
        save_screening(self.conn, make_screening())
        append_chat_message(self.conn, ChatMessage(Role.USER, "hi"))
        payload = export_all_data(self.conn)
        self.assertEqual(
            set(payload),
            {
                "app_version",
                "schema_version",
                "exported_at",
                "check_ins",
                "screenings",
                "chat_messages",
            },
        )
        self.assertEqual(len(payload["check_ins"]), 1)
        self.assertEqual(payload["screenings"][0]["instrument"], "PHQ9")
        self.assertEqual(payload["screenings"][0]["severity"], "MINIMAL")
        self.assertEqual(payload["chat_messages"][0]["role"], "user")
        # The export must be JSON-serialisable end to end.
        self.assertIn("check_ins", json.dumps(payload))

    def test_erase_all_data_keeps_the_schema(self) -> None:
        save_check_in(self.conn, make_check_in())
        save_screening(self.conn, make_screening())
        append_chat_message(self.conn, ChatMessage(Role.USER, "hi"))
        erase_all_data(self.conn)
        self.assertEqual(list_check_ins(self.conn), ())
        self.assertEqual(list_screenings(self.conn), ())
        self.assertEqual(load_chat_messages(self.conn), ())
        self.assertEqual(get_meta(self.conn, SCHEMA_VERSION_KEY), SCHEMA_VERSION)


class TimeHelperTests(unittest.TestCase):
    def test_utc_now_iso_shape(self) -> None:
        stamp = utc_now_iso()
        self.assertRegex(stamp, r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

    def test_to_utc_iso_converts_naive_and_aware(self) -> None:
        naive = datetime(2026, 10, 18, 9, 30, 0)
        self.assertEqual(to_utc_iso(naive), "2026-10-18T09:30:00Z")
        aware = datetime(2026, 10, 18, 11, 30, 0, tzinfo=UTC)
        self.assertEqual(to_utc_iso(aware), "2026-10-18T11:30:00Z")


if __name__ == "__main__":
    unittest.main()
