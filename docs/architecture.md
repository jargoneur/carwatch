---
title: Architecture
nav_order: 2
---

# Architecture

## Überblick

Dieses Diagramm zeigt die Hauptbausteine (Flask App, Scraping, Scorer, Database) und deren Kopplungen.

## Diagramm (empfohlen: als SVG einbetten)

> **Warum SVG?** GitHub Pages rendert `.puml`/`.drawio` nicht „von selbst“. SVG wird zuverlässig im Browser angezeigt.

1. Exportiere dein Diagramm als **SVG** nach: `docs/assets/img/architecture.svg`
2. Dann wird es hier automatisch angezeigt:

![Architecture diagram]({{ site.baseurl }}/assets/img/architecture.svg)

---

## Roh-Quelle (PlantUML)

Falls du das Diagramm später wieder rendern willst, ist hier die PlantUML-Quelle:

```plantuml
@startuml
skinparam componentStyle rectangle

package "Flask App" {
  [app.py] as App
  [auth.py] as Auth
  [cars.py] as Cars
  [tasks.py] as Tasks
  [db.py] as DB
  [templates/*] as Templates
}

package "Scraping" {
  [scrapers/koenig.py] as Koenig
  [upsert.py] as Upsert
}

package "Scorer" {
  [scoring.py] as Scoring
}

package "Database" {
  [sql/create_tables.sql] as Schema
  [instance/carwatch.sqlite] as SQLite
}

' App wiring
App --> Auth : register blueprint\n+ CLI create-user
App --> Cars : register blueprint
App --> Tasks : register CLI
App --> DB : init_app()\nDB lifecycle

' Request flow
Auth --> DB : users login\ncreate-user
Auth --> Templates : Login/Profil HTML

Cars --> DB : listings + saved_cars\nfilters/sort
Cars --> Templates : Autoliste HTML

' CLI tasks
Tasks --> DB : get_db_con()
Tasks ---> Upsert : upsert_listing()
Tasks --> Scoring : score_all_listings()
Tasks <---> Koenig : iter_koenig_listings()

' Scraping + upsert
Koenig --> "Selenium/ChromeDriver" : browser automation
Upsert --> DB : insert/update listings\n+ price history

'Scoring
Scoring -> DB : insert Score

' DB init
DB --> Schema : create/drop tables
DB --> SQLite : SQLite connection
@enduml
```
