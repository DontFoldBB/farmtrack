# FarmTrack

A local desktop app for tracking crypto airdrop farming — protocols, wallets, balances, P&L, and positions. Built with Python + Flask + pywebview. No cloud, no accounts, everything stays on your machine.

![Version](https://img.shields.io/badge/version-alpha%20v0.2-blue)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Platform](https://img.shields.io/badge/platform-Windows%20%7C%20macOS-lightgrey)

---

## Features

- **Profiles** — separate databases for different wallets/accounts, switch between them instantly
- **Protocols** — track every project you're farming: deposit, balance, spent, withdrawn, points, status
- **Wallets** — manage addresses across protocols, add labels, bulk import
- **Import** — paste wallet data from spreadsheets into any protocol; automatically creates wallets if they don't exist yet
- **Export** — export all data to Excel in one click
- **Reminders** — set deadlines per protocol, get notified when they're due
- **Perp Calculator** — track manual perpetual positions and pull live data from Hyperliquid
- **P&L overview** — see total balance, spent, and net profit across all protocols at a glance
- **EN / RU** — language toggle, preference saved locally

---

## Stack

| Layer | Tech |
|---|---|
| Backend | Python 3.10+, Flask |
| Frontend | Vanilla JS + HTML/CSS (Apple-style dark UI) |
| Desktop | pywebview (native window, no browser needed) |
| Database | SQLite (one `.db` file per profile) |
| Export | openpyxl |

---

## Getting Started

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

Data is stored in `data/<profile-name>.db` (created automatically, not tracked by git).

---

## Requirements

- Python 3.10+
- Windows or macOS (pywebview requirement)
- Dependencies from `requirements.txt`:
  - flask
  - pywebview
  - openpyxl
  - requests

---

## Notes

- All data is local — nothing is sent anywhere except live Hyperliquid price fetches (public API, no auth)
- Wallet addresses are never shared or logged
- The `data/` folder is in `.gitignore` — your databases won't be accidentally committed if you fork this
