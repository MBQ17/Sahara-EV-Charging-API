
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


SOURCE_URL = "https://saraicharge.com/chargers/"
OUTPUT_FILE = Path(__file__).parent / "public" / "data.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/120.0 Safari/537.36"
    )
}

TIMEOUT = 30


def get_page():
    response = requests.get(
        SOURCE_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )
    response.raise_for_status()
    return BeautifulSoup(response.text, "html.parser")


def get_station_data(soup):
    stations = []
    current_city = None
    seen_urls = set()

    # Read city headings and station links in document order.
    for element in soup.find_all(["h2", "h3", "h4", "a"]):

        if element.name in ("h2", "h3", "h4"):
            heading = element.get_text(" ", strip=True)

            match = re.match(
                r"^(.+?)\s+\d+\s+stations?\b",
                heading,
                re.IGNORECASE
            )

            if match:
                current_city = match.group(1).strip()

        elif element.name == "a":

            href = element.get("href", "")

            if not href:
                continue

            station_url = urljoin(SOURCE_URL, href)
            path_parts = [
                part for part in urlparse(station_url).path.split("/")
                if part
            ]

            # Station detail URLs have at least three path parts:
            # chargers / station-slug / (additional path if applicable)
            # City overview URLs are only chargers / city-slug.
            if len(path_parts) < 2:
                continue

            if path_parts[0] != "chargers":
                continue

            if len(path_parts) == 2:
                continue

            if station_url in seen_urls:
                continue

            name = element.get_text(" ", strip=True)

            if not name:
                continue

            # Station information is listed in the surrounding list item.
            parent = element.find_parent("li")

            if parent is None:
                continue

            details = parent.get_text(" ", strip=True)

            if not re.search(r"\b(?:DC|AC)\b", details, re.I):
                continue

            power_match = re.search(
                r"(\d+(?:\.\d+)?)\s*kW\b",
                details,
                re.IGNORECASE
            )

            price_match = re.search(
                r"PKR\s*([\d,]+)\s*(?:/|per)\s*kWh",
                details,
                re.IGNORECASE
            )

            power = (
                float(power_match.group(1))
                if power_match else None
            )

            price = (
                float(price_match.group(1).replace(",", ""))
                if price_match else None
            )

            charger_type = (
                "DC" if re.search(r"\bDC\b", details, re.I)
                else "AC"
            )

            if not current_city:
                continue

            station = {
                "name": name,
                "city": current_city,
                "power_kw": power,
                "charger_type": charger_type,
                "price_per_kwh": price,
                "currency": "PKR",
                "source_url": station_url
            }

            stations.append(station)
            seen_urls.add(station_url)

    if not stations:
        raise ValueError(
            "No stations were extracted. "
            "The website HTML structure may have changed."
        )

    return stations


def calculate_city_rates(stations):
    cities = {}

    for station in stations:
        city = station["city"]

        if city not in cities:
            cities[city] = []

        cities[city].append(station)

    results = {}

    for city, city_stations in cities.items():

        priced_stations = [
            s for s in city_stations
            if s["price_per_kwh"] is not None
        ]

        powered_stations = [
            s for s in city_stations
            if s["power_kw"] is not None
        ]

        cheapest = (
            min(
                priced_stations,
                key=lambda s: s["price_per_kwh"]
            )
            if priced_stations else None
        )

        fastest = (
            max(
                powered_stations,
                key=lambda s: s["power_kw"]
            )
            if powered_stations else None
        )

        fastest_price = (
            fastest["price_per_kwh"]
            if fastest else None
        )

        if (
            cheapest is not None
            and fastest_price is not None
        ):
            average_rate = round(
                (cheapest["price_per_kwh"] + fastest_price) / 2,
                2
            )
        else:
            average_rate = None

        results[city] = {
            "total_stations": len(city_stations),

            "cheapest_station": cheapest,
            "cheapest_rate": (
                cheapest["price_per_kwh"]
                if cheapest else None
            ),

            "fastest_station": fastest,
            "fastest_power_kw": (
                fastest["power_kw"]
                if fastest else None
            ),
            "fastest_station_rate": fastest_price,

            "average_rate": average_rate,
            "currency": "PKR",
            "unit": "kWh"
        }

    return results


def save_data(stations, cities):
    OUTPUT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    old_data = {}

    if OUTPUT_FILE.exists():
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as file:
                old_data = json.load(file)
        except (json.JSONDecodeError, OSError):
            old_data = {}

    # Sort data to avoid unnecessary changes.
    stations.sort(
        key=lambda s: (
            s["city"].lower(),
            s["name"].lower()
        )
    )

    new_content = {
        "source": SOURCE_URL,
        "total_stations": len(stations),
        "total_cities": len(cities),
        "stations": stations,
        "cities": cities
    }

    old_content = {
        key: old_data.get(key)
        for key in new_content
    }

    if old_content == new_content:
        print("No data changes detected.")
        print(
            "Last updated:",
            old_data.get("last_updated")
        )
        return

    now = datetime.now(timezone.utc).isoformat()

    new_content["last_checked"] = now
    new_content["last_updated"] = now

    with open(OUTPUT_FILE, "w", encoding="utf-8") as file:
        json.dump(
            new_content,
            file,
            indent=4,
            ensure_ascii=False
        )

    print("Data successfully updated.")
    print("Total stations:", len(stations))
    print("Total cities:", len(cities))
    print("Last updated:", now)


def main():
    print("Starting Sahara EV Tariff Scraper...")

    soup = get_page()

    print("Website successfully accessed.")

    stations = get_station_data(soup)

    print("Stations extracted:", len(stations))

    cities = calculate_city_rates(stations)

    save_data(stations, cities)

    print("Scraper completed successfully.")


if __name__ == "__main__":
    main()
