"""Import dossier JSON into the wallet registry.

A dossier may include ``handle`` and ``solana``. The Solana address is stored
with ``provenance`` ``dossier_import``. ``handle`` is copied into
``display_note`` only. A file with a handle and no ``wallet_label`` is refused.

``end837`` is forced to registry status ``blocked`` and whitelist
``tier=blocked`` / ``status=blocked``. Other dossiers stay ``unreviewed`` and
off the whitelist. A dossier cannot set itself to ``paper_copy``.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any

from desk.db import (
    get_labeled_wallet,
    is_negative_control,
    is_negative_control_pubkey,
    normalize_solana,
    upsert_labeled_wallet,
)
from desk.whitelist import WhitelistRefused, block_wallet, get_whitelist, record_observe

PROVENANCE_DOSSIER = "dossier_import"
_LABEL_KEYS = ("wallet_label", "label")
_SOLANA_KEYS = ("solana", "solana_address")


class DossierImportError(ValueError):
    """The dossier cannot be imported into the paper wallet registry."""


def _object(doc: Any) -> dict[str, Any]:
    if not isinstance(doc, dict):
        raise DossierImportError("dossier must be an object")
    return doc


def _wallet_label(doc: dict[str, Any]) -> str:
    for key in _LABEL_KEYS:
        value = doc.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    raise DossierImportError(
        "wallet_label is required; a handle is display-only and is not a watch key"
    )


def _solana(doc: dict[str, Any]) -> Any:
    for key in _SOLANA_KEYS:
        if key in doc and doc[key] is not None:
            return doc[key]
    return None


def _display_note(doc: dict[str, Any]) -> str | None:
    handle = doc.get("handle")
    if not isinstance(handle, str):
        return None
    text = handle.strip()
    return text or None


def _confidence(doc: dict[str, Any]) -> str:
    raw = doc.get("confidence")
    if not isinstance(raw, str):
        return "unknown"
    text = raw.strip().casefold()
    if text in {"unknown", "low", "medium", "high"}:
        return text
    return "unknown"


def _force_block(doc: dict[str, Any], label: str) -> bool:
    if is_negative_control(label):
        return True
    if doc.get("negative_control") is True:
        return True
    status = doc.get("status")
    return isinstance(status, str) and status.strip().casefold() == "blocked"


def _snapshot(conn: sqlite3.Connection, label: str) -> dict[str, Any]:
    wallet = get_labeled_wallet(conn, label)
    if wallet is None:
        raise DossierImportError("import did not persist the wallet")
    white = get_whitelist(conn, label)
    return {
        "wallet_label": wallet["wallet_label"],
        "solana_address": wallet["solana_address"],
        "display_note": wallet["display_note"],
        "provenance": wallet["provenance"],
        "confidence": wallet["confidence"],
        "status": wallet["status"],
        "dossier_json": wallet["dossier_json"],
        "updated_at": wallet["updated_at"],
        "whitelist_status": None if white is None else white["status"],
        "tier": None if white is None else white["tier"],
        "whitelist_entry_id": None if white is None else white["whitelist_entry_id"],
        "wallet_pubkey": wallet["solana_address"],
        "consent_provenance": None if white is None else white["consent_provenance"],
        "live_whitelist_consented": False
        if white is None
        else bool(white["live_whitelist_consented"]),
        "paper_copy_allowed": False if white is None else bool(white["paper_copy_allowed"]),
    }


def import_one(conn: sqlite3.Connection, doc: Any) -> dict[str, Any]:
    payload = _object(doc)
    raw_label = _wallet_label(payload)
    force_block = _force_block(payload, raw_label)
    archive = json.dumps(payload, separators=(",", ":"), sort_keys=True)
    try:
        wallet = upsert_labeled_wallet(
            conn,
            wallet_label=raw_label,
            solana_address=_solana(payload),
            provenance=PROVENANCE_DOSSIER,
            display_note=_display_note(payload),
            confidence=_confidence(payload),
            status="blocked" if force_block else "unreviewed",
            dossier_json=archive,
        )
    except ValueError as exc:
        raise DossierImportError(str(exc)) from exc
    if force_block:
        note = "negative control" if is_negative_control(raw_label) else "dossier blocked"
        block_wallet(
            conn,
            wallet_label=wallet["wallet_label"],
            provenance=PROVENANCE_DOSSIER,
            added_by=PROVENANCE_DOSSIER,
            note=note,
        )
    return _snapshot(conn, wallet["wallet_label"])


def _require_entry_text(entry: dict[str, Any], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str) or not value.strip():
        raise DossierImportError(f"{key} is required")
    return value.strip()


def _prepare_tier_a_entry(entry: Any) -> dict[str, Any]:
    payload = _object(entry)
    label = _require_entry_text(payload, "wallet_label")
    entry_id = _require_entry_text(payload, "whitelist_entry_id")
    provenance = payload.get("consent_provenance")
    if not isinstance(provenance, str) or not provenance.strip():
        provenance = payload.get("provenance")
    if not isinstance(provenance, str) or not provenance.strip():
        raise DossierImportError("consent_provenance is required")
    provenance = provenance.strip()
    raw_pubkey = payload.get("wallet_pubkey")
    if not isinstance(raw_pubkey, str) or not raw_pubkey.strip():
        raise DossierImportError(
            "wallet_pubkey is required; addresses are not resolved or invented"
        )
    try:
        pubkey = normalize_solana(raw_pubkey)
    except ValueError as exc:
        raise DossierImportError(str(exc)) from exc
    if pubkey is None:
        raise DossierImportError(
            "wallet_pubkey is required; addresses are not resolved or invented"
        )
    tier = str(payload.get("tier") or "A").strip()
    file_status = str(payload.get("status") or "").strip().casefold()
    force = (
        file_status == "blocked"
        or is_negative_control(label)
        or payload.get("forced_blocked_nc") is True
        or is_negative_control_pubkey(pubkey)
        or entry_id == "paper-a-01-end837"
    )
    if force:
        tier = "blocked"
    elif tier not in {"A", "B", "C"}:
        tier = "A"
    return {
        "wallet_label": label,
        "whitelist_entry_id": entry_id,
        "provenance": provenance,
        "pubkey": pubkey,
        "tier": tier,
        "force_blocked": force,
        "archive": json.dumps(payload, separators=(",", ":"), sort_keys=True),
    }


def _write_tier_a_entry(conn: sqlite3.Connection, prepared: dict[str, Any]) -> dict[str, Any]:
    """Write one shortlist row. Cap-math overrides in the file are not applied."""
    try:
        wallet = upsert_labeled_wallet(
            conn,
            wallet_label=prepared["wallet_label"],
            solana_address=prepared["pubkey"],
            provenance=prepared["provenance"],
            display_note=prepared["wallet_label"],
            status="blocked" if prepared["force_blocked"] else "unreviewed",
            dossier_json=prepared["archive"],
        )
        if prepared["force_blocked"]:
            block_wallet(
                conn,
                wallet_label=wallet["wallet_label"],
                provenance=prepared["provenance"],
                added_by="paper-shortlist",
                note="negative control",
                whitelist_entry_id=prepared["whitelist_entry_id"],
                consent_provenance=prepared["provenance"],
            )
        else:
            record_observe(
                conn,
                wallet_label=wallet["wallet_label"],
                tier=prepared["tier"],
                provenance=prepared["provenance"],
                added_by="paper-shortlist",
                whitelist_entry_id=prepared["whitelist_entry_id"],
                consent_provenance=prepared["provenance"],
            )
    except (ValueError, WhitelistRefused) as exc:
        raise DossierImportError(str(exc)) from exc
    return _snapshot(conn, wallet["wallet_label"])


def import_tier_a(conn: sqlite3.Connection, doc: Any) -> list[dict[str, Any]]:
    """Import ``tier_a_whitelist`` only.

    ``end837`` and ``forced_blocked_nc`` are stored blocked. Every other row
    is ``observe`` with paper copy and live consent left off. ``riskcontext_fixtures``
    are not applied.
    """
    payload = _object(doc)
    entries = payload.get("tier_a_whitelist")
    if not isinstance(entries, list):
        raise DossierImportError("tier_a_whitelist must be a list")
    prepared = [_prepare_tier_a_entry(entry) for entry in entries]
    return [_write_tier_a_entry(conn, item) for item in prepared]


def import_dossier(conn: sqlite3.Connection, doc: Any) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(doc, dict) and isinstance(doc.get("tier_a_whitelist"), list):
        return import_tier_a(conn, doc)
    if isinstance(doc, list):
        return [import_one(conn, item) for item in doc]
    return import_one(conn, doc)


def import_path(conn: sqlite3.Connection, path: str | Path) -> list[dict[str, Any]]:
    target = Path(path)
    files = sorted(item for item in target.glob("*.json") if item.is_file()) if target.is_dir() else [target]
    imported: list[dict[str, Any]] = []
    for file in files:
        payload = json.loads(file.read_text(encoding="utf-8"))
        result = import_dossier(conn, payload)
        if isinstance(result, list):
            imported.extend(result)
        else:
            imported.append(result)
    return imported
