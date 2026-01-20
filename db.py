

from __future__ import annotations

import os
import sqlite3
from typing import Any, Iterable

import click
from flask import current_app, g


def get_db_con(pragma_foreign_keys: bool = True) -> sqlite3.Connection:
    """Return a cached SQLite connection for the current Flask app context."""
    if "db_con" not in g:
        g.db_con = sqlite3.connect(
            current_app.config["DATABASE"],
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        g.db_con.row_factory = sqlite3.Row
        if pragma_foreign_keys:
            g.db_con.execute("PRAGMA foreign_keys = ON;")
    return g.db_con


def close_db_con(e: Exception | None = None) -> None:
    db_con = g.pop("db_con", None)
    if db_con is not None:
        db_con.close()


def query_one(sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> sqlite3.Row | None:
    con = get_db_con()
    cur = con.execute(sql, params or ())
    return cur.fetchone()


def query_all(sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> list[sqlite3.Row]:
    con = get_db_con()
    cur = con.execute(sql, params or ())
    return cur.fetchall()


def execute(sql: str, params: dict[str, Any] | tuple[Any, ...] | None = None) -> sqlite3.Cursor:
    con = get_db_con()
    cur = con.execute(sql, params or ())
    con.commit()
    return cur


def executemany(sql: str, seq_of_params: Iterable[tuple[Any, ...]]) -> None:
    con = get_db_con()
    con.executemany(sql, seq_of_params)
    con.commit()


@click.command("init-db")
def init_db() -> None:
    """(Re)create all tables."""
    try:
        os.makedirs(current_app.instance_path, exist_ok=True)
    except OSError:
        pass

    con = get_db_con()
    with current_app.open_resource("sql/drop_tables.sql") as f:
        con.executescript(f.read().decode("utf8"))
    with current_app.open_resource("sql/create_tables.sql") as f:
        con.executescript(f.read().decode("utf8"))
    con.commit()
    click.echo("Database has been initialized.")


def init_app(app) -> None:
    """Register db teardown + CLI command on the given Flask app."""
    app.teardown_appcontext(close_db_con)
    app.cli.add_command(init_db)
