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
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PriceGuard — Live Tracker</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='20' fill='%230B0E11'/%3E%3Cpath d='M50 15 L80 28 L80 52 C80 72 68 85 50 90 C32 85 20 72 20 52 L20 28 Z' fill='none' stroke='%234FD1C5' stroke-width='6'/%3E%3Cpath d='M38 50 L47 60 L64 40' fill='none' stroke='%234FD1C5' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@500;600;700&family=JetBrains+Mono:wght@400;500;600&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.0/chart.umd.min.js"></script>
<style>
  :root {{
    --bg: #0A0D10;
    --surface: #12161B;
    --surface-2: #1A1F26;
    --border: #232A33;
    --border-soft: #1B2129;
    --text: #EDEFF2;
    --text-dim: #7C8894;
    --text-faint: #4B5560;
    --cyan: #4FD1C5;
    --cyan-dim: rgba(79,209,197,0.12);
    --amber: #F0A868;
    --red: #E5595E;
    --green: #6FCF97;
    --mono: 'JetBrains Mono', 'Courier New', monospace;
    --display: 'Space Grotesk', var(--sans);
    --sans: 'Inter', -apple-system, sans-serif;
  }}

  * {{ box-sizing: border-box; margin: 0; padding: 0; }}

  body {{
    background: var(--bg);
    color: var(--text);
    font-family: var(--sans);
    padding: 48px 28px 90px;
    background-image:
      radial-gradient(circle at 12% 0%, rgba(79,209,197,0.07), transparent 42%),
      radial-gradient(circle at 88% 15%, rgba(240,168,104,0.05), transparent 40%);
    -webkit-font-smoothing: antialiased;
  }}

  .wrap {{ max-width: 1120px; margin: 0 auto; }}

  header {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-bottom: 40px;
    border-bottom: 1px solid var(--border);
    padding-bottom: 22px;
    flex-wrap: wrap;
    gap: 16px;
  }}

  .brand {{ display: flex; align-items: center; gap: 12px; }}

  .brand .dot {{
    width: 9px; height: 9px; border-radius: 50%;
    background: var(--cyan);
    box-shadow: 0 0 14px var(--cyan);
    animation: pulse 2.2s ease-in-out infinite;
    flex-shrink: 0;
  }}

  @keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.3; }}
  }}

  h1 {{
    font-family: var(--display);
    font-size: 26px;
    font-weight: 700;
    letter-spacing: -0.02em;
  }}

  .live-badge {{
    font-family: var(--mono);
    font-size: 10px;
    font-weight: 500;
    letter-spacing: 0.08em;
    color: var(--cyan);
    background: var(--cyan-dim);
    border: 1px solid rgba(79,209,197,0.25);
    padding: 3px 8px;
    border-radius: 20px;
    margin-left: 4px;
  }}

  .tagline {{
    font-family: var(--mono);
    font-size: 12px;
    color: var(--text-dim);
    margin-top: 6px;
  }}

  .last-updated {{
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-dim);
    text-align: right;
    line-height: 1.6;
  }}

  .last-updated span {{ color: var(--text-faint); letter-spacing: 0.06em; }}

  .metrics {{
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: var(--border-soft);
    border: 1px solid var(--border-soft);
    border-radius: 12px;
    overflow: hidden;
    margin-bottom: 44px;
  }}

  .metric {{
    background: var(--surface);
    padding: 22px 24px;
    transition: background 0.2s ease;
  }}

  .metric:hover {{ background: var(--surface-2); }}

  .metric .label {{
    font-family: var(--mono);
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--text-dim);
    margin-bottom: 10px;
  }}

  .metric .value {{
    font-family: var(--display);
    font-size: 30px;
    font-weight: 700;
  }}

  .metric .value.cyan {{ color: var(--cyan); }}
  .metric .value.red {{ color: var(--red); }}

  section {{ margin-bottom: 44px; }}

  .section-title {{
    font-family: var(--mono);
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.1em;
    color: var(--text-dim);
    margin-bottom: 16px;
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
    border-radius: 12px;
    padding: 26px;
  }}

  select {{
    background: var(--surface-2);
    color: var(--text);
    border: 1px solid var(--border);
    border-radius: 8px;
    padding: 10px 14px;
    font-family: var(--sans);
    font-size: 13px;
    margin-bottom: 22px;
    width: 100%;
    cursor: pointer;
    transition: border-color 0.15s ease;
  }}

  select:hover {{ border-color: var(--cyan); }}

  .snapshot-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
    gap: 14px;
  }}

  .product-card {{
    background: var(--surface-2);
    border: 1px solid var(--border);
    border-radius: 10px;
    padding: 18px 20px;
    transition: border-color 0.15s ease, transform 0.15s ease;
  }}

  .product-card:hover {{
    border-color: rgba(79,209,197,0.35);
    transform: translateY(-1px);
  }}

  .product-card .name {{
    font-size: 13px;
    line-height: 1.4;
    color: var(--text);
    margin-bottom: 12px;
    min-height: 36px;
    display: -webkit-box;
    -webkit-line-clamp: 2;
    -webkit-box-orient: vertical;
    overflow: hidden;
  }}

  .product-card .price-row {{
    display: flex;
    align-items: baseline;
    justify-content: space-between;
    margin-bottom: 10px;
  }}

  .product-card .price {{
    font-family: var(--mono);
    font-weight: 600;
    font-size: 19px;
    color: var(--cyan);
  }}

  .trend {{
    font-family: var(--mono);
    font-size: 11px;
    padding: 2px 7px;
    border-radius: 5px;
    font-weight: 500;
  }}

  .trend.up {{ color: var(--red); background: rgba(229,89,94,0.1); }}
  .trend.down {{ color: var(--green); background: rgba(111,207,151,0.1); }}
  .trend.flat {{ color: var(--text-faint); background: rgba(124,136,148,0.08); }}

  .product-card .meta-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    font-size: 11px;
  }}

  .discount-tag {{
    color: var(--amber);
    font-family: var(--mono);
    font-size: 11px;
  }}

  .stock-tag {{
    font-size: 10px;
    color: var(--text-faint);
    text-transform: uppercase;
    letter-spacing: 0.04em;
  }}

  .log-entry {{
    display: flex;
    gap: 12px;
    font-family: var(--mono);
    font-size: 12px;
    padding: 11px 16px;
    border-bottom: 1px solid var(--border-soft);
    align-items: baseline;
  }}

  .log-entry:last-child {{ border-bottom: none; }}

  .log-status {{
    width: 70px;
    flex-shrink: 0;
    font-weight: 600;
    display: flex;
    align-items: center;
    gap: 6px;
  }}

  .log-status::before {{
    content: '';
    width: 6px; height: 6px; border-radius: 50%;
    flex-shrink: 0;
  }}

  .log-status.success {{ color: var(--cyan); }}
  .log-status.success::before {{ background: var(--cyan); }}
  .log-status.failed {{ color: var(--red); }}
  .log-status.failed::before {{ background: var(--red); }}
  .log-status.healed {{ color: var(--amber); }}
  .log-status.healed::before {{ background: var(--amber); }}

  .log-time {{ color: var(--text-dim); width: 175px; flex-shrink: 0; }}
  .log-details {{ color: var(--text); opacity: 0.8; }}

  .empty {{
    color: var(--text-dim);
    font-family: var(--mono);
    font-size: 13px;
    padding: 24px 0;
    text-align: center;
  }}

  footer {{
    margin-top: 60px;
    padding-top: 20px;
    border-top: 1px solid var(--border-soft);
    font-family: var(--mono);
    font-size: 11px;
    color: var(--text-faint);
    text-align: center;
  }}

  @media (max-width: 720px) {{
    body {{ padding: 28px 16px 60px; }}
    header {{ flex-direction: column; align-items: flex-start; }}
    .last-updated {{ text-align: left; }}
    .metrics {{ grid-template-columns: repeat(2, 1fr); }}
    .card {{ padding: 18px; }}
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
        <span class="live-badge">LIVE</span>
      </div>
      <div class="tagline">self-healing scraper // laptop price tracker</div>
    </div>
    <div class="last-updated">
      <span>LAST SYNC</span><br>{last_updated}
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
    <div class="snapshot-grid" id="snapshotGrid"></div>
  </section>

  <section>
    <div class="section-title">Scraper Health Log</div>
    <div class="card" style="padding:0;">
      <div id="healthLog"></div>
    </div>
  </section>

  <footer>PriceGuard — built with Bright Data Scraper Studio for the Scrape-Verse Hackathon</footer>

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
        pointBorderColor: '#0A0D10',
        pointBorderWidth: 2,
        pointRadius: 5,
        pointHoverRadius: 7,
        tension: 0.3,
        fill: true
      }}]
    }},
    options: {{
      responsive: true,
      plugins: {{
        legend: {{ display: false }},
        tooltip: {{
          backgroundColor: '#1A1F26',
          borderColor: '#232A33',
          borderWidth: 1,
          titleFont: {{ family: 'JetBrains Mono', size: 11 }},
          bodyFont: {{ family: 'JetBrains Mono', size: 12 }},
          padding: 10,
          callbacks: {{ label: (ctx) => formatRupee(ctx.parsed.y) }}
        }}
      }},
      scales: {{
        x: {{ ticks: {{ color: '#7C8894', font: {{ family: 'JetBrains Mono', size: 10 }} }}, grid: {{ color: '#1B2129' }} }},
        y: {{ ticks: {{ color: '#7C8894', font: {{ family: 'JetBrains Mono', size: 10 }}, callback: v => formatRupee(v) }}, grid: {{ color: '#1B2129' }} }}
      }}
    }}
  }});
}}

function renderSnapshot() {{
  const grid = document.getElementById('snapshotGrid');
  const entries = Object.entries(productsData);

  if (entries.length === 0) {{
    grid.innerHTML = '<div class="empty">No data yet. Run pipeline.py to collect your first scrape.</div>';
    return;
  }}

  const cards = entries.map(([name, rows]) => {{
    const latest = rows[rows.length - 1];
    const prev = rows.length > 1 ? rows[rows.length - 2] : null;

    let trendHtml = '<span class="trend flat">—</span>';
    if (prev) {{
      const diff = latest.price_value - prev.price_value;
      if (diff > 0) trendHtml = `<span class="trend up">▲ ${{formatRupee(Math.abs(diff))}}</span>`;
      else if (diff < 0) trendHtml = `<span class="trend down">▼ ${{formatRupee(Math.abs(diff))}}</span>`;
    }}

    return `
      <div class="product-card">
        <div class="name">${{name}}</div>
        <div class="price-row">
          <span class="price">${{formatRupee(latest.price_value)}}</span>
          ${{trendHtml}}
        </div>
        <div class="meta-row">
          <span class="discount-tag">${{latest.discount || 'No discount'}}</span>
          <span class="stock-tag">${{latest.stock_availability || '—'}}</span>
        </div>
      </div>
    `;
  }}).join('');

  grid.innerHTML = cards;
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
try {{ renderChart(); }} catch (e) {{ console.error('Chart failed to render:', e); }}
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
