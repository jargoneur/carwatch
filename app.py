"""CarWatch Flask app.

Backend responsibilities (your part):
- SQLite database access
- scraping + upsert pipeline (via CLI commands)
- scoring pipeline (via CLI commands)
- search endpoints (HTML + JSON)
- login/session (minimal)

Run (dev):
  python app.py

CLI examples:
  flask --app app init-db
  flask --app app seed-dev
  flask --app app scrape --source demo-json --input-file sample_data/demo_listings.json
  flask --app app score
"""

from __future__ import annotations

import os 
from flask import Flask, redirect, url_for

import db
import auth
from auth import auth_bp as auth_bp
from cars import cars_bp as cars_bp
from tasks import register_cli


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)

    # NOTE: For a real deployment, do NOT hardcode the secret key.
    # Use an environment variable instead.
    app.config.from_mapping(
        SECRET_KEY=os.environ.get("CARWATCH_SECRET_KEY", "dev-only-secret"),
        DATABASE=os.path.join(app.instance_path, "carwatch.sqlite"),
    )
    if test_config:
        app.config.update(test_config)

    # Ensure instance folder exists
    try:
        os.makedirs(app.instance_path, exist_ok=True)
    except OSError:
        pass

    # DB lifecycle + init command
    db.init_app(app)

    # Blueprints
    app.register_blueprint(auth_bp)
    app.register_blueprint(cars_bp)

    # Auth CLI (create-user)
    auth.init_app(app)

    # CLI tasks (scrape/score/dev-seed)
    register_cli(app)

    @app.route("/")
    def index():
        return redirect(url_for("auth.login"))

    return app


if __name__ == "__main__":
    create_app().run(debug=True)
