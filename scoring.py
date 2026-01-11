"""Scoring logic for CarWatch.

Requirement (from your project spec):
    The score should be *relative to other offers* in your database, i.e.
    driven by statistics from the scraped market data (not hardcoded prices).

This module implements a **percentile-based "deal" score**:

    - We define "comparable cohorts" (e.g. same brand+model+year and similar
      mileage bucket).
    - Inside each cohort we rank listings by price.
    - Cheapest within its cohort -> score near 100
      Most expensive within its cohort -> score near 0

Because some cohorts can be too small, we use **hierarchical fallbacks** that
gradually broaden the cohort (year bins, wider mileage bins, brand-only, global).

Why this matches "relative scoring":
    The score is computed from empirical distributions of your own data.
    If the market shifts, the score shifts automatically.

You can extend the cohort keys later (fuel_type, transmission, region, etc.).
"""

from __future__ import annotations

from datetime import date
import json
from typing import Any

import numpy as np
import pandas as pd
import sqlite3


def _ensure_series(value: int, index: pd.Index) -> pd.Series:
    return pd.Series([value] * len(index), index=index)


def _rank_to_percentile(rank: pd.Series, group_size: pd.Series) -> pd.Series:
    """Convert 1..n ranks to a 0..1 percentile (0=cheapest, 1=most expensive)."""
    # For n == 1, define percentile 0.5 (neutral) to avoid division by zero.
    denom = (group_size - 1).replace({0: np.nan})
    pct = (rank - 1) / denom
    return pct.fillna(0.5)


def _compute_percentile_score(
    df: pd.DataFrame,
    *,
    keys: list[str],
    level_name: str,
    min_group_size: int,
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """Return (score, group_size, price_percentile) for a given cohort definition."""
    if not keys:
        # Global ranking
        group_size = _ensure_series(len(df), df.index)
        rank = df["price_eur"].rank(method="average", ascending=True)
    else:
        group_size = df.groupby(keys, sort=False)["id"].transform("size")
        rank = df.groupby(keys, sort=False)["price_eur"].rank(method="average", ascending=True)

    pct = _rank_to_percentile(rank, group_size)
    score = (1.0 - pct) * 100.0

    # If a cohort is too small, we do NOT trust its ranking.
    # We will fill those rows using broader cohorts later.
    score = score.where(group_size >= min_group_size)
    pct = pct.where(group_size >= min_group_size)

    # Attach useful debugging info
    score.attrs["level_name"] = level_name
    return score, group_size, pct


def score_all_listings(
    con: sqlite3.Connection,
    *,
    score_version: str = "percentile_v1",
    min_group_size: int = 25,
    km_bin_small: int = 10_000,
    km_bin_large: int = 25_000,
    year_bin_size: int = 2,
) -> int:
    """Compute + persist scores for all listings.

    Parameters
    - min_group_size: minimum cohort size to trust a percentile ranking.
    - km_bin_small/km_bin_large: mileage bucket widths.
    - year_bin_size: year bucket size for fallback (e.g. 2 => 2016-2017).
    """

    df = pd.read_sql_query(
        """
        SELECT
            id, brand, model, year, mileage_km, price_eur,
            COALESCE(accident, 0) AS accident
        FROM listings
        WHERE price_eur IS NOT NULL
          AND year IS NOT NULL
          AND mileage_km IS NOT NULL
          AND brand IS NOT NULL
          AND model IS NOT NULL
          AND is_active = 1
        """,
        con,
    )

    if df.empty:
        return 0

    df = df.copy()
    df["brand"] = df["brand"].astype(str).str.strip()
    df["model"] = df["model"].astype(str).str.strip()
    df["year"] = df["year"].astype(int)
    df["mileage_km"] = df["mileage_km"].astype(int)
    df["price_eur"] = df["price_eur"].astype(float)

    # Buckets for comparable cohorts
    df["km_bin_small"] = (df["mileage_km"] // km_bin_small) * km_bin_small
    df["km_bin_large"] = (df["mileage_km"] // km_bin_large) * km_bin_large
    df["year_bin"] = (df["year"] // year_bin_size) * year_bin_size

    # Output columns
    df["score"] = np.nan
    df["score_level"] = None
    df["score_group_size"] = np.nan
    df["score_price_percentile"] = np.nan

    # Hierarchical cohorts: narrow -> broad
    # (You can extend keys later: fuel_type, transmission, etc.)
    levels: list[tuple[str, list[str], int]] = [
        ("brand_model_year_km10k", ["brand", "model", "year", "km_bin_small"], min_group_size),
        ("brand_model_year_km25k", ["brand", "model", "year", "km_bin_large"], min_group_size),
        ("brand_model_yearbin_km25k", ["brand", "model", "year_bin", "km_bin_large"], min_group_size),
        ("brand_model_yearbin", ["brand", "model", "year_bin"], min_group_size),
        ("brand_model", ["brand", "model"], min_group_size),
        ("brand", ["brand"], min_group_size),
        ("global", [], 1),
    ]

    for level_name, keys, level_min_n in levels:
        remaining = df["score"].isna()
        if not remaining.any():
            break

        score_s, group_size_s, pct_s = _compute_percentile_score(
            df,
            keys=keys,
            level_name=level_name,
            min_group_size=level_min_n,
        )

        fill_mask = remaining & score_s.notna()
        if not fill_mask.any():
            continue

        df.loc[fill_mask, "score"] = score_s.loc[fill_mask].round(1)
        df.loc[fill_mask, "score_level"] = level_name
        df.loc[fill_mask, "score_group_size"] = group_size_s.loc[fill_mask].astype(int)
        df.loc[fill_mask, "score_price_percentile"] = pct_s.loc[fill_mask].round(4)

    # Safety clamp
    df["score"] = df["score"].clip(lower=0.0, upper=100.0)

    # --- persist ---
    cur = con.cursor()

    cur.executemany(
        """
        UPDATE listings
        SET
            score = ?,
            score_version = ?,
            score_computed_at = CURRENT_TIMESTAMP,
            score_level = ?,
            score_group_size = ?,
            score_price_percentile = ?
        WHERE id = ?
        """,
        [
            (
                float(r.score),
                score_version,
                str(r.score_level) if r.score_level is not None else None,
                int(r.score_group_size) if r.score_group_size == r.score_group_size else None,
                float(r.score_price_percentile)
                if r.score_price_percentile == r.score_price_percentile
                else None,
                int(r.id),
            )
            for r in df.itertuples(index=False)
        ],
    )

    # Append score history (with details for audit/debug)
    cur.executemany(
        """
        INSERT INTO listing_score_history (listing_id, score, score_version, details_json)
        VALUES (?, ?, ?, ?)
        """,
        [
            (
                int(r.id),
                float(r.score),
                score_version,
                json.dumps(
                    {
                        "level": r.score_level,
                        "group_size": int(r.score_group_size)
                        if r.score_group_size == r.score_group_size
                        else None,
                        "price_percentile": float(r.score_price_percentile)
                        if r.score_price_percentile == r.score_price_percentile
                        else None,
                    },
                    ensure_ascii=False,
                ),
            )
            for r in df.itertuples(index=False)
        ],
    )

    # Daily aggregates for trend/statistics (same as before)
    snapshot_date = date.today().isoformat()
    agg = (
        df.groupby(["brand", "model", "year"], dropna=False)
        .agg(
            n=("id", "count"),
            avg_price=("price_eur", "mean"),
            median_price=("price_eur", "median"),
            avg_mileage=("mileage_km", "mean"),
            median_mileage=("mileage_km", "median"),
        )
        .reset_index()
    )

    cur.executemany(
        """
        INSERT INTO model_year_stats (
            snapshot_date, brand, model, year,
            n, avg_price, median_price, avg_mileage, median_mileage
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date, brand, model, year)
        DO UPDATE SET
            n=excluded.n,
            avg_price=excluded.avg_price,
            median_price=excluded.median_price,
            avg_mileage=excluded.avg_mileage,
            median_mileage=excluded.median_mileage,
            updated_at=CURRENT_TIMESTAMP
        """,
        [
            (
                snapshot_date,
                str(r.brand),
                str(r.model),
                int(r.year),
                int(r.n),
                float(r.avg_price) if r.avg_price == r.avg_price else None,
                float(r.median_price) if r.median_price == r.median_price else None,
                float(r.avg_mileage) if r.avg_mileage == r.avg_mileage else None,
                float(r.median_mileage) if r.median_mileage == r.median_mileage else None,
            )
            for r in agg.itertuples(index=False)
        ],
    )

    con.commit()
    return len(df)
