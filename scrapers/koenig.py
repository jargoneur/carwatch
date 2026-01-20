from __future__ import annotations
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException
import time
import random
from contextlib import contextmanager
from typing import Any, Generator
import re
from pathlib import Path

def make_driver(*, headless: bool, user_data_dir: str | None) -> webdriver.Chrome:
    options = Options()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    if headless:
        options.add_argument("--headless=new")
    if user_data_dir:
        options.add_argument(f"--user-data-dir={user_data_dir}")
    return webdriver.Chrome(options=options)


def human_sleep(a=0.6, b=1.2):
    time.sleep(random.uniform(a, b))

def collect_listing_urls(driver: webdriver.Chrome, wait: WebDriverWait,) -> list[str]:
    driver.get('https://www.autohaus-koenig.de/')
    human_sleep(2.0, 4.0)
    gebrauchtwagen = driver.find_element(By.CSS_SELECTOR, "button[aria-controls='sub-menu-2']")
    gebrauchtwagen.click()

    human_sleep(    2.0, 4.0)
    Angebote = driver.find_element(By.XPATH,"//div[contains(@class,'MainNavigation_sub-menu')]//a[normalize-space()='Angebote']")
    Angebote.click()

    VEHICLE_LINKS = (By.XPATH, "//a[.//text()[contains(.,'Fahrzeug ansehen')] or normalize-space()='Fahrzeug ansehen']")
    LOAD_MORE = (By.XPATH, "//button[normalize-space()='Mehr anzeigen']")
    urls = set()

    def current_urls():
        urls = set()
        for a in driver.find_elements(*VEHICLE_LINKS):
            href = a.get_attribute("href")
            if href:
                urls.add(href)
        return urls
    def try_click_load_more():
        try:
            btn = wait.until(EC.presence_of_element_located(LOAD_MORE))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
            wait.until(EC.element_to_be_clickable(LOAD_MORE)).click()
            time.sleep(1)
            return True
        except TimeoutException:
            return False

    # 1) einmal "Mehr anzeigen" versuchen (falls vorhanden)
    try:
        btn = wait.until(EC.presence_of_element_located(LOAD_MORE))
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
        wait.until(EC.element_to_be_clickable(LOAD_MORE)).click()
        time.sleep(1)
    except TimeoutException:
        pass  # kein Button -> direkt infinite scroll

    def collect_urls():
        return {
            a.get_attribute("href")
            for a in driver.find_elements(*VEHICLE_LINKS)
            if a.get_attribute("href")
        }

    processed = 0              # wie viele "Fahrzeug ansehen"-Links wir schon verarbeitet haben
    no_growth_rounds = 0
    MAX_NO_GROWTH = 12         # wenn zu früh stoppt: 18

    while no_growth_rounds < MAX_NO_GROWTH :
        cards = driver.find_elements(*VEHICLE_LINKS)
        if not cards:
            # kurz warten, falls die Liste gerade neu lädt
            try:
                wait.until(lambda d: len(d.find_elements(*VEHICLE_LINKS)) > 0)
                cards = driver.find_elements(*VEHICLE_LINKS)
            except TimeoutException:
                break

        # ✅ nur NEUE Links einsammeln (statt jedes Mal alle)
        if processed < len(cards):
            for a in cards[processed:]:
                href = a.get_attribute("href")
                if href:
                    urls.add(href)
            processed = len(cards)
            no_growth_rounds = 0
        else:
            no_growth_rounds += 1
        
        print(f"Collected {len(urls)} vehicle URLs so far...")

        # zum letzten Element scrollen -> triggert lazy load
        last = cards[-1]
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", last)

        # falls "Mehr anzeigen" irgendwo erscheint: klicken
        try:
            btn = WebDriverWait(driver, 2).until(EC.element_to_be_clickable(LOAD_MORE))
            btn.click()
            time.sleep(0.8)
            no_growth_rounds = 0
        except TimeoutException:
            pass

        time.sleep(0.8)   # kurze Pause reicht


    vehicle_urls = list(urls)
    return vehicle_urls

def scrape_one_listing(driver: webdriver.Chrome, wait: WebDriverWait, url: str) -> dict[str, Any]:
    

    def read_grey_box(driver, wait) -> dict:
        box = wait.until(EC.presence_of_element_located((
            By.XPATH,
            "//*[contains(@class,'AdditionalVehicleInformation') and .//span[normalize-space()='Bereitstellungszeit:']]"
        )))
        rows = box.find_elements(By.XPATH, ".//div[span and span[1][contains(normalize-space(), ':')]]")

        data = {}
        for r in rows:
            spans = r.find_elements(By.XPATH, ".//span")
            if len(spans) < 2:
                continue
            key = spans[0].text.strip()
            if not key.endswith(":"):
                continue
            key = key[:-1].strip()
            val = spans[1].text.strip()
            if key:
                data[key] = val
        return data


    def read_vehicledata_section(driver, title: str) -> dict:
        try:
            section = driver.find_element(
                By.XPATH,
                f"//h3[normalize-space()='{title}']/following-sibling::*[1]"
            )
        except NoSuchElementException:
            return {}

        rows = section.find_elements(By.XPATH, ".//div[span and count(.//span) >= 2]")
        data = {}
        for r in rows:
            spans = r.find_elements(By.XPATH, ".//span")
            if len(spans) < 2:
                continue
            key = spans[0].text.strip().rstrip(":")
            val = spans[1].text.strip()
            if key:
                data[key] = val
        return data

    def read_price(driver, wait) -> str:
        wait.until(EC.presence_of_all_elements_located((By.XPATH, "//span[contains(@class,'PriceView_brutto')]")))
        for el in driver.find_elements(By.XPATH, "//span[contains(@class,'PriceView_brutto')]"):
            txt = el.text.strip()
            if txt:  # nicht leer
                return txt
        return ""


    def read_header_and_price(driver, wait) -> dict:
        # Marke/Modell
        title = wait.until(EC.presence_of_element_located((By.XPATH, "//h1"))).text.strip()
        parts = title.split(maxsplit=1)
        marke = parts[0]
        modell = parts[1] if len(parts) > 1 else ""

        # Modelldaten (Zeile unter h1)
        try:
            modelldaten = driver.find_element(
                By.XPATH,
                "//h1/following-sibling::*[self::div or self::p or self::h2][normalize-space()][1]"
            ).text.strip()
        except NoSuchElementException:
            modelldaten = ""


        preis = read_price(driver, wait)

        return {"Marke": marke, "Modell": modell, "Modelldaten": modelldaten, "Preis": preis}


    def read_detail_page(driver, wait) -> dict:
        result = {}
        result.update(read_header_and_price(driver, wait))

        try:
            result["info_box"] = read_grey_box(driver, wait)
        except TimeoutException:
            result["info_box"] = {}

        result["vehicle_data"] = {
            "Motorisierung & Leistung": read_vehicledata_section(driver, "Motorisierung & Leistung"),
            "Gewicht & Abmessung": read_vehicledata_section(driver, "Gewicht & Abmessung"),
            "Verbrauchswerte": read_vehicledata_section(driver, "Verbrauchswerte"),
        }
        return result


    def flatten_smart(output: dict) -> dict:
        flat = {}
        flat.update(output.get("info_box", {}))

        for section, fields in output.get("vehicle_data", {}).items():
            for k, v in (fields or {}).items():
                if k in flat:
                    flat[f"{section}__{k}"] = v
                else:
                    flat[k] = v

        # Header/Preis (ohne Prefix) am Ende drauflegen
        for k in ["Marke", "Modell", "Modelldaten", "Preis"]:
            if k in output:
                flat[k] = output[k]

        return flat


    def safe_get_value_next_to_label(driver, label: str) -> str:
        try:
            return driver.find_element(
                By.XPATH,
                f"//*[normalize-space()='{label}:']/following-sibling::*[1]"
            ).text.strip()
        except NoSuchElementException:
            return ""
    driver.get(url)
    human_sleep(2.0, 4.0)  
    raw = read_detail_page(driver, wait)
    output = flatten_smart(raw)

    output["Farbe außen"] = safe_get_value_next_to_label(driver, "Farbe außen")
    output["Innenfarbe"] = safe_get_value_next_to_label(driver, "Innenfarbe")

    return output

def parse_int_de(s: str) -> int | None:
    """
    Beispiele:
      '83.589 km'  -> 83589
      '7.399,00 €' -> 7399
      '999 cm³'    -> 999
      '1359'       -> 1359
    """
    if not s:
        return None
    s = s.strip()

    # Dezimalteil (",00") wegwerfen, falls vorhanden
    if "," in s:
        s = s.split(",", 1)[0]

    # Alles außer Ziffern/Punkt/Space entfernen
    s = re.sub(r"[^\d\. ]+", "", s)

    # Tausendertrenner weg
    s = s.replace(".", "").replace(" ", "").strip()
    if not s:
        return None

    try:
        return int(s)
    except ValueError:
        return None


def parse_year_from_text(s: str) -> int | None:
    """
    '08/2015' -> 2015
    '2015' -> 2015
    """
    if not s:
        return None
    m = re.search(r"(19\d{2}|20\d{2})", s)
    if not m:
        return None
    y = int(m.group(1))
    return y if 1950 <= y <= 2100 else None


def parse_bool_de(s: str) -> int | None:
    """
    'Ja'/'Nein' -> 1/0
    """
    if not s:
        return None
    v = s.strip().lower()
    if v in {"ja", "true", "1"}:
        return 1
    if v in {"nein", "false", "0"}:
        return 0
    return None


def external_id_from_url(url: str) -> str | None:
    if not url:
        return None
    tail = url.rstrip("/").split("/")[-1]
    return tail or None


# ----------------------------
# Normalizer -> DB-Dict (listings)
# ----------------------------

def normalize_koenig(flat: dict[str, Any], url: str) -> dict[str, Any]:
    """
    Output passt zu upsert_listing():
      source, external_id, url, title, brand, model, variant, year,
      mileage_km, price_eur, fuel_type, transmission, color,
      accident, condition, raw_json
    """
    brand = (flat.get("Marke") or "").strip()
    model = (flat.get("Modell") or "").strip()
    variant = (flat.get("Modelldaten") or "").strip() or None

    year = parse_year_from_text(flat.get("Erstzulassung", "") or "")
    mileage_km = parse_int_de(flat.get("Kilometerstand", "") or "")
    price_eur = parse_int_de(flat.get("Preis", "") or "")

    fuel_type = (flat.get("Kraftstoff") or "").strip() or None
    transmission = (flat.get("Getriebe") or "").strip() or None
    color = (flat.get("Farbe außen") or "").strip() or None
    accident = parse_bool_de(flat.get("Unfallfahrzeug", "") or "")
    condition = (flat.get("Zustand") or "").strip() or None

    title = " ".join([p for p in [brand, model, variant] if p]).strip() or None

    return {
        "source": "koenig",
        "external_id": external_id_from_url(url),
        "url": url,
        "title": title,
        "brand": brand,
        "model": model,
        "variant": variant,
        "year": year,
        "mileage_km": mileage_km,
        "price_eur": price_eur,
        "fuel_type": fuel_type,
        "transmission": transmission,
        "color": color,
        "accident": accident,
        "condition": condition,
        # wichtig: upsert_listing json.dumps't das; dict ist ok
        "raw_json": flat,
    }

def iter_koenig_listings(*, headless: bool = True, user_data_dir: str | None = None) -> Generator[dict[str, Any], None, None]:
   
    if user_data_dir is None:
        project_root = Path(__file__).resolve().parents[1]
        user_data_dir = str(project_root / "chrome profile")
    
    driver = make_driver(headless=headless, user_data_dir=user_data_dir)
    wait = WebDriverWait(driver, 20)

    try:
        urls = collect_listing_urls(driver, wait)
        i=0
        for url in urls:
            i+=1
            print(f"Scraping {i}/{len(urls)}: {url}")
            try:
                flat = scrape_one_listing(driver, wait, url)
                yield normalize_koenig(flat, url)
            except Exception as e:
                # sorgt dafür, dass tasks.py failed++ macht, ohne Insert:
                yield {
                    "source": "koenig",
                    "url": url,
                    "brand": "",
                    "model": "",
                    "raw_json": {"error": str(e), "url": url},
                }

    finally:
        try:
            driver.quit()
        except Exception:
            pass
