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
