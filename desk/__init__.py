"""Paper-only wallet registry for the FOMO desk.

Watching keys off owner-published Solana addresses. This package does not
trade, sign, or resolve a display name to a wallet.
"""

from desk.db import (
    PAPER_MODE,
    connect,
    get_labeled_wallet,
    init_db,
    insert_whale_signal,
    upsert_labeled_wallet,
)
from desk.dossiers import DossierImportError, import_dossier, import_path
from desk.whitelist import WhitelistRefused, add_whitelist, block_wallet, get_whitelist

__all__ = [
    "PAPER_MODE",
    "DossierImportError",
    "WhitelistRefused",
    "add_whitelist",
    "block_wallet",
    "connect",
    "get_labeled_wallet",
    "get_whitelist",
    "import_dossier",
    "import_path",
    "init_db",
    "insert_whale_signal",
    "upsert_labeled_wallet",
]
