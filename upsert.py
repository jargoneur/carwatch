"""Upsert helper for listings.

The scraping layer should output a normalized dict with keys like:

  source, external_id, url, title, brand, model, variant, year,
  mileage_km, price_eur, fuel_type, transmission, color,
  accident, condition, raw_json

Only a subset is required, but (source, url, brand, model) should always be present.
"""

from __future__ import annotations

import json
from typing import Any, Literal

import sqlite3


UpsertResult = Literal["inserted", "updated"]


def _to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, float):
        return int(v)
    if isinstance(v, str):
        s = v.strip().replace(".", "").replace(",", "")
        if s == "":
            return None
        try:
            return int(s)
        except ValueError:
            return None
    return None


def _to_text(v: Any) -> str | None:
    if v is None:
        return None
    s = str(v).strip()
    return s or None


def upsert_listing(con: sqlite3.Connection, listing: dict[str, Any]) -> UpsertResult:
    """Insert or update a listing by URL.

    - URL is treated as stable unique key.
    - Writes to listing_price_history when price or mileage changes.
    """

    source = _to_text(listing.get("source")) or "unknown"
    url = _to_text(listing.get("url"))
    brand = _to_text(listing.get("brand"))
    model = _to_text(listing.get("model"))

    if not url:
        raise ValueError("listing.url fehlt")
    if not brand or not model:
        raise ValueError("listing.brand und listing.model müssen gesetzt sein")

    external_id = _to_text(listing.get("external_id"))
    title = _to_text(listing.get("title"))
    variant = _to_text(listing.get("variant"))
    year = _to_int(listing.get("year"))
    mileage_km = _to_int(listing.get("mileage_km"))
    price_eur = _to_int(listing.get("price_eur"))
    fuel_type = _to_text(listing.get("fuel_type"))
    transmission = _to_text(listing.get("transmission"))
    color = _to_text(listing.get("color"))
    accident = _to_int(listing.get("accident"))
    condition = _to_text(listing.get("condition"))

    raw_json = listing.get("raw_json")
    if raw_json is None:
        # store full original dict as default raw payload
        raw_json = listing
    raw_json_text = json.dumps(raw_json, ensure_ascii=False)

    cur = con.execute(
        "SELECT id, price_eur, mileage_km FROM listings WHERE url = ?",
        (url,),
    )
    row = cur.fetchone()

    if row is None:
        cur = con.execute(
            """
            INSERT INTO listings (
                source, external_id, url, title,
                brand, model, variant,
                year, mileage_km, price_eur,
                fuel_type, transmission, color,
                accident, condition,
                raw_json,
                first_seen_at, last_seen_at, updated_at, is_active
            ) VALUES (
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?,
                ?, ?,
                ?,
                CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1
            )
            """,
            (
                source,
                external_id,
                url,
                title,
                brand,
                model,
                variant,
                year,
                mileage_km,
                price_eur,
                fuel_type,
                transmission,
                color,
                accident,
                condition,
                raw_json_text,
            ),
        )
        listing_id = cur.lastrowid
        con.execute(
            "INSERT INTO listing_price_history (listing_id, price_eur, mileage_km) VALUES (?, ?, ?)",
            (listing_id, price_eur, mileage_km),
        )
        con.commit()
        return "inserted"

    listing_id = row["id"]
    old_price = row["price_eur"]
    old_km = row["mileage_km"]

    # record history if changed
    if (price_eur is not None and price_eur != old_price) or (mileage_km is not None and mileage_km != old_km):
        con.execute(
            "INSERT INTO listing_price_history (listing_id, price_eur, mileage_km) VALUES (?, ?, ?)",
            (listing_id, price_eur, mileage_km),
        )

    con.execute(
        """
        UPDATE listings SET
            source = ?,
            external_id = ?,
            title = ?,
            brand = ?,
            model = ?,
            variant = ?,
            year = ?,
            mileage_km = ?,
            price_eur = ?,
            fuel_type = ?,
            transmission = ?,
            color = ?,
            accident = ?,
            condition = ?,
            raw_json = ?,
            last_seen_at = CURRENT_TIMESTAMP,
            updated_at = CURRENT_TIMESTAMP,
            is_active = 1
        WHERE id = ?
        """,
        (
            source,
            external_id,
            title,
            brand,
            model,
            variant,
            year,
            mileage_km,
            price_eur,
            fuel_type,
            transmission,
            color,
            accident,
            condition,
            raw_json_text,
            listing_id,
        ),
    )
    con.commit()
    return "updated"
