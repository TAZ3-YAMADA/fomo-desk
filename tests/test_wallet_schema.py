"""Schema, dossier import, and negative-control tests for the paper wallet registry."""

from __future__ import annotations

import json
import sqlite3
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from desk.db import (  # noqa: E402
    NEGATIVE_CONTROL_LABELS,
    PAPER_MODE,
    SCHEMA,
    connect,
    get_labeled_wallet,
    insert_whale_signal,
    upsert_labeled_wallet,
)
from desk.dossiers import DossierImportError, import_dossier, import_path  # noqa: E402
from desk.whitelist import WhitelistRefused, add_whitelist, get_whitelist  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures"
DOSSIERS = FIXTURES / "dossiers"
OWNER_ADDRESS = "FiXtureAwner1111111111111111111111111111111"
TEXT_SUFFIXES = {
    ".py",
    ".md",
    ".js",
    ".css",
    ".html",
    ".json",
    ".yml",
    ".yaml",
    ".svg",
    ".txt",
}


class SchemaTests(unittest.TestCase):
    def test_mode_is_paper(self) -> None:
        self.assertEqual(PAPER_MODE, "paper")

    def test_schema_creates_wallet_tables(self) -> None:
        conn = connect()
        tables = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        views = {
            row["name"]
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'view'"
            )
        }
        self.assertTrue({"labeled_wallets", "whitelist", "whale_signals"} <= tables)
        self.assertIn("whales", views)
        wallet = conn.execute("SELECT * FROM whales").fetchall()
        self.assertEqual(wallet, [])
        conn.close()

    def test_schema_init_is_idempotent(self) -> None:
        conn = connect()
        from desk.db import init_db

        init_db(conn)
        init_db(conn)
        count = conn.execute(
            "SELECT count(*) AS n FROM labeled_wallets"
        ).fetchone()["n"]
        self.assertEqual(count, 0)
        conn.close()

    def test_negative_control_is_in_schema_and_constant(self) -> None:
        self.assertIn("end837", NEGATIVE_CONTROL_LABELS)
        self.assertIn("end837", SCHEMA)

    def test_display_note_is_not_indexed(self) -> None:
        conn = connect()
        rows = conn.execute(
            "SELECT type, sql FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
        for row in rows:
            sql = (row["sql"] or "").lower()
            self.assertNotIn("display_note", sql)
            self.assertNotIn("handle", sql)
        conn.close()

    def test_provenance_is_required(self) -> None:
        conn = connect()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO labeled_wallets (
                    wallet_label, solana_address, provenance, updated_at
                ) VALUES ('orphan', NULL, '', '2026-11-05T00:00:00Z')
                """
            )
        conn.close()

    def test_signal_source_is_rpc_or_replay_only(self) -> None:
        conn = connect()
        upsert_labeled_wallet(
            conn,
            wallet_label="alpha-desk",
            solana_address=OWNER_ADDRESS,
            provenance="owner pasted the address",
        )
        before = conn.execute("SELECT count(*) AS n FROM whitelist").fetchone()["n"]
        stored = insert_whale_signal(
            conn,
            event_id="sig-replay-1",
            wallet_label="alpha-desk",
            side="buy",
            token_mint="mint-1",
            ts=1_700_000_000,
            source="replay",
            size_usd=12.5,
            raw={"event_id": "sig-replay-1"},
        )
        self.assertEqual(stored["source"], "replay")
        self.assertEqual(stored["chain"], "solana")
        self.assertEqual(stored["token_mint"], "mint-1")
        self.assertEqual(stored["user_id"], OWNER_ADDRESS)
        after = conn.execute("SELECT count(*) AS n FROM whitelist").fetchone()["n"]
        self.assertEqual(before, after)
        with self.assertRaises(ValueError):
            insert_whale_signal(
                conn,
                event_id="sig-bad-source",
                wallet_label="alpha-desk",
                side="sell",
                token_mint="mint-1",
                ts=1_700_000_001,
                source="other",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO whale_signals (
                    event_id, wallet_label, user_id, side, token_mint, chain,
                    size_usd, ts, source, raw_json
                ) VALUES ('sig-raw', 'alpha-desk', ?, 'buy', 'mint-1', 'solana', NULL, 1, 'other', NULL)
                """,
                (OWNER_ADDRESS,),
            )
        conn.close()

    def test_signal_requires_labeled_wallet_and_pubkey(self) -> None:
        conn = connect()
        upsert_labeled_wallet(
            conn,
            wallet_label="alpha-desk",
            solana_address=OWNER_ADDRESS,
            provenance="owner pasted the address",
        )
        with self.assertRaises(ValueError):
            insert_whale_signal(
                conn,
                event_id="sig-missing",
                wallet_label="missing-wallet",
                side="buy",
                token_mint="mint-1",
                ts=1_700_000_002,
                source="replay",
            )
        with self.assertRaises(ValueError):
            insert_whale_signal(
                conn,
                event_id="sig-mismatch",
                wallet_label="alpha-desk",
                side="buy",
                token_mint="mint-1",
                ts=1_700_000_003,
                source="rpc",
                user_id="FiXtureA1pha11111111111111111111111111111111",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                INSERT INTO whale_signals (
                    event_id, wallet_label, user_id, side, token_mint, chain,
                    size_usd, ts, source, raw_json
                ) VALUES (
                    'sig-raw-missing', 'missing-wallet', ?, 'buy', 'mint-1',
                    'solana', NULL, 1, 'replay', NULL
                )
                """,
                (OWNER_ADDRESS,),
            )
        conn.close()


class ImportTests(unittest.TestCase):
    def test_import_upserts_same_wallet_label(self) -> None:
        conn = connect()
        import_path(conn, DOSSIERS)
        rows = conn.execute(
            "SELECT wallet_label, solana_address, display_note, confidence, provenance "
            "FROM labeled_wallets ORDER BY wallet_label"
        ).fetchall()
        labels = [row["wallet_label"] for row in rows]
        self.assertEqual(labels, ["alpha-desk", "end837", "queue-note"])
        alpha = get_labeled_wallet(conn, "alpha-desk")
        assert alpha is not None
        self.assertEqual(
            alpha["solana_address"],
            "FiXtureA1pha22222222222222222222222222222222",
        )
        self.assertEqual(alpha["display_note"], "desk-note-renamed")
        self.assertEqual(alpha["confidence"], "high")
        self.assertEqual(alpha["provenance"], "dossier_import")
        self.assertIsNone(get_labeled_wallet(conn, "desk-note"))
        self.assertIsNone(get_labeled_wallet(conn, "desk-note-renamed"))
        self.assertIsNone(get_whitelist(conn, "alpha-desk"))
        queue = get_labeled_wallet(conn, "queue-note")
        assert queue is not None
        self.assertIsNone(queue["solana_address"])
        self.assertEqual(queue["display_note"], "waiting")
        self.assertEqual(queue["status"], "unreviewed")
        conn.close()

    def test_second_import_of_one_file_keeps_a_single_row(self) -> None:
        conn = connect()
        first = import_path(conn, DOSSIERS / "alpha.json")
        second = import_path(conn, DOSSIERS / "alpha.json")
        count = conn.execute(
            "SELECT count(*) AS n FROM labeled_wallets WHERE wallet_label = 'alpha-desk'"
        ).fetchone()["n"]
        self.assertEqual(count, 1)
        self.assertEqual(first[0]["wallet_label"], "alpha-desk")
        self.assertEqual(second[0]["solana_address"], first[0]["solana_address"])
        self.assertEqual(second[0]["display_note"], "desk-note")
        conn.close()

    def test_handle_only_dossier_is_refused(self) -> None:
        conn = connect()
        with self.assertRaises(DossierImportError):
            import_path(conn, FIXTURES / "invalid" / "handle_only.json")
        count = conn.execute("SELECT count(*) AS n FROM labeled_wallets").fetchone()["n"]
        self.assertEqual(count, 0)
        conn.close()

    def test_dossier_cannot_self_promote_to_paper_copy(self) -> None:
        conn = connect()
        imported = import_dossier(
            conn,
            {
                "wallet_label": "alpha-desk",
                "handle": "desk-note",
                "solana": "FiXtureA1pha11111111111111111111111111111111",
                "status": "paper_copy",
                "tier": "A",
            },
        )
        assert isinstance(imported, dict)
        self.assertEqual(imported["status"], "unreviewed")
        self.assertIsNone(imported["whitelist_status"])
        self.assertIsNone(imported["tier"])
        conn.close()

    def test_one_label_per_solana_address(self) -> None:
        conn = connect()
        upsert_labeled_wallet(
            conn,
            wallet_label="one",
            solana_address=OWNER_ADDRESS,
            provenance="owner form",
        )
        with self.assertRaises(sqlite3.IntegrityError):
            upsert_labeled_wallet(
                conn,
                wallet_label="two",
                solana_address=OWNER_ADDRESS,
                provenance="owner form",
            )
        conn.close()


class WhitelistTests(unittest.TestCase):
    def test_consented_wallet_can_be_paper_copy(self) -> None:
        conn = connect()
        upsert_labeled_wallet(
            conn,
            wallet_label="alpha-desk",
            solana_address=OWNER_ADDRESS,
            provenance="owner pasted the address",
        )
        add_whitelist(
            conn,
            wallet_label="alpha-desk",
            status="observe",
            tier="C",
            provenance="owner telegram confirmation",
            added_by="owner",
        )
        row = add_whitelist(
            conn,
            wallet_label="alpha-desk",
            status="paper_copy",
            tier="B",
            cap_usd=50,
            provenance="owner telegram confirmation",
            added_by="owner",
        )
        self.assertEqual(row["status"], "paper_copy")
        self.assertEqual(row["tier"], "B")
        self.assertEqual(row["cap_usd"], 50.0)
        conn.close()

    def test_end837_import_is_blocked(self) -> None:
        conn = connect()
        imported = import_path(conn, DOSSIERS / "end837.json")
        import_path(conn, DOSSIERS / "end837.json")
        self.assertEqual(len(imported), 1)
        self.assertEqual(
            conn.execute("SELECT count(*) AS n FROM labeled_wallets").fetchone()["n"],
            1,
        )
        self.assertEqual(
            conn.execute("SELECT count(*) AS n FROM whitelist").fetchone()["n"],
            1,
        )
        row = imported[0]
        self.assertEqual(row["wallet_label"], "end837")
        self.assertEqual(row["status"], "blocked")
        self.assertEqual(row["whitelist_status"], "blocked")
        self.assertEqual(row["tier"], "blocked")
        self.assertEqual(row["provenance"], "dossier_import")
        self.assertEqual(row["display_note"], "end837")
        self.assertEqual(
            row["solana_address"],
            "FiXtureEnd837111111111111111111111111111",
        )
        stored = get_whitelist(conn, "END837")
        assert stored is not None
        self.assertEqual(stored["wallet_label"], "end837")
        self.assertEqual(stored["status"], "blocked")
        self.assertEqual(stored["tier"], "blocked")
        conn.close()

    def test_end837_cannot_be_paper_copy(self) -> None:
        conn = connect()
        import_path(conn, DOSSIERS / "end837.json")
        with self.assertRaises(WhitelistRefused):
            add_whitelist(
                conn,
                wallet_label="end837",
                status="paper_copy",
                tier="A",
                provenance="should fail",
                added_by="owner",
            )
        with self.assertRaises(WhitelistRefused):
            add_whitelist(
                conn,
                wallet_label="END837",
                status="observe",
                tier="C",
                provenance="should fail",
                added_by="owner",
            )
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE whitelist
                SET status = 'paper_copy', tier = 'A'
                WHERE wallet_label = 'end837'
                """
            )
        conn.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE labeled_wallets
                SET status = 'unreviewed'
                WHERE wallet_label = 'end837'
                """
            )
        conn.rollback()
        still = get_whitelist(conn, "end837")
        assert still is not None
        self.assertEqual(still["status"], "blocked")
        self.assertEqual(still["tier"], "blocked")
        conn.close()

    def test_blocked_wallet_cannot_be_whitelisted(self) -> None:
        conn = connect()
        address = "FiXtureB1ock11111111111111111111111111111111"
        upsert_labeled_wallet(
            conn,
            wallet_label="control-b",
            solana_address=address,
            provenance="owner said stop",
            status="blocked",
        )
        with self.assertRaises(WhitelistRefused):
            add_whitelist(
                conn,
                wallet_label="control-b",
                status="paper_copy",
                tier="A",
                provenance="owner said stop",
                added_by="owner",
            )
        self.assertIsNone(get_whitelist(conn, "control-b"))
        conn.close()

    def test_missing_address_cannot_be_whitelisted(self) -> None:
        conn = connect()
        import_path(conn, DOSSIERS / "unresolved.json")
        with self.assertRaises(WhitelistRefused):
            add_whitelist(
                conn,
                wallet_label="queue-note",
                status="observe",
                tier="C",
                provenance="owner has not sent an address",
                added_by="owner",
            )
        conn.close()


class BoundaryTests(unittest.TestCase):
    def test_no_banned_api_strings(self) -> None:
        needles = ("fomo" + "api", "fomo-" + "api", "fomo_" + "api")
        hits: list[str] = []
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8").lower()
            for needle in needles:
                if needle in text:
                    hits.append(f"{path.relative_to(ROOT)}:{needle}")
        self.assertEqual(hits, [])

    def test_package_has_no_live_execution_terms(self) -> None:
        text = "\n".join(path.read_text(encoding="utf-8") for path in (ROOT / "desk").glob("*.py"))
        lowered = text.lower()
        self.assertNotIn("executionport", lowered)
        self.assertNotIn("private_key", lowered)
        self.assertNotIn("seed phrase", lowered)
        self.assertNotIn("sign_transaction", lowered)


class TierAFixtureTests(unittest.TestCase):
    def test_tier_a_observe_and_end837_blocked(self) -> None:
        conn = connect()
        path = FIXTURES / "paper-fixtures-v1.2-merged.json"
        payload = json.loads(path.read_text(encoding="utf-8"))
        template = payload["provenance_template"]
        self.assertIn("official-FOMO-signed-in-30d", template)
        self.assertIn("third-party-resolved", template)
        imported = import_path(conn, path)
        import_path(conn, path)
        ranked = sorted(payload["tier_a_whitelist"], key=lambda entry: entry["official_rank"])
        self.assertEqual(
            [row["wallet_label"] for row in imported],
            [entry["wallet_label"] for entry in ranked],
        )
        observe_labels = [
            entry["wallet_label"] for entry in ranked if entry["status"] == "observe"
        ]
        self.assertEqual(
            observe_labels,
            [
                "g41t3r98",
                "0xbr9",
                "cosby",
                "zelda89",
                "oura456",
                "awtorkowski7",
                "pressingprofits",
                "vvvvvvvvvv",
                "yuren477",
            ],
        )
        self.assertEqual(
            [entry["official_rank"] for entry in ranked if entry["status"] == "observe"],
            [2, 3, 4, 5, 6, 7, 9, 12, 15],
        )
        gaps = ["Quanterty", "aiwass", "SavageCountry", "bystevenr", "xfilesboy"]
        self.assertEqual(payload["gaps_no_solana_excluded"], gaps)
        imported_labels = {row["wallet_label"].casefold() for row in imported}
        for name in gaps:
            self.assertNotIn(name.casefold(), imported_labels)
        self.assertEqual(len(imported), 10)
        self.assertEqual(
            conn.execute("SELECT count(*) AS n FROM labeled_wallets").fetchone()["n"],
            10,
        )
        self.assertEqual(
            conn.execute("SELECT count(*) AS n FROM whitelist").fetchone()["n"],
            10,
        )
        by_label = {row["wallet_label"]: row for row in imported}
        self.assertEqual(set(by_label), {entry["wallet_label"] for entry in ranked})
        observe = []
        for entry in ranked:
            row = by_label[entry["wallet_label"]]
            expected_note = entry.get("display_note") or entry["wallet_label"]
            self.assertEqual(row["wallet_pubkey"], entry["wallet_pubkey"])
            self.assertEqual(row["solana_address"], entry["wallet_pubkey"])
            self.assertEqual(row["display_note"], expected_note)
            self.assertEqual(row["provenance"], template)
            self.assertEqual(row["consent_provenance"], template)
            self.assertEqual(row["whitelist_entry_id"], entry["whitelist_entry_id"])
            self.assertFalse(row["live_whitelist_consented"])
            self.assertFalse(row["paper_copy_allowed"])
            if entry["wallet_label"] == "end837" or entry["forced_blocked_nc"]:
                self.assertEqual(entry["status"], "blocked")
                self.assertEqual(entry["tier"], "blocked")
                self.assertTrue(entry["forced_blocked_nc"])
                self.assertEqual(row["status"], "blocked")
                self.assertEqual(row["whitelist_status"], "blocked")
                self.assertEqual(row["tier"], "blocked")
                self.assertEqual(row["whitelist_entry_id"], "paper-nc-end837")
            else:
                observe.append(row)
                self.assertEqual(entry["status"], "observe")
                self.assertEqual(row["whitelist_status"], "observe")
                self.assertEqual(row["tier"], "A")
        self.assertEqual(len(observe), 9)
        self.assertEqual(
            conn.execute(
                "SELECT count(*) AS n FROM whitelist WHERE status = 'paper_copy'"
            ).fetchone()["n"],
            0,
        )
        stored = get_whitelist(conn, "g41t3r98")
        assert stored is not None
        self.assertEqual(stored["status"], "observe")
        self.assertEqual(stored["paper_copy_allowed"], 0)
        self.assertEqual(get_labeled_wallet(conn, "g41t3r98")["display_note"], "G41T3R98")
        with self.assertRaises(WhitelistRefused):
            add_whitelist(
                conn,
                wallet_label="end837",
                status="paper_copy",
                tier="A",
                provenance="should fail",
                added_by="owner",
            )
        with self.assertRaises(WhitelistRefused) as locked:
            add_whitelist(
                conn,
                wallet_label="zelda89",
                status="paper_copy",
                tier="A",
                provenance=payload["provenance_template"],
                added_by="owner",
            )
        self.assertIn("PAPER_COPY_NOT_ALLOWED", str(locked.exception))
        with self.assertRaises(sqlite3.IntegrityError):
            conn.execute(
                """
                UPDATE whitelist
                SET status = 'paper_copy', tier = 'A', paper_copy_allowed = 1
                WHERE wallet_label = 'end837'
                """
            )
        conn.rollback()
        still = get_whitelist(conn, "end837")
        assert still is not None
        self.assertEqual(still["status"], "blocked")
        self.assertEqual(still["tier"], "blocked")
        self.assertEqual(still["paper_copy_allowed"], 0)
        self.assertEqual(still["live_whitelist_consented"], 0)
        conn.close()

    def test_tier_a_refuses_missing_pubkey(self) -> None:
        conn = connect()
        with self.assertRaises(DossierImportError):
            import_dossier(
                conn,
                {
                    "tier_a_whitelist": [
                        {
                            "whitelist_entry_id": "paper-b-11-no-address",
                            "wallet_label": "tier-b-example",
                            "tier": "B",
                            "consent_provenance": "third-party-resolved · FomoRadar 30d · 2026-11-04 19:09 UTC",
                            "status": "observe",
                        }
                    ]
                },
            )
        count = conn.execute("SELECT count(*) AS n FROM labeled_wallets").fetchone()["n"]
        self.assertEqual(count, 0)
        conn.close()


if __name__ == "__main__":
    unittest.main()
