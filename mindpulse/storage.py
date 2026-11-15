"""SQLite persistence - the only module that reads or writes the database.

One local file holds everything: check-ins, screenings, chat messages, and app
metadata. Timestamps are ISO-8601 UTC strings (``2026-10-18T09:30:00Z``). Reads
return tuples of frozen dataclasses sorted by ``created_at``; a corrupt row is
logged and skipped rather than crashing the app.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from collections.abc import Sequence
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .config import APP_VERSION, JOURNAL_MAX_CHARS, SCALE_MAX, SCALE_MIN, SLEEP_MAX_HOURS
from .instruments import is_valid_impairment_value
from .models import ChatMessage, CheckIn, Instrument, Role, Screening, Severity

LOGGER = logging.getLogger(__name__)

#: Bumped when the schema or the stored instrument content changes.
SCHEMA_VERSION = "2"
SCHEMA_VERSION_KEY = "schema_version"
APP_VERSION_KEY = "app_version"

#: Schema DDL, applied with ``executescript`` on every launch (all statements are
#: ``IF NOT EXISTS``). Kept as module literals: no SQL is ever built from input.
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS check_ins (
    id          INTEGER PRIMARY KEY,
    created_at  TEXT    NOT NULL,
    mood        INTEGER NOT NULL CHECK (mood BETWEEN 1 AND 10),
    stress      INTEGER NOT NULL CHECK (stress BETWEEN 1 AND 10),
    energy      INTEGER NOT NULL CHECK (energy BETWEEN 1 AND 10),
    sleep_hours REAL    NOT NULL CHECK (sleep_hours BETWEEN 0 AND 24),
    journal     TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS screenings (
    id               INTEGER PRIMARY KEY,
    created_at       TEXT    NOT NULL,
    instrument       TEXT    NOT NULL CHECK (instrument IN ('PHQ9','GAD7')),
    answers          TEXT    NOT NULL,
    total            INTEGER NOT NULL,
    severity         TEXT    NOT NULL,
    risk_flag        INTEGER NOT NULL DEFAULT 0,
    impairment       TEXT,
    content_checksum TEXT    NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS chat_messages (
    id         INTEGER PRIMARY KEY,
    created_at TEXT    NOT NULL,
    role       TEXT    NOT NULL CHECK (role IN ('user','assistant','system')),
    content    TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS app_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
) WITHOUT ROWID;

CREATE INDEX IF NOT EXISTS idx_check_ins_created_at ON check_ins (created_at);
CREATE INDEX IF NOT EXISTS idx_screenings_created_at ON screenings (created_at);
CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at ON chat_messages (created_at);
"""


# ---------------------------------------------------------------------------
# Time helpers (pure)
# ---------------------------------------------------------------------------


def to_utc_iso(moment: datetime) -> str:
    """Return ``moment`` as an ISO-8601 UTC string with seconds precision."""
    aware = moment.astimezone(UTC) if moment.tzinfo else moment.replace(tzinfo=UTC)
    return aware.strftime("%Y-%m-%dT%H:%M:%SZ")


def utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return to_utc_iso(datetime.now(UTC))


# ---------------------------------------------------------------------------
# Connection and schema
# ---------------------------------------------------------------------------


def connect(database_path: Path | str) -> sqlite3.Connection:
    """Open (creating if needed) the SQLite database at ``database_path``.

    Creates the parent directory, enables foreign keys, and returns a connection
    with ``sqlite3.Row`` rows. Call :func:`run_migrations` before reading.
    """
    if isinstance(database_path, Path):
        database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(database_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def run_migrations(conn: sqlite3.Connection) -> None:
    """Create any missing tables and indexes. Idempotent; safe on every launch."""
    with conn:
        conn.executescript(_SCHEMA_SQL)
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO NOTHING",
            (SCHEMA_VERSION_KEY, SCHEMA_VERSION),
        )
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (APP_VERSION_KEY, APP_VERSION),
        )


def reset_database(database_path: Path | str) -> None:
    """Delete the database file and its journal files (tests and "erase everything").

    Close any open connection first; an open connection keeps writing to the
    deleted file instead of the new one.
    """
    if not isinstance(database_path, Path):
        return
    for suffix in ("", "-wal", "-shm"):
        candidate = database_path.with_name(database_path.name + suffix)
        if candidate.exists():
            candidate.unlink()


def erase_all_data(conn: sqlite3.Connection) -> None:
    """Delete every stored row while keeping the schema in place."""
    with conn:
        conn.execute("DELETE FROM check_ins")
        conn.execute("DELETE FROM screenings")
        conn.execute("DELETE FROM chat_messages")


# ---------------------------------------------------------------------------
# Validation (pure)
# ---------------------------------------------------------------------------


def validate_check_in(check_in: CheckIn) -> CheckIn:
    """Return ``check_in`` after validating its scales and journal length.

    Raises ``ValueError`` with a user-presentable message for any invalid field.
    """
    for name, value in (
        ("Mood", check_in.mood),
        ("Stress", check_in.stress),
        ("Energy", check_in.energy),
    ):
        if not isinstance(value, int) or isinstance(value, bool):
            raise ValueError(f"{name} must be a whole number between 1 and 10.")
        if value < SCALE_MIN or value > SCALE_MAX:
            raise ValueError(f"{name} must be between 1 and 10.")
    if not isinstance(check_in.sleep_hours, int | float) or isinstance(check_in.sleep_hours, bool):
        raise ValueError("Sleep hours must be a number between 0 and 24.")
    if check_in.sleep_hours < 0 or check_in.sleep_hours > SLEEP_MAX_HOURS:
        raise ValueError("Sleep hours must be between 0 and 24.")
    if len(check_in.journal) > JOURNAL_MAX_CHARS:
        raise ValueError(f"Journal entries are limited to {JOURNAL_MAX_CHARS} characters.")
    return check_in


def validate_chat_message(message: ChatMessage) -> ChatMessage:
    """Return ``message`` after validating that role and content are usable."""
    if Role(message.role) not in (Role.USER, Role.ASSISTANT, Role.SYSTEM):
        raise ValueError(f"Unknown chat role {message.role!r}")
    if not message.content.strip():
        raise ValueError("A chat message cannot be empty.")
    return message


def validate_screening(screening: Screening) -> Screening:
    """Return ``screening`` after validating its enum fields and impairment value."""
    if not isinstance(screening.answers, tuple) or not screening.answers:
        raise ValueError("A screening needs its answers as a tuple of integers.")
    if not is_valid_impairment_value(screening.impairment):
        raise ValueError(f"Unknown impairment value {screening.impairment!r}")
    if screening.total < 0:
        raise ValueError("A screening total cannot be negative.")
    return screening


# ---------------------------------------------------------------------------
# Row conversion (pure)
# ---------------------------------------------------------------------------


def row_to_check_in(row: sqlite3.Row) -> CheckIn:
    """Convert a ``check_ins`` row to a :class:`CheckIn`. Raises on corrupt data."""
    return CheckIn(
        created_at=str(row["created_at"]),
        mood=int(row["mood"]),
        stress=int(row["stress"]),
        energy=int(row["energy"]),
        sleep_hours=float(row["sleep_hours"]),
        journal=str(row["journal"]),
        id=int(row["id"]),
    )


def row_to_screening(row: sqlite3.Row) -> Screening:
    """Convert a ``screenings`` row to a :class:`Screening`. Raises on corrupt data."""
    try:
        answers = json.loads(str(row["answers"]))
    except json.JSONDecodeError as error:
        raise ValueError("Stored answers are not valid JSON") from error
    if not isinstance(answers, list):
        raise ValueError("Stored answers are not a JSON list")
    return Screening(
        created_at=str(row["created_at"]),
        instrument=Instrument(str(row["instrument"])),
        answers=tuple(int(weight) for weight in answers),
        total=int(row["total"]),
        severity=Severity(str(row["severity"])),
        risk_flag=bool(row["risk_flag"]),
        impairment=str(row["impairment"]) if row["impairment"] is not None else None,
        content_checksum=str(row["content_checksum"]),
        id=int(row["id"]),
    )


def row_to_chat_message(row: sqlite3.Row) -> ChatMessage:
    """Convert a ``chat_messages`` row to a :class:`ChatMessage`."""
    return ChatMessage(
        role=Role(str(row["role"])),
        content=str(row["content"]),
        created_at=str(row["created_at"]),
        id=int(row["id"]),
    )


def _rows_to_records(
    rows: Sequence[sqlite3.Row],
    converter: Any,
    table: str,
) -> tuple[Any, ...]:
    """Convert rows, logging and skipping any corrupt row instead of crashing."""
    records: list[Any] = []
    for row in rows:
        try:
            records.append(converter(row))
        except (ValueError, TypeError, KeyError, json.JSONDecodeError) as error:
            LOGGER.warning("Skipping corrupt %s row id=%s: %s", table, row["id"], error)
    return tuple(records)


# ---------------------------------------------------------------------------
# Check-ins
# ---------------------------------------------------------------------------


def save_check_in(conn: sqlite3.Connection, check_in: CheckIn) -> int:
    """Insert ``check_in`` and return the new row id. Raises ``ValueError`` if invalid."""
    validated = validate_check_in(check_in)
    created_at = validated.created_at or utc_now_iso()
    with conn:
        cursor = conn.execute(
            "INSERT INTO check_ins (created_at, mood, stress, energy, sleep_hours, journal) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (
                created_at,
                validated.mood,
                validated.stress,
                validated.energy,
                float(validated.sleep_hours),
                validated.journal,
            ),
        )
    return int(cursor.lastrowid or 0)


def list_check_ins(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> tuple[CheckIn, ...]:
    """Return check-ins sorted oldest first, optionally since ``since`` (inclusive).

    ``limit`` keeps the newest ``limit`` records; the result stays oldest first.
    """
    if since:
        rows = conn.execute(
            "SELECT * FROM check_ins WHERE created_at >= ? ORDER BY created_at ASC, id ASC",
            (since,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM check_ins ORDER BY created_at ASC, id ASC").fetchall()
    records = _rows_to_records(rows, row_to_check_in, "check_ins")
    if limit is not None and len(records) > limit:
        return records[-limit:]
    return records


def latest_check_in(conn: sqlite3.Connection) -> CheckIn | None:
    """Return the most recent check-in, or ``None`` when there are none."""
    rows = conn.execute(
        "SELECT * FROM check_ins ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchall()
    records = _rows_to_records(rows, row_to_check_in, "check_ins")
    return records[0] if records else None


# ---------------------------------------------------------------------------
# Screenings
# ---------------------------------------------------------------------------


def save_screening(conn: sqlite3.Connection, screening: Screening) -> int:
    """Insert ``screening`` and return the new row id. Raises ``ValueError`` if invalid."""
    validated = validate_screening(screening)
    created_at = validated.created_at or utc_now_iso()
    with conn:
        cursor = conn.execute(
            "INSERT INTO screenings "
            "(created_at, instrument, answers, total, severity, risk_flag, impairment, "
            "content_checksum) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                created_at,
                Instrument(validated.instrument).value,
                json.dumps(list(validated.answers)),
                validated.total,
                Severity(validated.severity).value,
                1 if validated.risk_flag else 0,
                validated.impairment,
                validated.content_checksum,
            ),
        )
    return int(cursor.lastrowid or 0)


def list_screenings(
    conn: sqlite3.Connection,
    *,
    since: str | None = None,
    limit: int | None = None,
) -> tuple[Screening, ...]:
    """Return screenings sorted oldest first, optionally since ``since`` (inclusive)."""
    if since:
        rows = conn.execute(
            "SELECT * FROM screenings WHERE created_at >= ? ORDER BY created_at ASC, id ASC",
            (since,),
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM screenings ORDER BY created_at ASC, id ASC").fetchall()
    records = _rows_to_records(rows, row_to_screening, "screenings")
    if limit is not None and len(records) > limit:
        return records[-limit:]
    return records


def latest_screening(conn: sqlite3.Connection) -> Screening | None:
    """Return the most recent screening of any instrument, or ``None``."""
    rows = conn.execute(
        "SELECT * FROM screenings ORDER BY created_at DESC, id DESC LIMIT 1"
    ).fetchall()
    records = _rows_to_records(rows, row_to_screening, "screenings")
    return records[0] if records else None


def screening_risk_active(conn: sqlite3.Connection) -> bool:
    """Return True when the most recent screening has its risk flag set.

    The AI companion stays paused while this is True (Prompt B §7.5).
    """
    latest = latest_screening(conn)
    return bool(latest and latest.risk_flag)


# ---------------------------------------------------------------------------
# Chat
# ---------------------------------------------------------------------------


def append_chat_message(conn: sqlite3.Connection, message: ChatMessage) -> int:
    """Append one chat message and return its row id. Raises ``ValueError`` if invalid."""
    validated = validate_chat_message(message)
    created_at = validated.created_at or utc_now_iso()
    with conn:
        cursor = conn.execute(
            "INSERT INTO chat_messages (created_at, role, content) VALUES (?, ?, ?)",
            (created_at, Role(validated.role).value, validated.content),
        )
    return int(cursor.lastrowid or 0)


def load_chat_messages(
    conn: sqlite3.Connection,
    *,
    limit: int | None = None,
) -> tuple[ChatMessage, ...]:
    """Return chat messages oldest first, keeping only the newest ``limit`` if given."""
    rows = conn.execute("SELECT * FROM chat_messages ORDER BY created_at ASC, id ASC").fetchall()
    records = _rows_to_records(rows, row_to_chat_message, "chat_messages")
    if limit is not None and len(records) > limit:
        return records[-limit:]
    return records


def delete_conversation(conn: sqlite3.Connection) -> int:
    """Delete every stored chat message and return how many rows were removed."""
    with conn:
        cursor = conn.execute("DELETE FROM chat_messages")
    return int(cursor.rowcount if cursor.rowcount > 0 else 0)


# ---------------------------------------------------------------------------
# Metadata and export
# ---------------------------------------------------------------------------


def get_meta(conn: sqlite3.Connection, key: str, default: str | None = None) -> str | None:
    """Return the stored metadata value for ``key``, or ``default`` when absent."""
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return str(row["value"]) if row is not None else default


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    """Store ``value`` under ``key``, replacing any previous value."""
    with conn:
        conn.execute(
            "INSERT INTO app_meta (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def export_all_data(conn: sqlite3.Connection) -> dict[str, Any]:
    """Return every stored record as plain JSON-serialisable data.

    Log metadata is included so an export can be understood later; no secrets are
    stored in the database, so nothing sensitive is added.
    """
    return {
        "app_version": APP_VERSION,
        "schema_version": get_meta(conn, SCHEMA_VERSION_KEY, SCHEMA_VERSION),
        "exported_at": utc_now_iso(),
        "check_ins": [asdict(record) for record in list_check_ins(conn)],
        "screenings": [
            {
                **asdict(record),
                "instrument": Instrument(record.instrument).value,
                "severity": Severity(record.severity).value,
                "answers": list(record.answers),
            }
            for record in list_screenings(conn)
        ],
        "chat_messages": [
            {**asdict(message), "role": Role(message.role).value}
            for message in load_chat_messages(conn)
        ],
    }
