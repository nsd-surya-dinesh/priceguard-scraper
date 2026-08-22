# PriceGuard — Self-Healing Price Tracking Pipeline

Built for the WeMakeDevs × Bright Data "Scrape-Verse" Hackathon.

## What it does

PriceGuard tracks live laptop prices and stock availability from an e-commerce
listing page. It's built around Bright Data's Scraper Studio, and the core
idea is **self-healing**: when the target site changes and the scraper starts
returning broken or incomplete data, the pipeline can be repaired with a
single natural-language prompt — no manual selector-hunting required.

## How it works

1. **`bdata scraper create`** generates the scraper from a URL and a plain-English
   description of the data needed (product name, price, discount, stock).
2. **`pipeline.py`** triggers the scraper, parses the returned JSON, cleans it
   up (fixes encoding issues, normalizes garbled discount text, fills in
   missing product names from the URL as a fallback), and stores everything
   in a local SQLite database (`prices.db`). Every run — success or failure —
   is logged to a `scraper_health` table.
3. **`generate_dashboard.py`** reads `prices.db` and generates a static,
   self-contained `dashboard.html` — a dark, systems-monitoring-style
   dashboard showing price history charts, a current snapshot table, and a
   live scraper health log. No server required.
4. **Self-healing loop:** when the scraper output degrades (e.g. a field goes
   missing or gets garbled after a site change), running
   `bdata scraper heal <COLLECTOR_ID> "<what's wrong>"` generates a fix,
   which is reviewed and applied with `bdata scraper approve <COLLECTOR_ID>`.
   The downstream pipeline code needs zero changes — it just starts receiving
   clean data again.

## Setup

```bash
npx -p @brightdata/cli
bdata login
```

## Run

```bash
python pipeline.py            # scrape + store latest prices
python generate_dashboard.py  # regenerate dashboard.html
```

Open `dashboard.html` in a browser to view.

## Self-healing in action

During development, the scraper's `discount_percentage` field came back
garbled (word order scrambled, e.g. `"off)23.53%, 20,000(Save ₹"` instead of
`"Save ₹20,000 (23.53% off)"`). This was fixed live using:

```bash
bdata scraper heal c_msymhd5y23d7ustw2z "the discount_percentage field is garbled and out of order, it should read like 'Save ₹20,000 (23.53% off)'"
bdata scraper approve c_msymhd5y23d7ustw2z
```

See the demo video for the full before → heal → after sequence.

## Tech stack

- **Bright Data Scraper Studio** — AI-generated, self-healing scraper
- **Python** — pipeline orchestration, data cleaning
- **SQLite** — local storage for price history and scraper health logs
- **HTML/CSS/JS + Chart.js** — static dashboard, no backend required

## Why this matters

Scraper maintenance is usually the hidden cost of any data pipeline —
websites redesign, and selectors silently break. PriceGuard treats that as a
solvable problem from day one: instead of manually re-inspecting broken HTML,
you describe what changed in plain English and the scraper repairs itself.
