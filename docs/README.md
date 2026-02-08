```md
# Carwatch

Internal tool that scrapes used‑car listings from online marketplaces, stores them in SQLite, scores deals relative to the market, and displays results in a Flask web app.

## Audience
This Project is for the project’s single contractor. It focuses on how to run, scrape, score, and troubleshoot.

## Features
- Scrape listings 
- Normalize and upsert listings with price history
- Percentile‑based deal scoring relative to current market data
- Web UI for browsing and filtering listings
- Simple login and saved‑cars functionality

## Tech Stack
- Python, Flask
- SQLite (local DB)
- pandas + numpy (scoring)
- Selenium + Chrome (scraper)

## Project Layout
- `app.py` Flask app factory and entrypoint
- `tasks.py` CLI commands for scraping, scoring, seed data
- `scrapers/koenig.py` Selenium scraper for autohaus‑koenig.de
- `scoring.py` percentile‑based scoring logic
- `upsert.py` normalize + insert/update logic
- `sql/create_tables.sql` schema
- `templates/` HTML templates 

## Setup
```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

Initialize DB:
```bash
flask --app app init-db
```

Create a login user:
```bash
flask --app app create-user
```

Run the app:
```bash
python app.py
# or
flask --app app run
```

## Scraping
Demo JSON (local file):
```bash
flask --app app scrape --source demo-json --input-file sample_data/demo_listings.json
```

Autohaus Koenig (Selenium + Chrome required):
```bash
flask --app app scrape --source koenig --headless
```

Optional flags:
- `--user-data-dir "chrome profile"` to reuse the profile in `chrome profile`
- `--limit 50` to cap the number of listings

## Scoring
Computes a percentile‑based deal score within brand+model+year cohorts, using mileage bins and condition. Falls back to broader bins if cohorts are small, and applies weighted overlays for fuel type, transmission, color, variant, and accident history.

Run scoring:
```bash
flask --app app score
```

## Web Routes
- `/login`, `/logout`
- `/autoliste` main listing page
- `/api/listings` JSON listing search
- `/api/listings/<id>` JSON listing + price/score history
- `/profil` user profile (static UI)

## Database Schema
Key tables:
- `users`
- `listings`
- `listing_price_history`
- `listing_score_history`
- `model_year_stats`
- `saved_cars`

See Pages for the full schema.

## Troubleshooting
- “no such table” errors: run `flask --app app init-db`
- Login fails: create a user via `flask --app app create-user`

## Security Note
Auth is intentionally minimal.

## License
Private / internal use only (update if needed).

