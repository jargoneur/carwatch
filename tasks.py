"""CLI commands for scraping, scoring and dev data.

Why CLI?
- easiest way to run data jobs without JavaScript or a separate worker
- you can schedule them later (cron/systemd/GitHub actions)

Example:
  flask --app app init-db
  flask --app app seed-dev
  flask --app app score

Scrape demo (reads a JSON file):
  flask --app app scrape --source demo-json --input-file sample_data/demo_listings.json
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import click
from flask import Flask

import db
from scoring import score_all_listings
from upsert import upsert_listing


def register_cli(app: Flask) -> None:
    """Register custom CLI commands for scraping, scoring, and dev seeding."""

    @app.cli.command("seed-dev")
    def seed_dev_cmd() -> None:
        """Insert a small deterministic set of demo listings."""
        demo_listings = [
            {
                "source": "demo",
                "external_id": "DEMO-1001",
                "url": "https://example.com/listing/1001",
                "title": "BMW 320d Touring",
                "brand": "BMW",
                "model": "3er",
                "variant": "320d Touring",
                "year": 2018,
                "mileage_km": 89000,
                "price_eur": 21900,
                "fuel_type": "diesel",
                "transmission": "automatik",
                "color": "grau",
                "accident": 0,
                "condition": "gut",
            },
            {
                "source": "demo",
                "external_id": "DEMO-1002",
                "url": "https://example.com/listing/1002",
                "title": "Audi A4 Avant 2.0 TDI",
                "brand": "Audi",
                "model": "A4",
                "variant": "Avant 2.0 TDI",
                "year": 2016,
                "mileage_km": 145000,
                "price_eur": 14900,
                "fuel_type": "diesel",
                "transmission": "schalter",
                "color": "schwarz",
                "accident": 0,
                "condition": "ok",
            },
            {
                "source": "demo",
                "external_id": "DEMO-1003",
                "url": "https://example.com/listing/1003",
                "title": "Tesla Model 3 Long Range",
                "brand": "Tesla",
                "model": "Model 3",
                "variant": "Long Range",
                "year": 2022,
                "mileage_km": 24900,
                "price_eur": 37900,
                "fuel_type": "elektrisch",
                "transmission": "automatik",
                "color": "silber",
                "accident": 0,
                "condition": "sehr_gut",
            },
            {
                "source": "demo",
                "external_id": "DEMO-1004",
                "url": "https://example.com/listing/1004",
                "title": "VW Golf 7 1.4 TSI",
                "brand": "Volkswagen",
                "model": "Golf",
                "variant": "7 1.4 TSI",
                "year": 2017,
                "mileage_km": 120000,
                "price_eur": 12900,
                "fuel_type": "benzin",
                "transmission": "schalter",
                "color": "blau",
                "accident": 1,
                "condition": "ok",
            },
        ]

        con = db.get_db_con()
        inserted = 0
        updated = 0
        for item in demo_listings:
            action = upsert_listing(con, item)
            inserted += 1 if action == "inserted" else 0
            updated += 1 if action == "updated" else 0
        click.echo(f"seed-dev: inserted={inserted} updated={updated}")

    @app.cli.command("scrape")
    @click.option("--source",
        default="demo-json",
        show_default=True,
        help="Scraper type."
        )
    @click.option(
        "--headless/--no-headless",
        default=True,
        show_default=True,
        help="Run browser headless (used by selenium sources).",
    )
    @click.option(
        "--user-data-dir",
        default=None,
        show_default=False,
        help="Optional Chrome user-data-dir profile path (selenium sources).",
    )
    @click.option(
        "--input-file",
        type=click.Path(dir_okay=False, path_type=Path),
        required=False,
        help="Used by demo-json scraper: JSON file with a list of listings.",
    )
    @click.option(
        "--limit",
        default=None,
        type=int,
        help="Optional limit for number of listings to scrape (for testing).",
    )
    def scrape_cmd(source: str, headless: bool, user_data_dir: str, limit:int | None, input_file: Path | None) -> None:
        """Run a scraping job.

        Supported sources:
        - demo-json: reads listings from a JSON file (used for testing)
        - koenig: scrapes https://www.autohaus-koenig.de/ (requires ChromeDriver and Selenium)
        """

        con = db.get_db_con()

        inserted = 0
        updated = 0

        if source == "demo-json":
            if input_file is None:
                raise click.ClickException("--input-file is required for source=demo-json")
            if not input_file.exists():
                raise click.ClickException(f"input file not found: {input_file}")

            items: list[dict[str, Any]] = json.loads(input_file.read_text(encoding="utf-8"))
            if not isinstance(items, list):
                raise click.ClickException("JSON must be a list of listing objects")

            for item in items:
                if not isinstance(item, dict):
                    continue
                action = upsert_listing(con, item)
                inserted += 1 if action == "inserted" else 0
                updated += 1 if action == "updated" else 0
            click.echo(f"scrape: inserted={inserted} updated={updated} from {input_file}")
            return

        if source == "koenig":
            from scrapers.koenig import iter_koenig_listings

            failed = 0
            for item in iter_koenig_listings( headless=headless, user_data_dir=user_data_dir, limit=limit):
                try:
                    action = upsert_listing(con, item)
                    inserted += 1 if action == "inserted" else 0
                    updated += 1 if action == "updated" else 0
                except Exception as e:
                    failed += 1
                    url = item.get("url") if isinstance(item, dict) else None
                    click.echo(f"koenig: failed url={url} err={e}")

            click.echo(
                f"scrape(koenig): inserted={inserted} updated={updated} failed={failed} headless={headless}"
            )
            return

        raise click.ClickException(
            "Unknown source. Supported: demo-json, koenig"
        )

    @app.cli.command("score")
    @click.option("--version", default="percentile_v1", show_default=True)
    @click.option(
        "--min-n",
        default=25,
        show_default=True,
        type=int,
        help="Min cohort size (percentile ranking) before falling back to broader cohorts.",
    )
    def score_cmd(version: str, min_n: int) -> None:
        """Compute scores for all listings."""
        con = db.get_db_con()
        n = score_all_listings(con, score_version=version, min_group_size=min_n)
        click.echo(f"score: updated scores for {n} listings")
