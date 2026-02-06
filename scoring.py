"""Scoring logic for CarWatch.

Requirement (from your project spec):
    The score should be *relative to other offers* in your database, i.e.
    driven by statistics from the scraped market data (not hardcoded prices).

This module implements a **percentile-based "deal" score**:

    - We define "comparable cohorts" by brand+model+year, plus mileage bins
      and a numeric condition score.
    - Inside each cohort we rank listings by price.
    - Cheapest within its cohort -> score near 100
      Most expensive within its cohort -> score near 0

Because some cohorts can be too small, we use **hierarchical fallbacks** that
broaden the mileage bins (10k -> 25k -> 50k).

Why this matches "relative scoring":
    The score is computed from empirical distributions of your own data.
    If the market shifts, the score shifts automatically.

We also apply weighted overlays for fuel_type, transmission, color, variant, and accident.
"""

from __future__ import annotations

from datetime import date
import json
from itertools import combinations
from typing import Any

import numpy as np
import pandas as pd
import sqlite3


def _ensure_series(value: float | int, index: pd.Index) -> pd.Series:
    return pd.Series([value] * len(index), index=index)


def _normalize_text_series(series: pd.Series, *, unknown: str = "unknown") -> pd.Series:
    s = series.astype("string").str.strip()
    s = s.where(s != "", other=unknown)
    return s.fillna(unknown)


def _map_condition_to_score(series: pd.Series) -> pd.Series:
    norm = series.astype("string").str.strip().str.lower()
    norm = norm.str.replace(" ", "_", regex=False).str.replace("-", "_", regex=False)
    mapping = {
        "sehr_gut": 4.0,
        "sehrgut": 4.0,
        "gut": 3.0,
        "ok": 2.0,
        "okay": 2.0,
        "schlecht": 1.0,
    }
    score = norm.map(mapping)
    return score.fillna(2.5).astype(float)


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
    min_group_size: int | pd.Series,
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

    if isinstance(min_group_size, pd.Series):
        min_required = min_group_size.reindex(df.index)
    else:
        min_required = _ensure_series(min_group_size, df.index)

    # If a cohort is too small, we do NOT trust its ranking.
    # We will fill those rows using broader cohorts later.
    score = score.where(group_size >= min_required)
    pct = pct.where(group_size >= min_required)

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
    km_bin_xlarge: int = 50_000,
) -> int:
    """Compute + persist scores for all listings.

    Parameters
    - min_group_size: minimum cohort size to trust a percentile ranking.
    - km_bin_small/km_bin_large/km_bin_xlarge: mileage bucket widths.
    """

    df = pd.read_sql_query(
        """
        SELECT
            id, brand, model, year, mileage_km, price_eur,
            fuel_type, transmission, color, variant, condition,
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

    # Normalize condition into numeric scale for grouping
    df["condition_score"] = _map_condition_to_score(df["condition"])

    # Buckets for comparable cohorts
    df["km_bin_small"] = (df["mileage_km"] // km_bin_small) * km_bin_small
    df["km_bin_large"] = (df["mileage_km"] // km_bin_large) * km_bin_large
    df["km_bin_xlarge"] = (df["mileage_km"] // km_bin_xlarge) * km_bin_xlarge

    # Output columns
    df["score"] = np.nan
    df["score_level"] = None
    df["score_group_size"] = np.nan
    df["score_price_percentile"] = np.nan
    df["km_bin_used"] = np.nan

    # Current cohort sizes (brand+model+year)
    bmy_current_n = df.groupby(["brand", "model", "year"], sort=False)["id"].transform("size")
    df["bmy_km10k_n"] = df.groupby(
        ["brand", "model", "year", "km_bin_small"], sort=False
    )["id"].transform("size")
    df["bmy_km25k_n"] = df.groupby(
        ["brand", "model", "year", "km_bin_large"], sort=False
    )["id"].transform("size")
    df["bmy_km50k_n"] = df.groupby(
        ["brand", "model", "year", "km_bin_xlarge"], sort=False
    )["id"].transform("size")
    df["bmy_max_n"] = bmy_current_n
    try:
        bmy_hist = pd.read_sql_query(
            """
            SELECT brand, model, year, MAX(n) AS max_n
            FROM model_year_stats
            GROUP BY brand, model, year
            """,
            con,
        )
        if not bmy_hist.empty:
            bmy_hist["max_n"] = bmy_hist["max_n"].astype(int)
            df = df.merge(bmy_hist, on=["brand", "model", "year"], how="left")
            df["bmy_max_n"] = df["max_n"].fillna(bmy_current_n).astype(int)
            df = df.drop(columns=["max_n"])
    except Exception:
        # If stats table is missing on a fresh DB, fall back to current counts.
        pass

    # Hierarchical cohorts: narrow -> broad (brand+model+year are non-negotiable)
    levels: list[tuple[str, list[str], int]] = [
        (
            "bmy_km10k_cond",
            ["brand", "model", "year", "km_bin_small", "condition_score"],
            min_group_size,
        ),
        (
            "bmy_km25k_cond",
            ["brand", "model", "year", "km_bin_large", "condition_score"],
            min_group_size,
        ),
        (
            "bmy_km50k_cond",
            ["brand", "model", "year", "km_bin_xlarge", "condition_score"],
            1,
        ),
    ]

    for level_name, keys, level_min_n in levels:
        remaining = df["score"].isna()
        if not remaining.any():
            break

        # Dynamic threshold: only mileage bin size limits the minimum.
        min_required = np.minimum(level_min_n, df["bmy_max_n"])
        if level_name == "bmy_km10k_cond":
            min_required = np.minimum(min_required, df["bmy_km10k_n"])
        elif level_name == "bmy_km25k_cond":
            min_required = np.minimum(min_required, df["bmy_km25k_n"])
        elif level_name == "bmy_km50k_cond":
            min_required = _ensure_series(1, df.index)
        min_required = min_required.clip(lower=1)

        score_s, group_size_s, pct_s = _compute_percentile_score(
            df,
            keys=keys,
            level_name=level_name,
            min_group_size=min_required,
        )

        fill_mask = remaining & score_s.notna()
        if not fill_mask.any():
            continue

        df.loc[fill_mask, "score"] = score_s.loc[fill_mask].round(1)
        df.loc[fill_mask, "score_level"] = level_name
        df.loc[fill_mask, "score_group_size"] = group_size_s.loc[fill_mask].astype(int)
        df.loc[fill_mask, "score_price_percentile"] = pct_s.loc[fill_mask].round(4)
        if level_name == "bmy_km10k_cond":
            df.loc[fill_mask, "km_bin_used"] = df.loc[fill_mask, "km_bin_small"]
        elif level_name == "bmy_km25k_cond":
            df.loc[fill_mask, "km_bin_used"] = df.loc[fill_mask, "km_bin_large"]
        elif level_name == "bmy_km50k_cond":
            df.loc[fill_mask, "km_bin_used"] = df.loc[fill_mask, "km_bin_xlarge"]

    # Overlays for extra conditions (fuel/transmission/color/variant/accident) with diminishing weights
    df["fuel_type_norm"] = _normalize_text_series(df["fuel_type"])
    df["transmission_norm"] = _normalize_text_series(df["transmission"])
    df["color_norm"] = _normalize_text_series(df["color"])
    df["variant_norm"] = _normalize_text_series(df["variant"])
    df["accident_flag"] = df["accident"].astype(int)

    base_keys = ["brand", "model", "year", "km_bin_used", "condition_score"]
    base_weight = 1.0
    score_total = df["score"] * base_weight
    weight_total = _ensure_series(base_weight, df.index)

    base_weights = {
        "fuel_type_norm": 0.5,
        "transmission_norm": 0.5,
        "color_norm": 0.5,
        "variant_norm": 0.5,
        "accident_flag": 1.0,
    }

    for size in (1, 2, 3):
        for combo in combinations(base_weights.keys(), size):
            combo_keys = list(combo)
            combo_weight = sum(base_weights[k] for k in combo_keys) / len(combo_keys)
            combo_weight = combo_weight / (2 ** (size - 1))

            overlay_score, overlay_group_size, _ = _compute_percentile_score(
                df,
                keys=base_keys + combo_keys,
                level_name=f"overlay_{'_'.join(combo_keys)}",
                min_group_size=1,
            )

            ratio = (overlay_group_size / df["score_group_size"]).clip(lower=0.0, upper=1.0)
            overlay_weight = combo_weight * (0.5 + 0.5 * ratio)

            score_total = score_total + overlay_score * overlay_weight
            weight_total = weight_total + overlay_weight

    df["score"] = (score_total / weight_total).round(1)

    # Singleton rule: only ever one listing for brand+model+year => guaranteed 100
    singleton_mask = df["bmy_max_n"] <= 1
    if singleton_mask.any():
        df.loc[singleton_mask, "score"] = 100.0
        df.loc[singleton_mask, "score_level"] = "bmy_singleton"
        df.loc[singleton_mask, "score_group_size"] = 1
        df.loc[singleton_mask, "score_price_percentile"] = np.nan

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
