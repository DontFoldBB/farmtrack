# FarmTrack

A local desktop app for tracking crypto airdrop farming — protocols, wallets, balances, P&L, and perp positions. Built with Python + Flask + pywebview. No cloud, no accounts, everything stays on your machine.

![Version](https://img.shields.io/badge/version-alpha%20v0.9-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)

---

## Features

- **Profiles** — separate databases for different sets of wallets, switch between them instantly
- **Protocols** — track every project: deposit, balance, spent, withdrawn, points, $/point, status
- **Weekly snapshots** — break protocol data into weeks, track progress over time
- **Wallets** — manage addresses across protocols, add labels, bulk import from spreadsheets
- **Import** — paste wallet data from Google Sheets into any protocol or weekly snapshot
- **Export** — export all data to Excel in one click
- **Reminders** — set deadlines per protocol, see what's due
- **Perp** — live positions from HyperLiquid, Nado, Extended, Pacifica; grouped by account with P&L, Margin Ratio and Account Leverage badges per account
- **Overview** — total balance, spent, net profit, $/point across all protocols at a glance
- **Light/dark theme** — toggle in the sidebar, persists between sessions

---

## Download

Pre-built binaries are available in [Actions → latest build → Artifacts](../../actions):

- **FarmTrack-Windows** — unzip, run `FarmTrack.exe`
- **FarmTrack-Mac** — unzip, run `FarmTrack.app` (right-click → Open on first launch)

No Python required.

---

## Run from source

### 1. Clone

```bash
git clone https://github.com/DontFoldBB/farmtrack.git
cd farmtrack
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Run

```bash
python main.py
```

The app opens as a native desktop window. On first launch, create a profile to get started.

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.10+, Flask |
| Frontend | Vanilla JS + HTML/CSS (OpenCode design system, light + dark) |
| Desktop | pywebview (native window, no browser needed) |
| Database | SQLite (one `.db` file per profile) |
| Export | openpyxl |

---

## Project Structure

```
farmtrack/
├── main.py           # Entry point — starts Flask + opens webview window
├── app.py            # Flask routes / REST API
├── database.py       # SQLite logic, all DB operations
├── requirements.txt  # Python dependencies
└── templates/
    ├── index.html    # Main app UI (single-page)
    └── profiles.html # Profile selection screen
```

Data is stored in `data/<profile-name>.db` — created automatically, not tracked by git.

---

## Notes

- All data is local — nothing is sent anywhere except live price fetches from exchange public APIs (no auth)
- Wallet addresses are never shared or logged
- The `data/` folder is in `.gitignore` — your databases won't be accidentally committed if you fork this
