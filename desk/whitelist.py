"""Whitelist writes for paper copy.

``add_whitelist`` is the active-list helper. It refuses the negative control
``end837`` and any wallet whose registry status is already ``blocked``.
Blocked rows are recorded with ``block_wallet``, which is not a promotion.
"""

from __future__ import annotations

import sqlite3
from typing import Any

from desk.db import (
    as_dict,
    canonical_label,
    get_labeled_wallet,
    is_negative_control,
    utc_now,
)

ADD_STATUSES = frozenset({"observe", "paper_copy", "paused"})
ADD_TIERS = frozenset({"A", "B", "C"})


class WhitelistRefused(Exception):
    """The wallet cannot enter the active paper whitelist."""


def get_whitelist(
    conn: sqlite3.Connection, wallet_label: str
) -> dict[str, Any] | None:
    label = canonical_label(wallet_label)
    row = conn.execute(
        "SELECT * FROM whitelist WHERE wallet_label = ?",
        (label,),
    ).fetchone()
    return as_dict(row)


def _require_text(value: str, field: str) -> str:
    text = str(value).strip()
    if not text:
        raise WhitelistRefused(f"{field} is required")
    return text


def _cap(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise WhitelistRefused("cap_usd must be a number or null")
    if value < 0:
        raise WhitelistRefused("cap_usd must be >= 0")
    return float(value)


def _refuse_if_control(conn: sqlite3.Connection, label: str) -> dict[str, Any]:
    if is_negative_control(label):
        raise WhitelistRefused("end837 is a negative control and cannot be whitelisted")
    wallet = get_labeled_wallet(conn, label)
    if wallet is None:
        raise WhitelistRefused("wallet_label is not in labeled_wallets")
    if wallet["status"] == "blocked":
        raise WhitelistRefused("blocked wallets cannot be whitelisted")
    if not wallet["solana_address"]:
        raise WhitelistRefused("whitelist requires a public solana address")
    existing = get_whitelist(conn, label)
    if existing is not None and existing["status"] == "blocked":
        raise WhitelistRefused("blocked whitelist rows cannot be promoted")
    return wallet


def add_whitelist(
    conn: sqlite3.Connection,
    *,
    wallet_label: str,
    status: str,
    tier: str,
    provenance: str,
    added_by: str,
    cap_usd: float | None = None,
    note: str | None = None,
) -> dict[str, Any]:
    """Add or update an active whitelist row (observe, paper_copy, or paused)."""
    label = canonical_label(wallet_label)
    if status not in ADD_STATUSES:
        raise WhitelistRefused("status must be observe, paper_copy, or paused")
    if tier not in ADD_TIERS:
        raise WhitelistRefused("tier must be A, B, or C")
    provenance = _require_text(provenance, "provenance")
    added_by = _require_text(added_by, "added_by")
    _refuse_if_control(conn, label)
    cap = _cap(cap_usd)
    now = utc_now()
    try:
        conn.execute(
            """
            INSERT INTO whitelist (
                wallet_label, status, tier, cap_usd, note, added_at, added_by, provenance
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(wallet_label) DO UPDATE SET
                status = excluded.status,
                tier = excluded.tier,
                cap_usd = excluded.cap_usd,
                note = excluded.note,
                added_at = excluded.added_at,
                added_by = excluded.added_by,
                provenance = excluded.provenance
            """,
            (label, status, tier, cap, note, now, added_by, provenance),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    row = get_whitelist(conn, label)
    if row is None:
        raise RuntimeError("whitelist write did not persist")
    return row


def block_wallet(
    conn: sqlite3.Connection,
    *,
    wallet_label: str,
    provenance: str,
    added_by: str,
    note: str | None = None,
) -> dict[str, Any]:
    """Record a blocked whitelist row. This is not an active whitelist add."""
    label = canonical_label(wallet_label)
    provenance = _require_text(provenance, "provenance")
    added_by = _require_text(added_by, "added_by")
    wallet = get_labeled_wallet(conn, label)
    if wallet is None:
        raise WhitelistRefused("cannot block an unknown wallet_label")
    now = utc_now()
    try:
        conn.execute(
            """
            UPDATE labeled_wallets
            SET status = 'blocked', updated_at = ?
            WHERE wallet_label = ?
            """,
            (now, label),
        )
        conn.execute(
            """
            INSERT INTO whitelist (
                wallet_label, status, tier, cap_usd, note, added_at, added_by, provenance
            ) VALUES (?, 'blocked', 'blocked', NULL, ?, ?, ?, ?)
            ON CONFLICT(wallet_label) DO UPDATE SET
                status = 'blocked',
                tier = 'blocked',
                cap_usd = NULL,
                note = excluded.note,
                added_at = excluded.added_at,
                added_by = excluded.added_by,
                provenance = excluded.provenance
            """,
            (label, note, now, added_by, provenance),
        )
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    row = get_whitelist(conn, label)
    if row is None:
        raise RuntimeError("blocked whitelist write did not persist")
    return row
