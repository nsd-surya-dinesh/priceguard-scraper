import subprocess
import json
import re
import sqlite3
from datetime import datetime

COLLECTOR_ID = "c_msymhd5y23d7ustw2z"
TARGET_URL = "https://www.croma.com/computers-tablets/laptops/c/20"
DB_FILE = "prices.db"


def strip_ansi(text):
    """Removes ANSI escape codes (color/spinner control characters) from CLI output."""
    ansi_pattern = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    return ansi_pattern.sub('', text)


BDATA_PATH = r"C:\Users\nagas\AppData\Local\npm-cache\_npx\47c97c996798144b\node_modules\.bin\bdata.cmd"


def run_scraper():
    """Runs the Bright Data scraper via CLI and returns parsed JSON."""
    command = f'"{BDATA_PATH}" scraper run {COLLECTOR_ID} "{TARGET_URL}"'
    result = subprocess.run(
        command,
        shell=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=180  # fail after 3 minutes instead of hanging indefinitely
    )

    raw_stdout = strip_ansi(result.stdout)
    raw_stderr = strip_ansi(result.stderr)
    combined = raw_stdout + "\n" + raw_stderr

    # Debug: show what was actually captured if JSON extraction fails later.
    print("----- RAW CLI OUTPUT (for debugging) -----")
    print(combined)
    print("-------------------------------------------")

    # Find the LAST '[' that starts a valid JSON array (in case spinner text
    # also contains stray '[' characters from formatting).
    json_start = combined.rfind("[")
    json_end = combined.rfind("]")

    if json_start == -1 or json_end == -1 or json_end < json_start:
        raise ValueError("No JSON found in scraper output:\n" + combined)

    json_text = combined[json_start:json_end + 1]
    return json.loads(json_text)


def parse_discount(raw_discount):
    """Fixes Bright Data's garbled discount string into readable format."""
    if not raw_discount:
        return None

    percent_match = re.search(r'(\d+\.?\d*)%', raw_discount)
    # Amount appears as digits with commas, anywhere in the string
    amount_match = re.search(r'([\d,]+)\(Save', raw_discount)

    percent = percent_match.group(1) if percent_match else None
    amount = amount_match.group(1) if amount_match else None

    if percent and amount:
        return f"Save ₹{amount} ({percent}% off)"
    return raw_discount


def init_db():
    """Creates tables if they don't exist yet."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            product_name TEXT,
            price_value REAL,
            currency TEXT,
            discount TEXT,
            stock_availability TEXT,
            product_url TEXT,
            scraped_at TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS scraper_health (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            run_at TEXT,
            status TEXT,
            details TEXT
        )
    """)

    conn.commit()
    conn.close()


def save_results(products):
    """Saves scraped product data into the database."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()

    for product in products:
        name = product.get("product_name")

        # Skip non-laptop items (warranties, support plans, accessories)
        if name and any(keyword in name.lower() for keyword in ["zipcare", "warranty", "support", "care plan"]):
            continue

        if not name:
            # Fallback: derive a readable name from the URL slug if missing.
            # URLs look like: .../some-product-name-slug-/p/322265
            # so we split on '/p/' and take the part before it.
            url_for_name = product.get("product_page_url", "")
            if "/p/" in url_for_name:
                slug = url_for_name.split("/p/")[0].rstrip("/").split("/")[-1]
            else:
                slug = "Unknown Product"
            name = slug.replace("-", " ").title()

        price_info = product.get("price", {})
        price_value = price_info.get("value")
        currency = price_info.get("currency")
        discount = parse_discount(product.get("discount_percentage"))
        stock = product.get("stock_availability")
        url = product.get("product_page_url")

        cursor.execute("""
            INSERT INTO prices (product_name, price_value, currency, discount,
                                 stock_availability, product_url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (name, price_value, currency, discount, stock, url, timestamp))

    conn.commit()
    conn.close()


def log_health(status, details=""):
    """Logs whether the scrape run succeeded or failed."""
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    timestamp = datetime.now().isoformat()

    cursor.execute("""
        INSERT INTO scraper_health (run_at, status, details)
        VALUES (?, ?, ?)
    """, (timestamp, status, details))

    conn.commit()
    conn.close()


def main():
    init_db()

    try:
        products = run_scraper()

        if not products:
            log_health("failed", "Empty result returned")
            print("Scrape returned no products. Logged as failed.")
            return

        save_results(products)
        log_health("success", f"{len(products)} products saved")
        print(f"Saved {len(products)} products to {DB_FILE}")

    except subprocess.TimeoutExpired:
        log_health("failed", "Scraper timed out after 180 seconds")
        print("Scrape timed out. Try again — Croma's page can be slow to load sometimes.")
    except Exception as e:
        log_health("failed", str(e))
        print(f"Scrape failed: {e}")


if __name__ == "__main__":
    main()
