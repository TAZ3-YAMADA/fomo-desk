# Desk

Static trading desk. GitHub Pages serves this repository from the `main` branch, folder `/` (root).

https://taz3-yamada.github.io/fomo-desk/

Settings → Pages → Deploy from a branch → `main` → `/ (root)`. `.nojekyll` is here so Pages serves `d/` as files, not a Jekyll site.

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
