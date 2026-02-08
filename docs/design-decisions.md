---
title: Design decisions
nav_order: 4
---

# Design decisions

## Scraper

- Entscheidung für **Selenium**, da es eine der bekanntesten Browser-Automation-Bibliotheken ist und auf eine breite Dokumentation und viele Use-Case-Beispiele zurückgreifen lässt.
- Einfache HTML-Scraper wie **BeautifulSoup** wurden als funktional nicht genügend bewertet, da die meisten Autohandel-Plattformen dynamisch sind.
- Gegen ein hybrides Modell entschieden, um den Stack nicht weiter zu verkomplizieren.

## Scorer

- Bracket-reduziertes Scoring-Modell basierend auf der Marktspezifik entwickelt, da viele Parameter als „abgrenzende Parameter“ gelten und deshalb nicht überschritten werden dürfen.

## Interface

- Selbstständiges Scraping nicht als separate Seite integriert, da es zu langen Wartezeiten und dem Gefühl eines „hängenden Browsers“ führte.
- Diskutiert: Scrape-Button mit farbiger Statusanzeige **oder** automatisierter Start mit Ausgabe in einem hypothetischen Server-Zustandsblock. Beides für spätere Versionen.
- Interface orientiert sich an bestehenden Formatvorlagen, um den Designaufwand zu reduzieren.
