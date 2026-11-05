"""SQLite schema for paper-only, wallet-centric whale labels.

The Pages book (``state.json`` positions) is symbol display data. This repo
has no mint watchlist and no coins table. These tables sit beside that book:

- ``labeled_wallets`` — public address, provenance, confidence, status
- ``whales`` — read view of ``labeled_wallets``
- ``whitelist`` — observe / paper_copy / paused / blocked
- ``whale_signals`` — tx-signature events from ``rpc`` or ``replay`` only

``display_note`` is a human note. It is not indexed. ``end837`` is hardcoded
in the triggers below and in ``NEGATIVE_CONTROL_LABELS``; keep them together.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PAPER_MODE = "paper"

LABELED_STATUSES = frozenset({"unreviewed", "blocked"})
CONFIDENCE_VALUES = frozenset({"unknown", "low", "medium", "high"})
SIGNAL_SOURCES = frozenset({"rpc", "replay"})
SIGNAL_SIDES = frozenset({"buy", "sell"})
NEGATIVE_CONTROL_LABELS = frozenset({"end837"})

_B58_ALPHABET = frozenset(
    "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
)
_SOLANA_SENTINELS = frozenset(
    {"", "unresolved", "unknown", "none", "null", "n/a", "na", "-", "—"}
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS labeled_wallets (
    wallet_label TEXT PRIMARY KEY,
    solana_address TEXT,
    display_note TEXT,
    provenance TEXT NOT NULL,
    confidence TEXT NOT NULL DEFAULT 'unknown',
    status TEXT NOT NULL DEFAULT 'unreviewed',
    dossier_json TEXT,
    updated_at TEXT NOT NULL,
    CHECK (length(wallet_label) BETWEEN 1 AND 128),
    CHECK (length(trim(provenance)) > 0),
    CHECK (confidence IN ('unknown', 'low', 'medium', 'high')),
    CHECK (status IN ('unreviewed', 'blocked')),
    CHECK (display_note IS NULL OR length(display_note) <= 500),
    CHECK (
        solana_address IS NULL
        OR length(solana_address) BETWEEN 32 AND 44
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS labeled_wallets_solana_uidx
ON labeled_wallets(solana_address)
WHERE solana_address IS NOT NULL;

CREATE VIEW IF NOT EXISTS whales AS
SELECT
    wallet_label,
    solana_address,
    display_note,
    provenance,
    confidence,
    status,
    dossier_json,
    updated_at
FROM labeled_wallets;

CREATE TABLE IF NOT EXISTS whitelist (
    wallet_label TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    tier TEXT NOT NULL,
    cap_usd REAL,
    note TEXT,
    added_at TEXT NOT NULL,
    added_by TEXT NOT NULL,
    provenance TEXT NOT NULL,
    FOREIGN KEY (wallet_label) REFERENCES labeled_wallets(wallet_label),
    CHECK (status IN ('observe', 'paper_copy', 'paused', 'blocked')),
    CHECK (tier IN ('A', 'B', 'C', 'blocked')),
    CHECK (
        (status = 'blocked' AND tier = 'blocked')
        OR (status != 'blocked' AND tier != 'blocked')
    ),
    CHECK (length(trim(provenance)) > 0),
    CHECK (length(trim(added_by)) > 0),
    CHECK (cap_usd IS NULL OR cap_usd >= 0)
);

CREATE TABLE IF NOT EXISTS whale_signals (
    event_id TEXT PRIMARY KEY,
    wallet_label TEXT NOT NULL,
    side TEXT NOT NULL,
    token_mint TEXT NOT NULL,
    chain TEXT NOT NULL DEFAULT 'solana',
    size_usd REAL,
    ts INTEGER NOT NULL,
    source TEXT NOT NULL,
    raw_json TEXT,
    CHECK (length(event_id) BETWEEN 1 AND 128),
    CHECK (side IN ('buy', 'sell')),
    CHECK (length(token_mint) BETWEEN 1 AND 64),
    CHECK (chain = 'solana'),
    CHECK (source IN ('rpc', 'replay')),
    CHECK (ts > 0),
    CHECK (size_usd IS NULL OR size_usd >= 0)
);

CREATE TRIGGER IF NOT EXISTS labeled_end837_insert
BEFORE INSERT ON labeled_wallets
WHEN lower(trim(NEW.wallet_label)) = 'end837'
 AND (NEW.wallet_label != 'end837' OR NEW.status != 'blocked')
BEGIN
    SELECT RAISE(ABORT, 'end837 must be stored canonically as blocked');
END;

CREATE TRIGGER IF NOT EXISTS labeled_end837_update
BEFORE UPDATE ON labeled_wallets
WHEN lower(trim(OLD.wallet_label)) = 'end837'
 AND (NEW.wallet_label != 'end837' OR NEW.status != 'blocked')
BEGIN
    SELECT RAISE(ABORT, 'end837 must stay blocked');
END;

CREATE TRIGGER IF NOT EXISTS labeled_blocked_sticks
BEFORE UPDATE ON labeled_wallets
WHEN OLD.status = 'blocked' AND NEW.status != 'blocked'
BEGIN
    SELECT RAISE(ABORT, 'blocked wallet status cannot be cleared');
END;

CREATE TRIGGER IF NOT EXISTS whitelist_end837_insert
BEFORE INSERT ON whitelist
WHEN lower(trim(NEW.wallet_label)) = 'end837'
 AND (
    NEW.wallet_label != 'end837'
    OR NEW.status != 'blocked'
    OR NEW.tier != 'blocked'
 )
BEGIN
    SELECT RAISE(ABORT, 'end837 cannot be whitelisted');
END;

CREATE TRIGGER IF NOT EXISTS whitelist_end837_update
BEFORE UPDATE ON whitelist
WHEN lower(trim(OLD.wallet_label)) = 'end837'
 AND (
    NEW.wallet_label != 'end837'
    OR NEW.status != 'blocked'
    OR NEW.tier != 'blocked'
 )
BEGIN
    SELECT RAISE(ABORT, 'end837 cannot be whitelisted');
END;

CREATE TRIGGER IF NOT EXISTS whitelist_blocked_sticks
BEFORE UPDATE ON whitelist
WHEN OLD.status = 'blocked'
 AND (NEW.status != 'blocked' OR NEW.tier != 'blocked')
BEGIN
    SELECT RAISE(ABORT, 'blocked whitelist rows cannot be promoted');
END;
"""


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def canonical_label(wallet_label: str) -> str:
    text = str(wallet_label).strip()
    if not text:
        raise ValueError("wallet_label is required")
    if text.casefold() in NEGATIVE_CONTROL_LABELS:
        return "end837"
    return text


def is_negative_control(wallet_label: str) -> bool:
    return str(wallet_label).strip().casefold() in NEGATIVE_CONTROL_LABELS


def normalize_solana(value: Any) -> str | None:
    """Return a public address string, or None when the dossier has no address.

    Sentinels such as ``unresolved`` become None. This does not look up a
    display name and does not call a network.
    """
    if value is None:
        return None
    text = str(value).strip()
    if text.casefold() in _SOLANA_SENTINELS:
        return None
    if not (32 <= len(text) <= 44) or any(ch not in _B58_ALPHABET for ch in text):
        raise ValueError("solana must be a public address")
    return text


def connect(path: str | Path = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    init_db(conn)
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA user_version = 1")
    conn.commit()


def as_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return {key: row[key] for key in row.keys()}


def get_labeled_wallet(
    conn: sqlite3.Connection, wallet_label: str
) -> dict[str, Any] | None:
    label = canonical_label(wallet_label)
    row = conn.execute(
        "SELECT * FROM labeled_wallets WHERE wallet_label = ?",
        (label,),
    ).fetchone()
    return as_dict(row)


def upsert_labeled_wallet(
    conn: sqlite3.Connection,
    *,
    wallet_label: str,
    solana_address: Any,
    provenance: str,
    display_note: str | None = None,
    confidence: str = "unknown",
    status: str = "unreviewed",
    dossier_json: str | None = None,
) -> dict[str, Any]:
    label = canonical_label(wallet_label)
    provenance = str(provenance).strip()
    if not provenance:
        raise ValueError("provenance is required")
    if is_negative_control(label):
        status = "blocked"
    if status not in LABELED_STATUSES:
        raise ValueError("status must be unreviewed or blocked")
    confidence = str(confidence).strip().casefold()
    if confidence not in CONFIDENCE_VALUES:
        raise ValueError("confidence must be unknown, low, medium, or high")
    solana = normalize_solana(solana_address)
    note = None if display_note is None else str(display_note).strip() or None
    if note is not None and len(note) > 500:
        raise ValueError("display_note is too long")
    now = utc_now()
    try:
        conn.execute(
            """
            INSERT INTO labeled_wallets (
                wallet_label, solana_address, display_note, provenance,
                confidence, status, dossier_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(wallet_label) DO UPDATE SET
                solana_address = excluded.solana_address,
                display_note = excluded.display_note,
                provenance = excluded.provenance,
                confidence = excluded.confidence,
                status = CASE
                    WHEN labeled_wallets.status = 'blocked' THEN 'blocked'
                    ELSE excluded.status
                END,
                dossier_json = excluded.dossier_json,
                updated_at = excluded.updated_at
            """,
            (label, solana, note, provenance, confidence, status, dossier_json, now),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    wallet = get_labeled_wallet(conn, label)
    if wallet is None:
        raise RuntimeError("labeled wallet upsert did not persist")
    return wallet


def insert_whale_signal(
    conn: sqlite3.Connection,
    *,
    event_id: str,
    wallet_label: str,
    side: str,
    token_mint: str,
    ts: int,
    source: str,
    size_usd: float | None = None,
    raw: dict[str, Any] | None = None,
    chain: str = "solana",
) -> dict[str, Any]:
    """Store one paper signal. This does not whitelist the wallet."""
    event = str(event_id).strip()
    if not event:
        raise ValueError("event_id is required")
    label = canonical_label(wallet_label)
    if side not in SIGNAL_SIDES:
        raise ValueError("side must be buy or sell")
    mint = str(token_mint).strip()
    if not mint:
        raise ValueError("token_mint is required")
    if source not in SIGNAL_SOURCES:
        raise ValueError("source must be rpc or replay")
    if chain != "solana":
        raise ValueError("chain must be solana")
    if isinstance(ts, bool) or not isinstance(ts, int) or ts <= 0:
        raise ValueError("ts must be a positive unix second")
    if size_usd is not None and (
        isinstance(size_usd, bool) or not isinstance(size_usd, (int, float)) or size_usd < 0
    ):
        raise ValueError("size_usd must be a non-negative number or null")
    raw_json = None if raw is None else json.dumps(raw, separators=(",", ":"), sort_keys=True)
    size = None if size_usd is None else float(size_usd)
    try:
        conn.execute(
            """
            INSERT INTO whale_signals (
                event_id, wallet_label, side, token_mint, chain,
                size_usd, ts, source, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (event, label, side, mint, chain, size, ts, source, raw_json),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    row = conn.execute(
        "SELECT * FROM whale_signals WHERE event_id = ?",
        (event,),
    ).fetchone()
    result = as_dict(row)
    if result is None:
        raise RuntimeError("whale signal insert did not persist")
    return result
