"""Authentication (minimal).

This is intentionally small (no Flask-Login dependency). It supports:
- user creation via CLI (create-user)
- login/logout using Flask sessions
- @login_required decorator

Security note: for a course project this is fine; for real production use,
use HTTPS, strong secrets, CSRF protection, rate limiting, etc.
"""

from __future__ import annotations

import re
from functools import wraps
from typing import Any, Callable, TypeVar

import click
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db


bp = Blueprint("auth", __name__)

T = TypeVar("T")


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def _is_email(s: str) -> bool:
    return bool(re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", s.strip()))


@bp.before_app_request
def load_logged_in_user() -> None:
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
        return
    row = db.query_one("SELECT id, username, email, created_at FROM users WHERE id = ?", (user_id,))
    g.user = dict(row) if row else None


def login_required(view: Callable[..., T]) -> Callable[..., T]:
    @wraps(view)
    def wrapped_view(*args: Any, **kwargs: Any):
        if g.get("user") is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)

    return wrapped_view  # type: ignore[return-value]


@bp.route("/login", methods=("GET", "POST"))
def login():
    # Templates in repo are capitalized.
    # If you rename them, update here.
    if request.method == "GET":
        return render_template("Login.html")

    identifier = (request.form.get("identifier") or request.form.get("email") or "").strip()
    password = request.form.get("password") or ""

    if not identifier or not password:
        flash("Bitte Benutzername/E-Mail und Passwort angeben.")
        return render_template("Login.html"), 400

    if _is_email(identifier):
        user = db.query_one("SELECT * FROM users WHERE email = ?", (identifier.lower(),))
    else:
        user = db.query_one("SELECT * FROM users WHERE username = ?", (_normalize_username(identifier),))

    if user is None or not check_password_hash(user["password_hash"], password):
        flash("Login fehlgeschlagen.")
        return render_template("Login.html"), 401

    session.clear()
    session["user_id"] = user["id"]

    next_url = request.args.get("next")
    return redirect(next_url or url_for("cars.autoliste"))


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/profil")
@login_required
def profil():
    # This template is currently static UI; we still pass user for future use.
    return render_template("Profil.html", user=g.user)


@click.command("create-user")
@click.option("--username", prompt=True)
@click.option("--email", prompt=True)
@click.option("--password", prompt=True, hide_input=True, confirmation_prompt=True)
def create_user_cmd(username: str, email: str, password: str):
    username_n = _normalize_username(username)
    email_n = email.strip().lower()
    if not username_n:
        raise click.ClickException("username darf nicht leer sein")
    if not _is_email(email_n):
        raise click.ClickException("Bitte eine gültige E-Mail angeben")

    existing = db.query_one("SELECT id FROM users WHERE username = ? OR email = ?", (username_n, email_n))
    if existing:
        raise click.ClickException("User existiert schon (username oder email)")

    db.execute(
        "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
        (username_n, email_n, generate_password_hash(password)),
    )
    click.echo(f"User '{username_n}' angelegt.")


def init_app(app) -> None:
    app.cli.add_command(create_user_cmd)
