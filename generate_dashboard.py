import sqlite3
import json
import os
from datetime import datetime

DB_FILE = "prices.db"
OUTPUT_FILE = "dashboard.html"


def load_data():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM prices ORDER BY scraped_at")
    prices = [dict(row) for row in cursor.fetchall()]

    cursor.execute("SELECT * FROM scraper_health ORDER BY run_at DESC")
    health = [dict(row) for row in cursor.fetchall()]

    conn.close()
    return prices, health


def build_html(prices, health):
    # Group by product_url since that's always consistent,
    # even when the scraper's product_name field is sometimes missing.
    grouped_by_url = {}
    for row in prices:
        url = row["product_url"]
        grouped_by_url.setdefault(url, []).append(row)

    products = {}
    for url, rows in grouped_by_url.items():
        # Prefer the longest/most complete name seen across all runs for this URL
        # (real scraped names are far longer than short URL-slug fallbacks like "P").
        best_name = max((r["product_name"] or "" for r in rows), key=len)
        if not best_name:
            best_name = "Unknown Product"
        products[best_name] = rows

    latest_snapshot = []
    for name, rows in products.items():
        latest_snapshot.append(rows[-1])
    latest_snapshot.sort(key=lambda r: r["price_value"])

    last_updated = prices[-1]["scraped_at"] if prices else "No data yet"
    total_scrapes = len(set(r["scraped_at"] for r in prices))
    success_count = len([h for h in health if h["status"] == "success"])
    failed_count = len([h for h in health if h["status"] == "failed"])

    products_json = json.dumps(products, ensure_ascii=False)

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>PriceGuard — Live Tracker</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0B0E11;
    --surface: #12161B;
    --surface-2: #1A1F26;
    --border: #232A33;
    --text: #E8EAED;
    --text-dim: #7C8894;
    --cyan: #4FD1C5;
    --amber: #F0A868;
    --red: #E5595E;
    --mono: 'IBM Plex Mono', 'Courier New', monospace;
    --sans: 'Inter', -apple-system, sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    padding: 40px 24px 80px;
    background-image:
      radial-gradient(circle at 15% 0%, rgba(79,209,197,0.06), transparent 40%),
      radial-gradient(circle at 85% 20%, rgba(240,168,104,0.05), transparent 40%);
  }}

  .wrap {{ max-width: 1100px; margin: 0 auto; }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 36px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 20px;
  }}

  .brand {{ display: flex; align-items: baseline; gap: 12px; }}

  .brand .dot {{
    width: 10px; height: 10px; border-radius: 50%;
    background: var(--cyan);
    box-shadow: 0 0 12px var(--cyan);
    animation: pulse 2s ease-in-out infinite;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.35; }}
  }}

  h1 {{
    font-family: var(--mono);
    font-size: 22px;
    font-weight: 600;
    letter-spacing: -0.02em;
  }}

  .tagline {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 4px;
  }}

  .last-updated {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    text-align: right;
  }}

  .metrics {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border);
    border: 1px solid var(--border);
    border-radius: 10px;
    overflow: hidden;
    margin-bottom: 40px;
  }}

  .metric {{
    background: var(--surface);
    padding: 20px 22px;
  }}

  .metric .label {{
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    margin-bottom: 8px;
  }}

  .metric .value {{
    font-family: var(--mono);
    font-size: 26px;
    font-weight: 600;
  }}

  .metric .value.cyan {{ color: var(--cyan); }}
  .metric .value.red {{ color: var(--red); }}

  section {{ margin-bottom: 40px; }}

  .section-title {{
    font-family: var(--mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    margin-bottom: 14px;
    display: flex;
    align-items: center;
    gap: 10px;
  }}

  .section-title::after {{
    content: '';
    flex: 1;
    height: 1px;
    background: var(--border);
  }}

  .card {{
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 24px;
  }}

  select {{
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 6px;
    padding: 8px 12px;
    font-family: var(--sans);
    font-size: 13px;
    margin-bottom: 20px;
    width: 100%;
    cursor: pointer;
  }}

  table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 13px;
  }}

  th {{
    text-align: left;
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.06em;
    color: var(--text-dim);
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
  }}

  td {{
    padding: 14px;
    border-bottom: 1px solid var(--border);
    vertical-align: top;
  }}

  tr:last-child td {{ border-bottom: none; }}

  .product-name {{ max-width: 340px; line-height: 1.4; }}

  .price {{
    font-family: var(--mono);
    font-weight: 600;
    color: var(--cyan);
  }}

  .discount {{
    color: var(--amber);
    font-size: 12px;
    font-family: var(--mono);
  }}

  .stock {{
    font-size: 11px;
    color: var(--text-dim);
  }}

  .log-entry {{
    display: flex;
    gap: 12px;
    font-family: var(--mono);
    font-size: 12px;
    padding: 10px 14px;
    border-bottom: 1px solid var(--border);
    align-items: baseline;
  }}

  .log-entry:last-child {{ border-bottom: none; }}

  .log-status {{
    width: 68px;
    flex-shrink: 0;
    font-weight: 600;
  }}

  .log-status.success {{ color: var(--cyan); }}
  .log-status.failed {{ color: var(--red); }}
  .log-status.healed {{ color: var(--amber); }}

  .log-time {{ color: var(--text-dim); width: 170px; flex-shrink: 0; }}
  .log-details {{ color: var(--text); opacity: 0.85; }}

  .empty {{
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 13px;
    padding: 20px 0;
  }}
</style>
</head>
<body>
<div class="wrap">

  <header>
    <div>
      <div class="brand">
        <div class="dot"></div>
        <h1>PriceGuard</h1>
      </div>
      <div class="tagline">self-healing scraper // laptop price tracker</div>
    </div>
    <div class="last-updated">
      LAST SYNC<br>{last_updated}
    </div>
  </header>

  <div class="metrics">
    <div class="metric">
      <div class="label">Products Tracked</div>
      <div class="value">{len(products)}</div>
    </div>
    <div class="metric">
      <div class="label">Total Scrape Runs</div>
      <div class="value">{total_scrapes}</div>
    </div>
    <div class="metric">
      <div class="label">Successful Runs</div>
      <div class="value cyan">{success_count}</div>
    </div>
    <div class="metric">
      <div class="label">Failed Runs</div>
      <div class="value red">{failed_count}</div>
    </div>
  </div>

  <section>
    <div class="section-title">Price History</div>
    <div class="card">
      <select id="productSelect" onchange="renderChart()"></select>
      <canvas id="priceChart" height="90"></canvas>
    </div>
  </section>

  <section>
    <div class="section-title">Current Snapshot</div>
    <div class="card" style="padding:0;">
      <table>
        <thead>
          <tr>
            <th>Product</th>
            <th>Price</th>
            <th>Discount</th>
            <th>Stock</th>
          </tr>
        </thead>
        <tbody id="snapshotBody"></tbody>
      </table>
    </div>
  </section>

  <section>
    <div class="section-title">Scraper Health Log</div>
    <div class="card" style="padding:0;">
      <div id="healthLog"></div>
    </div>
  </section>

</div>

<script>
const productsData = {products_json};
const healthData = {json.dumps(health, ensure_ascii=False)};
let chart = null;

function formatRupee(v) {{
  return '₹' + Number(v).toLocaleString('en-IN');
}}

function populateSelect() {{
  const sel = document.getElementById('productSelect');
  Object.keys(productsData).forEach(name => {{
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name.length > 70 ? name.slice(0, 70) + '…' : name;
    sel.appendChild(opt);
  }});
}}

function renderChart() {{
  const sel = document.getElementById('productSelect');
  const rows = productsData[sel.value] || [];
  const labels = rows.map(r => r.scraped_at.slice(0, 16).replace('T', ' '));
  const data = rows.map(r => r.price_value);

  if (chart) chart.destroy();
  const ctx = document.getElementById('priceChart').getContext('2d');
  chart = new Chart(ctx, {{
    type: 'line',
    data: {{
      labels: labels,
      datasets: [{{
        label: 'Price (₹)',
        data: data,
        borderColor: '#4FD1C5',
        backgroundColor: 'rgba(79,209,197,0.08)',
        borderWidth: 2,
        pointBackgroundColor: '#4FD1C5',
        pointRadius: 4,
        tension: 0.25,
        fill: true
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{ legend: {{ display: false }} }},
      scales: {{
        x: {{ ticks: {{ color: '#7C8894', font: {{ family: 'IBM Plex Mono', size: 10 }} }}, grid: {{ color: '#232A33' }} }},
        y: {{ ticks: {{ color: '#7C8894', font: {{ family: 'IBM Plex Mono', size: 10 }}, callback: v => formatRupee(v) }}, grid: {{ color: '#232A33' }} }}
      }}
    }}
  }});
}}

function renderSnapshot() {{
  const body = document.getElementById('snapshotBody');
  const latest = Object.values(productsData).map(rows => rows[rows.length - 1]);
  latest.sort((a, b) => a.price_value - b.price_value);

  if (latest.length === 0) {{
    body.innerHTML = '<tr><td colspan="4" class="empty">No data yet. Run pipeline.py to collect your first scrape.</td></tr>';
    return;
  }}

  body.innerHTML = latest.map(r => `
    <tr>
      <td class="product-name">${{r.product_name}}</td>
      <td class="price">${{formatRupee(r.price_value)}}</td>
      <td class="discount">${{r.discount || '—'}}</td>
      <td class="stock">${{r.stock_availability || '—'}}</td>
    </tr>
  `).join('');
}}

function renderHealth() {{
  const container = document.getElementById('healthLog');
  if (healthData.length === 0) {{
    container.innerHTML = '<div class="empty" style="padding:20px;">No health log entries yet.</div>';
    return;
  }}
  container.innerHTML = healthData.map(h => `
    <div class="log-entry">
      <span class="log-status ${{h.status}}">${{h.status.toUpperCase()}}</span>
      <span class="log-time">${{h.run_at.slice(0, 19).replace('T', ' ')}}</span>
      <span class="log-details">${{h.details || ''}}</span>
    </div>
  `).join('');
}}

populateSelect();
renderChart();
renderSnapshot();
renderHealth();
</script>

</body>
</html>
"""
    return html


def main():
    if not os.path.exists(DB_FILE):
        print(f"Database not found at {os.path.abspath(DB_FILE)}. Run pipeline.py first.")
        return

    prices, health = load_data()
    html = build_html(prices, health)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Dashboard generated: {os.path.abspath(OUTPUT_FILE)}")
    print("Open it in your browser to view.")


if __name__ == "__main__":
    main()
