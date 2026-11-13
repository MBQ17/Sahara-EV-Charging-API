
import re
import json
from datetime import datetime, timezone
from collections import defaultdict
from pathlib import Path

import requests
from bs4 import BeautifulSoup

URL = "https://saraicharge.com/chargers/"
OUTPUT_FILE = Path("data.json")


def extract_price(text):
    """Extract price in PKR/kWh."""

    match = re.search(
        r"(?:PKR|Rs\.?)\s*([\d,]+(?:\.\d+)?)\s*/\s*kWh\b",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return float(match.group(1).replace(",", ""))


def normalize(text):
    return re.sub(r"\s+", " ", text).strip().lower()


def scrape_city_averages():

    print("Connecting to Sarai Charge...")

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; SaharaEVResearch/1.0)"
    }

    response = requests.get(
        URL,
        headers=headers,
        timeout=30
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    station_table = None

    for table in soup.find_all("table"):

        for row in table.find_all("tr"):

            cells = row.find_all(["th", "td"], recursive=False)

            headings = [
                normalize(cell.get_text(" ", strip=True))
                for cell in cells
            ]

            if (
                "station" in headings
                and "city" in headings
                and "price" in headings
            ):
                station_table = table
                break

        if station_table:
            break

    if station_table is None:
        raise ValueError("Station table not found.")

    rows = station_table.find_all("tr")

    header_names = []
    header_row = None

    for row in rows:

        cells = row.find_all(["th", "td"], recursive=False)

        names = [
            normalize(cell.get_text(" ", strip=True))
            for cell in cells
        ]

        if (
            "station" in names
            and "city" in names
            and "price" in names
        ):
            header_row = row
            header_names = names
            break

    if header_row is None:
        raise ValueError("Could not identify station columns.")

    city_index = header_names.index("city")
    price_index = header_names.index("price")

    city_prices = defaultdict(list)

    station_count = 0
    missing_prices = 0

    for row in rows:

        if row == header_row:
            continue

        cells = row.find_all(["th", "td"], recursive=False)

        if len(cells) <= max(city_index, price_index):
            continue

        city = cells[city_index].get_text(" ", strip=True)

        price_text = cells[price_index].get_text(" ", strip=True)

        if not city or normalize(city) == "city":
            continue

        price = extract_price(price_text)

        if price is None:
            missing_prices += 1
            continue

        city_prices[city].append(price)
        station_count += 1

    if not city_prices:
        raise ValueError("No valid station prices found.")

    # Prepare API data

    city_data = []

    for city, prices in sorted(city_prices.items()):

        average = sum(prices) / len(prices)

        city_data.append({
            "city": city,
            "stations_priced": len(prices),
            "average_price_per_kwh": round(average, 2),
            "currency": "PKR"
        })

    # Create JSON response

    data = {
        "status": "success",
        "country": "Pakistan",
        "source": URL,
        "last_updated": datetime.now(
            timezone.utc
        ).isoformat(),
        "total_stations_priced": station_count,
        "missing_prices": missing_prices,
        "unit": "PKR/kWh",
        "cities": city_data
    }

    # Save only after successful scraping and validation

    temp_file = OUTPUT_FILE.with_suffix(".tmp")

    with open(temp_file, "w", encoding="utf-8") as file:

        json.dump(
            data,
            file,
            indent=4,
            ensure_ascii=False
        )

    temp_file.replace(OUTPUT_FILE)

    # Display report

    print("\nSAHARA EV CHARGING PRICE REPORT")

    print("-" * 65)

    for item in city_data:

        print(
            f"{item['city']:<25}"
            f"{item['stations_priced']:>10}"
            f"{item['average_price_per_kwh']:>15.2f} PKR"
        )

    print("-" * 65)

    print("Total stations:", station_count)
    print("Missing prices:", missing_prices)

    print("\nAPI JSON updated successfully!")


def main():

    try:

        scrape_city_averages()

    except requests.RequestException as error:

        print("Network error:", error)
        raise

    except Exception as error:

        print("Scraping failed:", error)
        raise


if __name__ == "__main__":
    main()
