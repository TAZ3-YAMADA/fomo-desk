# Desk

Static trading desk for GitHub Pages, served from the `main` branch at `/` (root).

https://taz3-yamada.github.io/fomo-desk/

Pages is not on until a repository admin saves it once:

1. Open https://github.com/TAZ3-YAMADA/fomo-desk/settings/pages
2. Build and deployment → Source: **Deploy from a branch**
3. Branch: `main`, folder: `/ (root)`, then Save

`.nojekyll` is in the root so Pages serves `d/` as files instead of running Jekyll. Turning Pages on needs `pages: write` or repository administration; a contents-only token cannot do it.

## Data

Live JSON is not in git. It is published at:

`/d/{DATA_PATH}/state.json`
`/d/{DATA_PATH}/chart.json`
`/d/{DATA_PATH}/activity.json`

`DATA_PATH` is a secret. The folder is not listed. Do not commit the path, API keys, or tokens.

Open the site once with the URL fragment `#d=` set to that path. The page stores it in this browser's `localStorage` and removes it from the address bar. The app then polls those three relative URLs every 15 seconds. A failed fetch shows an offline or error banner and does not write the path to the console.

`state.json`: `equity`, `cash`, `dayPnl`, `dayPnlPct`, `positions` (`symbol`, `qty`, `price`, `value`, `pnl`), `agents` (`name`, `status`, `pnl`, `detail`).

`chart.json`: `points` as `{ "t", "v" }` pairs (two or more).

`activity.json`: `items` as `{ "time", "title", "detail", "amount" }`.

## Architect — wallet whitelist (paper only)

Wallet watching is a SQLite registry beside the Pages book. This repo has no mint watchlist and no coins table; `state.json` positions stay symbol display data. `desk/db.py` creates `labeled_wallets` (read view `whales`), `whitelist`, and `whale_signals`.

The watch key is `wallet_label` together with the public Solana address. `provenance` is required and records how the owner provided that address. Dossier import stores that address with `provenance` set to `dossier_import`. When the file includes a handle, the string is copied into `display_note` only. A dossier with a handle and no `wallet_label` is refused, so a display name is never a watch key.

`end837` is a negative control. Import stores it as whitelist `status=blocked` and `tier=blocked`. `add_whitelist` refuses that label and any wallet whose status is already `blocked`. `whale_signals.source` accepts `rpc` or `replay` only. This slice is schema, import, and tests: paper/sim only, with no trading, signing, or ingest.

Run `python -m unittest discover -s tests`.
