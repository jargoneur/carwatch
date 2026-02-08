**Value Proposition**

- Zusammenführung von Autoanzeigen aus externen Automobilseiten an einem
  Ort, spart Zeit und reduziert Suchaufwand

- Transparente Vergleichbarkeit durch standardisiertes Scoring-System
  von .0.00 bis 100.00

- effizientere Fahrzeugsuche durch Filter nach relevanten Kriterien
  statt unübersichtlicher Einzelportale

**Architecture**

> <img src="media/image1.png" style="width:6.26772in;height:3.25in" />
>
> @startuml
>
> skinparam componentStyle rectangle
>
> package "Flask App" {
>
> \[app.py\] as App
>
> \[auth.py\] as Auth
>
> \[cars.py\] as Cars
>
> \[tasks.py\] as Tasks
>
> \[db.py\] as DB
>
> \[templates/\*\] as Templates
>
> }
>
> package "Scraping" {
>
> \[scrapers/koenig.py\] as Koenig
>
> \[upsert.py\] as Upsert
>
> }
>
> package "Scorer" {
>
> \[scoring.py\] as Scoring
>
> }
>
> package "Database" {
>
> \[sql/create_tables.sql\] as Schema
>
> \[instance/carwatch.sqlite\] as SQLite
>
> }
>
> ' App wiring
>
> App --\> Auth : register blueprint\n+ CLI create-user
>
> App --\> Cars : register blueprint
>
> App --\> Tasks : register CLI
>
> App --\> DB : init_app()\nDB lifecycle
>
> ' Request flow
>
> Auth --\> DB : users login\ncreate-user
>
> Auth --\> Templates : Login/Profil HTML
>
> Cars --\> DB : listings + saved_cars\nfilters/sort
>
> Cars --\> Templates : Autoliste HTML
>
> ' CLI tasks
>
> Tasks --\> DB : get_db_con()
>
> Tasks ---\> Upsert : upsert_listing()
>
> Tasks --\> Scoring : score_all_listings()
>
> Tasks \<---\> Koenig : iter_koenig_listings()
>
> ' Scraping + upsert
>
> Koenig --\> "Selenium/ChromeDriver" : browser automation
>
> Upsert --\> DB : insert/update listings\n+ price history
>
> 'Scoring
>
> Scoring -\> DB : insert Score
>
> ' DB init
>
> DB --\> Schema : create/drop tables
>
> DB --\> SQLite : SQLite connection
>
> @enduml

**Data Model**

> <img src="media/image2.png" style="width:6.26772in;height:8.93056in" />
>
> **\`\`\` Mermaid**
>
> **erDiagram**
>
> USERS **\|\|--o{** SAVED_CARS **:** saves
>
> LISTINGS **\|\|--o{** SAVED_CARS **:** saved_by
>
> LISTINGS **\|\|--o{** LISTING_PRICE_HISTORY **:** price_history
>
> LISTINGS **\|\|--o{** LISTING_SCORE_HISTORY **:** score_history
>
> USERS **{**
>
> INT id PK
>
> TEXT username
>
> TEXT email
>
> TEXT password_hash
>
> TEXT created_at
>
> **}**
>
> LISTINGS **{**
>
> INT id PK
>
> TEXT source
>
> TEXT external_id
>
> TEXT url
>
> TEXT title
>
> TEXT brand
>
> TEXT model
>
> TEXT variant
>
> INT year
>
> INT mileage_km
>
> INT price_eur
>
> TEXT fuel_type
>
> TEXT transmission
>
> TEXT color
>
> INT accident
>
> TEXT condition
>
> REAL score
>
> TEXT score_version
>
> TEXT score_computed_at
>
> TEXT score_level
>
> INT score_group_size
>
> REAL score_price_percentile
>
> TEXT raw_json
>
> TEXT first_seen_at
>
> TEXT last_seen_at
>
> TEXT updated_at
>
> INT is_active
>
> **}**
>
> SAVED_CARS **{**
>
> INT user_id FK
>
> INT listing_id FK
>
> TEXT created_at
>
> **}**
>
> LISTING_PRICE_HISTORY **{**
>
> INT id PK
>
> INT listing_id FK
>
> TEXT recorded_at
>
> INT price_eur
>
> INT mileage_km
>
> **}**
>
> LISTING_SCORE_HISTORY **{**
>
> int id PK
>
> INT listing_id FK
>
> TEXT computed_at
>
> REAL score
>
> TEXT score_version
>
> TEXT details_json
>
> **}**
>
> MODEL_YEAR_STATS **{**
>
> INT id PK
>
> TEXT snapshot_date
>
> TEXT brand
>
> TEXT model
>
> INT year
>
> INT n
>
> REAL avg_price
>
> REAL median_price
>
> REAL avg_mileage
>
> REAL median_mileage
>
> TEXT updated_at
>
> **}**
>
> \`\`\`

**Reference**

- Technische Orientierung an bestehenden Auto-Marktplätzen und
  Vergleichsplattformen

- Nutzung von Dokumentationen und Best Practices zu Web Scraping,
  REST-APIs und Filterlogik

**Design decisions**

- Scraper: Es wurde die Entscheidung gefällt Selenium zu nutzen, da es
  die bekannteste Browser Automation Bibliothek ist, die auf eine
  ausführliche Dokumentation und viele Use-Case Beispiele hoffen lassen
  hat. einfache HTML-Scraper wie BeautifulSoup wurden als Funktional
  nicht genügend gewertet, da die meisten Autohandel-Plattformen
  dynamisch sind. Wir haben uns gegen ein hybrides Modell entschieden,
  weil das den Stack noch weiter verkomplizieren würde.

- Scorer: Das Bracket-Reduzierte Scoring Modell wurde auf Basis der
  Marktspezifik entwickelt, da viele der Parameter als abgrenzende
  Parameter gelten und deshalb nicht überschritten werden dürfen.

- Interface

  - Die Option des selbstständigen Scrapens wurde nicht als separate
    Seite eingefügt, da eine solche Lösung zu langen Wartezeiten führte
    und das Gefühl eines hängenden Browsers kreierte. Zurzeit werden die
    Optionen eines Scrape buttons, mit Farbiger Statusanzeige und eines
    Automatisierten Scraping-Starts mit Ausgabe in einem Hypothetischen
    Server-Zustand Block Diskutiert. Beide Lösungen mitsamt Startblock
    werden aber erst in späteren Versionen realisiert werden können.

  - Das Interface wurde auf Basis exestierender Formatvolagen entwickelt
    um mit grafischem Design verbundenen Aufwand zu reduziert

**User evaluation**

- Direktes Feedback zu Verständlichkeit und Bedienung

- Kurzer Test mit Nutzern zur Bewertung von Übersichtlichkeit, Filtern
  und Scoring-Verständlichkeit

- Feedback zeigte schnellen Mehrwert, aber Verbesserungsbedarf bei
  Erklärung des Scoring-Systems

**Goals achieved & missed**

Achieved

- Kernfunktionen erfolgreich umgesetzt, Übersichtliche Zusammenführung
  von Autoanzeigen aus einer externen Automobilseite an einem Ort

- funktionierenden Filter

- übersichtliche Anzeige von den Autos

Missed

- Einbindung von mehreren externen Automobil-Seiten

- eventuelles Anschreiben von den Autoanzeigen

**How we would improve next time**

- Frühere Tests mit Nutzern, um Feedback einzuholen und bessere bzw.
  schnellere Änderungen vornehmen zu können

**Peer review Individual contributions**

- Klare Aufgabenverteilung im Team, Frontend, Backend, Scraping,
  Dokumenation

- Eigenverantwortliche Umsetzung für Planung, Umsetzung und Tests seiner
  Bereiche

**Sources**

- ChatGPT kenntlich machen, Internetseiten

- Frontend: CSS mit hilfe von ChatGPT, grobes Layout, Hilfe mit dem
  Filter zurücksetzen

- Backend:

Repository with basic GitHub Pages structure:
https://github.com/hwrberlin/fswd-app/tree/docs Some inspiration for
your technical documentation: https://arc42.org

Schritte noch

[<u>READ.me</u>](http://read.me) kleine Anleitung zum Starten/Benutzung
der App

Word-Datei konvertieren und in GitHub-Pages einfügen

**Schritt 1: Word in Markdown umwandeln**

- Öffnet die .docx lokal

- Mit **Pandoc** konvertieren

- pandoc dokumentation.docx -o docs/index.md

- Danach Markdown **manuell nachziehen**

  - Überschriften prüfen

  - Tabellen und Aufzählungen fixen

  - Bilder in docs/img/ legen und verlinken

**Schritt 2: Struktur aufbauen**

Empfohlene Struktur

docs/

index.md

architecture.md

data-model.md

design-decisions.md

evaluation.md

**Schritt 3: MkDocs aufsetzen**

pip install mkdocs

mkdocs new .

mkdocs.yml minimal:

site_name: CarWatch Documentation

nav:

\- Home: index.md

\- Architecture: architecture.md

\- Data Model: data-model.md

\- Design Decisions: design-decisions.md

\- Evaluation: evaluation.md

**Schritt 4: Lokal testen**

mkdocs serve

Browser → http://127.0.0.1:8000

**Schritt 5: Deploy auf GitHub Pages**

mkdocs gh-deploy --force
