"""Car listing views + search endpoints.

The front-end is mostly static right now (pure HTML/CSS). This module focuses on
providing the data you need:

- /autoliste (HTML) with server-side filtering and sorting via query params
- /api/listings (JSON) for debugging / later integration
"""

from __future__ import annotations

from typing import Any

from flask import Blueprint, abort, g, jsonify, redirect, render_template, request, url_for

import db
from auth import login_required


cars_bp = Blueprint("cars", __name__)


@cars_bp.before_request
def require_login_for_cars() -> Any:
    if g.get("user") is None:
        return redirect(url_for("auth.login", next=request.path))
    return None


def _parse_int(value: str | None) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError:
        return None


def search_listings(filters: dict[str, Any]) -> list[dict[str, Any]]:
    """Search listings with simple filters.

    NOTE: We whitelist sort keys to keep it safe.
    """

    brand = filters.get("brand")
    model = filters.get("model")
    q = filters.get("q")
    year_min = filters.get("year_min")
    year_max = filters.get("year_max")
    km_min = filters.get("km_min")
    km_max = filters.get("km_max")
    score_min = filters.get("score_min")
    sort = filters.get("sort") or "price_asc"
    saved_ids = filters.get("saved_ids")

    sql = (
        "SELECT id, source, url, title, brand, model, variant, year, mileage_km, "
        "price_eur, fuel_type, transmission, color, accident, condition, score, "
        "score_version, score_computed_at, score_level, score_group_size, score_price_percentile, last_seen_at "
        "FROM listings WHERE 1=1"
    )
    params: list[Any] = []

    if brand:
        sql += " AND brand = ?"
        params.append(brand)
    if q:
        # simple text search across common text columns
        sql += " AND (brand LIKE ? OR model LIKE ? OR title LIKE ? OR variant LIKE ? )"
        like = f"%{q}%"
        params.extend([like, like, like, like])
    if model:
        sql += " AND model = ?"
        params.append(model)
    if year_min is not None:
        sql += " AND year >= ?"
        params.append(year_min)
    if year_max is not None:
        sql += " AND year <= ?"
        params.append(year_max)
    if km_min is not None:
        sql += " AND mileage_km >= ?"
        params.append(km_min)
    if km_max is not None:
        sql += " AND mileage_km <= ?"
        params.append(km_max)
    if score_min is not None:
        sql += " AND score >= ?"
        params.append(score_min)
    if saved_ids is not None:
        if not saved_ids:
            return []
        placeholders = ",".join(["?"] * len(saved_ids))
        sql += f" AND id IN ({placeholders})"
        params.extend(saved_ids)

    sort_map = {
        "score_desc": "score DESC NULLS LAST, price_eur ASC",
        "score_asc": "score ASC NULLS LAST, price_eur ASC",
        "price_asc": "price_eur ASC NULLS LAST, score DESC",
        "price_desc": "price_eur DESC NULLS LAST, score DESC",
        "km_asc": "mileage_km ASC NULLS LAST, score DESC",
        "km_desc": "mileage_km DESC NULLS LAST, score DESC",
        "year_desc": "year DESC NULLS LAST, score DESC",
        "year_asc": "year ASC NULLS LAST, score DESC",
        "seen_desc": "last_seen_at DESC",
    }
    sql += " ORDER BY " + sort_map.get(sort, sort_map["score_desc"])

    limit = filters.get("limit") or 50
    offset = filters.get("offset") or 0
    sql += " LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = db.query_all(sql, tuple(params))
    return [dict(r) for r in rows]


@cars_bp.route("/autoliste")
@login_required
def autoliste():
    user_id = g.user["id"] if g.get("user") else None
    saved_ids: list[int] = []
    if user_id is not None:
        saved_rows = db.query_all(
            "SELECT listing_id FROM saved_cars WHERE user_id = ?",
            (user_id,),
        )
        saved_ids = [int(r["listing_id"]) for r in saved_rows]

    saved_only = request.args.get("saved") is not None
    if saved_only and user_id is None:
        return redirect(url_for("auth.login", next=request.path))

    filters = {
        "brand": (request.args.get("brand") or "").strip() or None,
        "q": (request.args.get("q") or "").strip() or None,
        "model": (request.args.get("model") or "").strip() or None,
        "year_min": _parse_int(request.args.get("year_min")),
        "year_max": _parse_int(request.args.get("year_max")),
        "km_min": _parse_int(request.args.get("km_min")),
        "km_max": _parse_int(request.args.get("km_max")),
        "score_min": _parse_int(request.args.get("score_min")),
        "sort": (request.args.get("sort") or "").strip() or None,
        "limit": _parse_int(request.args.get("limit")) or 50,
        "offset": _parse_int(request.args.get("offset")) or 0,
    }
    if saved_only:
        filters["saved_ids"] = saved_ids

    listings = search_listings(filters)
    # If no results from search, show a few random listings from DB as fallback
    if not listings and not saved_only:
        # Prefer random listings that came from the 'koenig' scraper and are active
        rows = db.query_all(
            "SELECT id, source, url, title, brand, model, variant, year, mileage_km, "
            "price_eur, fuel_type, transmission, color, accident, condition, score "
            "FROM listings WHERE source = ? AND is_active = 1 ORDER BY RANDOM() LIMIT 12",
            ("koenig",),
        )
        listings = [dict(r) for r in rows]

        # If not enough koenig listings, fill with other active listings (avoid duplicates)
        if len(listings) < 12:
            remaining = 12 - len(listings)
            rows = db.query_all(
                "SELECT id, source, url, title, brand, model, variant, year, mileage_km, "
                "price_eur, fuel_type, transmission, color, accident, condition, score "
                "FROM listings WHERE is_active = 1 AND source != ? ORDER BY RANDOM() LIMIT ?",
                ("koenig", remaining),
            )
            listings.extend([dict(r) for r in rows])

    # Debug-friendly: /autoliste?json=1 returns JSON
    if request.args.get("json") is not None:
        return jsonify(listings)

    # The current Autoliste.html is a static mock. We still pass the data,
    # so your frontend partner can plug it in with Jinja loops.
    from datetime import datetime
    current_year = datetime.now().year
    return render_template(
        "Autoliste.html",
        listings=listings,
        filters=filters,
        current_year=current_year,
        saved_ids=saved_ids,
    )


@cars_bp.post("/autoliste/save/<int:listing_id>")
@login_required
def save_car(listing_id: int):
    user_id = g.user["id"]
    exists = db.query_one("SELECT 1 FROM listings WHERE id = ?", (listing_id,))
    if not exists:
        abort(404)

    saved = db.query_one(
        "SELECT 1 FROM saved_cars WHERE user_id = ? AND listing_id = ?",
        (user_id, listing_id),
    )
    if saved:
        db.execute(
            "DELETE FROM saved_cars WHERE user_id = ? AND listing_id = ?",
            (user_id, listing_id),
        )
    else:
        db.execute(
            "INSERT OR IGNORE INTO saved_cars (user_id, listing_id) VALUES (?, ?)",
            (user_id, listing_id),
        )

    return redirect(request.referrer or url_for("cars.autoliste"))


@cars_bp.route("/api/listings")
def api_listings():
    # Same filters as /autoliste, always JSON.
    filters = {
        "brand": (request.args.get("brand") or "").strip() or None,
        "model": (request.args.get("model") or "").strip() or None,
        "year_min": _parse_int(request.args.get("year_min")),
        "year_max": _parse_int(request.args.get("year_max")),
        "km_min": _parse_int(request.args.get("km_min")),
        "km_max": _parse_int(request.args.get("km_max")),
        "score_min": _parse_int(request.args.get("score_min")),
        "sort": (request.args.get("sort") or "").strip() or None,
        "limit": _parse_int(request.args.get("limit")) or 50,
        "offset": _parse_int(request.args.get("offset")) or 0,
    }
    return jsonify(search_listings(filters))


@cars_bp.route("/api/listings/<int:listing_id>")
def api_listing_detail(listing_id: int):
    row = db.query_one("SELECT * FROM listings WHERE id = ?", (listing_id,))
    if not row:
        return jsonify({"error": "not found"}), 404
    data = dict(row)
    data["price_history"] = [
        dict(r)
        for r in db.query_all(
            "SELECT recorded_at, price_eur, mileage_km FROM listing_price_history "
            "WHERE listing_id = ? ORDER BY recorded_at DESC LIMIT 50",
            (listing_id,),
        )
    ]
    data["score_history"] = [
        dict(r)
        for r in db.query_all(
            "SELECT computed_at, score, score_version, details_json FROM listing_score_history "
            "WHERE listing_id = ? ORDER BY computed_at DESC LIMIT 50",
            (listing_id,),
        )
    ]
    return jsonify(data)
