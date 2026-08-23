import sqlite3
import json
import os
from datetime import datetime

DB_FILE = "prices.db"
OUTPUT_FILE = "index.html"


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


def build_chart_svg(rows):
    """Builds a stepped polyline chart (matching the reference's style) from
    real price rows. Returns dict with polygon points, polyline points,
    y-axis labels, and x-axis labels."""
    if not rows:
        return {
            "polygon": "0,100 100,100",
            "polyline": "0,50 100,50",
            "y_labels": ["-", "-", "-", "-"],
            "x_labels": ["-"],
            "current_x": 100, "current_y": 50,
        }

    values = [r["price_value"] for r in rows]
    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmin -= 1
        vmax += 1
    vrange = vmax - vmin

    n = len(rows)
    step = 100 / n if n > 0 else 100

    # Build stepped points: for each value, draw a flat segment across its
    # time slot, then step up/down to the next value (matches reference SVG).
    pts = []
    for i, v in enumerate(values):
        y = 90 - ((v - vmin) / vrange) * 80  # invert + pad within 0-90 range
        x_start = i * step
        x_end = (i + 1) * step
        pts.append((x_start, y))
        pts.append((x_end, y))

    polyline = " ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
    polygon = polyline + f" 100,100 0,100"

    # Y-axis labels: 4 evenly spaced price points, high to low
    y_labels = [
        f"₹{vmax:,.0f}",
        f"₹{(vmin + vrange * 0.66):,.0f}",
        f"₹{(vmin + vrange * 0.33):,.0f}",
        f"₹{vmin:,.0f}",
    ]

    # X-axis labels: real dates from the scrape timestamps
    x_labels = []
    for i, r in enumerate(rows):
        dt = r["scraped_at"][5:10]  # MM-DD
        x_labels.append("Now" if i == n - 1 else dt)

    current_x, current_y = pts[-1]
    return {
        "polygon": polygon,
        "polyline": polyline,
        "y_labels": y_labels,
        "x_labels": x_labels,
        "current_x": current_x,
        "current_y": current_y,
    }


def build_html(prices, health):
    grouped_by_url = {}
    for row in prices:
        url = row["product_url"]
        grouped_by_url.setdefault(url, []).append(row)

    products = {}
    for url, rows in grouped_by_url.items():
        best_name = max((r["product_name"] or "" for r in rows), key=len)
        if not best_name:
            best_name = "Unknown Product"
        products[best_name] = rows

    last_updated = prices[-1]["scraped_at"] if prices else "No data yet"
    total_scrapes = len(set(r["scraped_at"] for r in prices))
    success_count = len([h for h in health if h["status"] == "success"])
    failed_count = len([h for h in health if h["status"] == "failed"])
    total_runs = len(health)
    success_pct = round((success_count / total_runs) * 100, 1) if total_runs else 0.0
    failed_pct = round((failed_count / total_runs) * 100, 1) if total_runs else 0.0

    # Pick hero product: biggest price drop, fallback to first product
    hero_name = None
    hero_rows = []
    hero_drop = -1
    for name, rows in products.items():
        if len(rows) > 1:
            drop = rows[-2]["price_value"] - rows[-1]["price_value"]
            if drop > hero_drop:
                hero_drop = drop
                hero_name = name
                hero_rows = rows
    if hero_name is None and products:
        hero_name = next(iter(products))
        hero_rows = products[hero_name]

    hero_latest = hero_rows[-1] if hero_rows else None
    hero_prev = hero_rows[-2] if len(hero_rows) > 1 else None
    hero_diff = (hero_latest["price_value"] - hero_prev["price_value"]) if (hero_latest and hero_prev) else 0

    chart = build_chart_svg(hero_rows)

    products_json = json.dumps(products, ensure_ascii=False)
    health_json = json.dumps(health, ensure_ascii=False)

    hero_name_display = (hero_name[:40] + "…") if hero_name and len(hero_name) > 40 else (hero_name or "No data")
    hero_name_full = hero_name or ""
    hero_url = hero_latest["product_url"] if hero_latest else "#"
    hero_price = f"₹{hero_latest['price_value']:,.0f}" if hero_latest else "—"
    hero_discount = hero_latest["discount"] if hero_latest and hero_latest.get("discount") else "No discount data"
    hero_stock = hero_latest["stock_availability"] if hero_latest else "—"

    trend_icon = "arrow_downward" if hero_diff < 0 else ("arrow_upward" if hero_diff > 0 else "remove")
    trend_color = "text-secondary-container" if hero_diff <= 0 else "text-error"
    trend_text = f"₹{abs(hero_diff):,.0f}" if hero_diff != 0 else "—"

    html = f"""<!DOCTYPE html>
<html class="dark" lang="en">
<head>
<meta charset="utf-8"/>
<meta content="width=device-width, initial-scale=1.0" name="viewport"/>
<title>PriceGuard Dashboard</title>
<link rel="icon" href="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'%3E%3Crect width='100' height='100' rx='22' fill='%2310141a'/%3E%3Cpath d='M50 15 L80 28 L80 52 C80 72 68 85 50 90 C32 85 20 72 20 52 L20 28 Z' fill='none' stroke='%2300f0ff' stroke-width='6'/%3E%3Cpath d='M38 50 L47 60 L64 40' fill='none' stroke='%2300f0ff' stroke-width='6' stroke-linecap='round' stroke-linejoin='round'/%3E%3C/svg%3E">
<script src="https://cdn.tailwindcss.com?plugins=forms,container-queries"></script>
<link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;600;700&family=JetBrains+Mono:wght@400;500;700&family=Hanken+Grotesk:wght@400;500&display=swap" rel="stylesheet"/>
<link href="https://fonts.googleapis.com/css2?family=Material+Symbols+Outlined:wght,FILL@100..700,0..1&display=swap" rel="stylesheet"/>
<script id="tailwind-config">
        tailwind.config = {{
            darkMode: "class",
            theme: {{
                extend: {{
                    "colors": {{
                        "primary-fixed": "#7df4ff",
                        "inverse-primary": "#006970",
                        "error-container": "#93000a",
                        "on-secondary-container": "#3d6200",
                        "tertiary": "#fff3f2",
                        "surface-container": "#1c2026",
                        "on-surface": "#dfe2eb",
                        "on-secondary": "#203600",
                        "on-secondary-fixed": "#112000",
                        "outline": "#849495",
                        "tertiary-fixed": "#ffdad7",
                        "surface-container-low": "#181c22",
                        "tertiary-container": "#ffceca",
                        "secondary": "#bcff5f",
                        "secondary-container": "#95e400",
                        "on-tertiary": "#68000b",
                        "primary": "#dbfcff",
                        "secondary-fixed": "#a8f928",
                        "on-background": "#dfe2eb",
                        "on-surface-variant": "#b9cacb",
                        "on-primary": "#00363a",
                        "outline-variant": "#3b494b",
                        "error": "#ffb4ab",
                        "primary-container": "#00f0ff",
                        "on-primary-fixed": "#002022",
                        "on-tertiary-fixed": "#410004",
                        "on-error": "#690005",
                        "surface-tint": "#00dbe9",
                        "surface-container-highest": "#31353c",
                        "primary-fixed-dim": "#00dbe9",
                        "on-primary-fixed-variant": "#004f54",
                        "tertiary-fixed-dim": "#ffb3ae",
                        "on-tertiary-fixed-variant": "#930014",
                        "inverse-surface": "#dfe2eb",
                        "secondary-fixed-dim": "#8fdb00",
                        "surface-container-high": "#262a31",
                        "surface-bright": "#353940",
                        "surface-container-lowest": "#0a0e14",
                        "on-error-container": "#ffdad6",
                        "on-primary-container": "#006970",
                        "background": "#10141a",
                        "surface-dim": "#10141a",
                        "on-tertiary-container": "#bb1824",
                        "on-secondary-fixed-variant": "#314f00",
                        "surface-variant": "#31353c",
                        "inverse-on-surface": "#2d3137",
                        "surface": "#10141a"
                    }},
                    "borderRadius": {{
                        "DEFAULT": "0.125rem",
                        "lg": "0.25rem",
                        "xl": "0.5rem",
                        "full": "0.75rem"
                    }},
                    "spacing": {{
                        "base": "4px",
                        "xs": "8px",
                        "margin": "20px",
                        "sm": "12px",
                        "lg": "24px",
                        "xl": "32px",
                        "gutter": "16px",
                        "md": "16px"
                    }},
                    "fontFamily": {{
                        "headline-sm": ["Geist"],
                        "body-lg": ["Hanken Grotesk"],
                        "label-xs": ["JetBrains Mono"],
                        "data-md": ["JetBrains Mono"],
                        "body-md": ["Hanken Grotesk"],
                        "display-lg": ["Geist"],
                        "data-lg": ["JetBrains Mono"],
                        "headline-md": ["Geist"]
                    }},
                    "fontSize": {{
                        "headline-sm": ["20px", {{ "lineHeight": "28px", "fontWeight": "600" }}],
                        "body-lg": ["16px", {{ "lineHeight": "24px", "fontWeight": "400" }}],
                        "label-xs": ["10px", {{ "lineHeight": "12px", "fontWeight": "700" }}],
                        "data-md": ["14px", {{ "lineHeight": "18px", "fontWeight": "500" }}],
                        "body-md": ["14px", {{ "lineHeight": "20px", "fontWeight": "400" }}],
                        "display-lg": ["32px", {{ "lineHeight": "40px", "letterSpacing": "-0.02em", "fontWeight": "700" }}],
                        "data-lg": ["20px", {{ "lineHeight": "24px", "letterSpacing": "0.05em", "fontWeight": "700" }}],
                        "headline-md": ["24px", {{ "lineHeight": "32px", "letterSpacing": "-0.01em", "fontWeight": "600" }}]
                    }}
                }}
            }}
        }}
    </script>
<style>
        body {{
            background-color: #10141a;
            color: #dfe2eb;
        }}

        .clean-card {{
            background-color: #1c2026;
            border: 1px solid #3b494b;
            border-radius: 0.5rem;
        }}

        ::-webkit-scrollbar {{ width: 6px; height: 6px; }}
        ::-webkit-scrollbar-track {{ background: #10141a; }}
        ::-webkit-scrollbar-thumb {{ background: #3b494b; border-radius: 3px; }}
        ::-webkit-scrollbar-thumb:hover {{ background: #849495; }}

        .page {{ display: none; }}
        .page.active {{ display: block; }}

        .nav-link.active {{
            background-color: #262a31;
            color: #dfe2eb;
            border: 1px solid #3b494b;
        }}
        .nav-link:not(.active) {{ color: #b9cacb; }}
        .nav-link:not(.active):hover {{ color: #dfe2eb; background-color: #1c2026; }}

        .log-row {{ border-bottom: 1px solid #3b494b; }}
        .log-row:last-child {{ border-bottom: none; }}

        .product-row {{ transition: border-color 0.15s ease; }}
        .product-row:hover {{ border-color: #00dbe9; }}

        /* Mobile: hide desktop sidebar, show a simple top bar with a select-based nav */
        @media (max-width: 767px) {{
            .mobile-nav-select {{ display: block; }}
        }}
        @media (min-width: 768px) {{
            .mobile-nav-select {{ display: none; }}
        }}
    </style>
</head>
<body class="font-body-lg antialiased min-h-screen flex relative overflow-hidden bg-background">

<!-- Side Navigation Shell (desktop) -->
<nav class="hidden md:flex flex-col w-64 bg-surface-container-lowest border-r border-outline-variant z-10 h-screen py-lg shrink-0">
  <div class="px-lg pb-xl border-b border-outline-variant flex items-center gap-xs">
    <span class="material-symbols-outlined text-primary-container text-display-lg">sensors</span>
    <div>
      <h1 class="font-headline-md text-headline-md font-bold tracking-tighter text-on-surface">PriceGuard</h1>
      <p class="font-label-xs text-label-xs text-on-surface-variant tracking-widest uppercase">Dashboard</p>
    </div>
  </div>
  <div class="flex-1 overflow-y-auto px-md flex flex-col gap-sm py-md">
    <a class="nav-link active flex items-center gap-md px-4 py-3 rounded-lg transition-colors" href="javascript:void(0)" onclick="showPage('overview', this)">
      <span class="material-symbols-outlined" style="font-variation-settings: 'FILL' 1;">monitoring</span>
      <span class="font-data-md text-data-md">Dashboard</span>
    </a>
    <a class="nav-link flex items-center gap-md px-4 py-3 rounded-lg transition-colors" href="javascript:void(0)" onclick="showPage('history', this)">
      <span class="material-symbols-outlined">timeline</span>
      <span class="font-data-md text-data-md">History</span>
    </a>
    <a class="nav-link flex items-center gap-md px-4 py-3 rounded-lg transition-colors" href="javascript:void(0)" onclick="showPage('logs', this)">
      <span class="material-symbols-outlined">terminal</span>
      <span class="font-data-md text-data-md">Logs</span>
    </a>
    <a class="nav-link flex items-center gap-md px-4 py-3 rounded-lg transition-colors" href="javascript:void(0)" onclick="showPage('snapshots', this)">
      <span class="material-symbols-outlined">insert_chart</span>
      <span class="font-data-md text-data-md">Snapshots</span>
    </a>
  </div>
  <div class="px-md mt-auto pt-lg border-t border-outline-variant">
    <button onclick="location.reload()" class="w-full py-2 bg-surface-container border border-outline-variant text-on-surface font-data-md text-data-md rounded-lg hover:bg-surface-variant transition-colors flex items-center justify-center gap-xs">
      <span class="material-symbols-outlined text-[18px]">sync</span>
      RE-SYNC ALL
    </button>
  </div>
</nav>

<!-- Main Content Area -->
<main class="flex-1 min-h-screen overflow-y-auto relative z-10 px-xl pt-lg pb-xl bg-background">

  <!-- Mobile-only compact header + page selector -->
  <div class="mobile-nav-select mb-lg">
    <div class="flex items-center gap-xs mb-md">
      <span class="material-symbols-outlined text-primary-container">sensors</span>
      <h1 class="font-headline-md text-headline-md font-bold tracking-tighter text-on-surface">PriceGuard</h1>
    </div>
    <select onchange="showPage(this.value, null)" class="w-full bg-surface-container border border-outline-variant text-on-surface font-data-md text-data-md rounded-lg px-3 py-2.5">
      <option value="overview">Dashboard</option>
      <option value="history">History</option>
      <option value="logs">Logs</option>
      <option value="snapshots">Snapshots</option>
    </select>
  </div>

  <!-- ===================== PAGE: OVERVIEW ===================== -->
  <div id="page-overview" class="page active">

    <header class="flex justify-between items-end mb-xl border-b border-outline-variant pb-md flex-wrap gap-md">
      <div>
        <h2 class="font-display-lg text-display-lg text-on-surface mb-1">Overview</h2>
        <div class="flex items-center gap-2">
          <span class="w-2 h-2 rounded-full bg-secondary-container"></span>
          <span class="font-label-xs text-label-xs text-on-surface-variant uppercase tracking-wider">System Online — Last sync {last_updated[:16].replace('T', ' ')}</span>
        </div>
      </div>
      <div class="flex items-center gap-md">
        <div class="relative">
          <span class="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-outline">search</span>
          <input id="searchBox" oninput="filterSnapshots()" class="bg-surface-container border border-outline-variant text-on-surface font-body-md text-body-md rounded-lg pl-10 pr-4 py-2 focus:outline-none focus:border-primary-container focus:ring-1 focus:ring-primary-container transition-all w-64" placeholder="Search targets..." type="text"/>
        </div>
        <button onclick="location.reload()" class="p-2 rounded-lg bg-surface-container hover:bg-surface-variant text-on-surface transition-colors border border-outline-variant flex items-center justify-center">
          <span class="material-symbols-outlined">settings</span>
        </button>
      </div>
    </header>

    <!-- Metrics Grid -->
    <div class="grid grid-cols-1 md:grid-cols-4 gap-gutter mb-xl">
      <div class="clean-card p-md flex flex-col justify-between min-h-[128px]">
        <div class="flex justify-between items-start">
          <p class="font-label-xs text-label-xs text-on-surface-variant tracking-wider uppercase">Products Tracked</p>
          <span class="material-symbols-outlined text-outline">inventory_2</span>
        </div>
        <div>
          <span class="font-data-lg text-display-lg text-on-surface block mb-1">{len(products)}</span>
          <span class="font-label-xs text-label-xs text-secondary-container flex items-center gap-1"><span class="material-symbols-outlined text-[12px]">trending_up</span> tracked</span>
        </div>
      </div>
      <div class="clean-card p-md flex flex-col justify-between min-h-[128px]">
        <div class="flex justify-between items-start">
          <p class="font-label-xs text-label-xs text-on-surface-variant tracking-wider uppercase">Total Runs</p>
          <span class="material-symbols-outlined text-outline">speed</span>
        </div>
        <div>
          <span class="font-data-lg text-display-lg text-on-surface block mb-1">{total_scrapes}</span>
          <span class="font-label-xs text-label-xs text-on-surface-variant">Scrape sessions</span>
        </div>
      </div>
      <div class="clean-card p-md flex flex-col justify-between min-h-[128px]">
        <div class="flex justify-between items-start">
          <p class="font-label-xs text-label-xs text-on-surface-variant tracking-wider uppercase">Successful</p>
          <span class="material-symbols-outlined text-outline">check_circle</span>
        </div>
        <div>
          <span class="font-data-lg text-display-lg text-on-surface block mb-1">{success_pct}%</span>
        </div>
      </div>
      <div class="clean-card p-md flex flex-col justify-between min-h-[128px]">
        <div class="flex justify-between items-start">
          <p class="font-label-xs text-label-xs text-on-surface-variant tracking-wider uppercase">Failed</p>
          <span class="material-symbols-outlined text-outline">warning</span>
        </div>
        <div>
          <span class="font-data-lg text-display-lg text-error block mb-1">{failed_pct}%</span>
          <span class="font-label-xs text-label-xs text-on-surface-variant">{failed_count} error(s)</span>
        </div>
      </div>
    </div>

    <!-- Main Focus: Live Tracking Card -->
    <div class="clean-card p-lg flex flex-col xl:flex-row gap-xl">
      <div class="xl:w-1/3 flex flex-col justify-between">
        <div>
          <div class="flex justify-between items-center mb-md">
            <span class="px-2 py-1 bg-surface-container-high text-on-surface-variant font-label-xs text-label-xs rounded border border-outline-variant uppercase tracking-widest">LIVE TRACKING</span>
            <span class="font-label-xs text-label-xs text-on-surface-variant">CROMA</span>
          </div>
          <h3 class="font-headline-md text-headline-md text-on-surface mb-xs">{hero_name_display}</h3>
          <p class="font-body-md text-body-md text-on-surface-variant mb-lg">{hero_stock}</p>
          <div class="p-md bg-surface-container-low rounded-lg border border-outline-variant mb-lg">
            <div class="flex items-baseline gap-sm mb-1 flex-wrap">
              <span class="font-data-lg text-display-lg text-on-surface">{hero_price}</span>
              <span class="font-data-md text-data-md {trend_color} flex items-center">
                <span class="material-symbols-outlined text-[16px]">{trend_icon}</span>
                {trend_text}
              </span>
            </div>
            <p class="font-label-xs text-label-xs text-on-surface-variant">{hero_discount}</p>
          </div>
        </div>
        <div class="flex gap-sm mt-auto">
          <a href="{hero_url}" target="_blank" class="flex-1 py-2 bg-primary-container text-on-primary-container font-data-md text-data-md rounded-lg hover:bg-primary transition-colors flex justify-center items-center gap-xs">
            <span class="material-symbols-outlined text-[18px]">shopping_cart</span>
            VIEW ON CROMA
          </a>
          <button onclick="showPage('history', document.querySelector('[onclick*=history]'))" class="px-4 py-2 bg-surface-container border border-outline-variant text-on-surface font-data-md text-data-md rounded-lg hover:bg-surface-variant transition-colors flex justify-center items-center">
            <span class="material-symbols-outlined text-[18px]">history</span>
          </button>
        </div>
      </div>

      <div class="xl:w-2/3 bg-surface-container-low rounded-lg border border-outline-variant relative overflow-hidden h-[300px] xl:h-auto flex flex-col p-md">
        <div class="flex justify-between items-center mb-md z-10 border-b border-outline-variant pb-sm">
          <span class="font-label-xs text-label-xs text-on-surface-variant uppercase tracking-wider">Price History — {hero_name_display}</span>
          <div class="flex gap-2">
            <button class="px-2 py-1 text-label-xs font-data-md bg-surface-container-high text-on-surface rounded border border-outline-variant">ALL</button>
          </div>
        </div>
        <div class="flex-1 relative w-full h-full">
          <div class="absolute inset-0 flex flex-col justify-between opacity-20 z-0 py-4">
            <div class="w-full border-t border-outline-variant"></div>
            <div class="w-full border-t border-outline-variant"></div>
            <div class="w-full border-t border-outline-variant"></div>
            <div class="w-full border-t border-outline-variant"></div>
          </div>
          <div class="absolute left-0 top-0 bottom-0 flex flex-col justify-between py-2 z-10 pointer-events-none">
            <span class="font-label-xs text-label-xs text-on-surface-variant">{chart['y_labels'][0]}</span>
            <span class="font-label-xs text-label-xs text-on-surface-variant">{chart['y_labels'][1]}</span>
            <span class="font-label-xs text-label-xs text-on-surface-variant">{chart['y_labels'][2]}</span>
            <span class="font-label-xs text-label-xs text-on-surface-variant">{chart['y_labels'][3]}</span>
          </div>
          <div class="absolute bottom-0 left-14 right-0 flex justify-between z-10 pointer-events-none px-4">
            {''.join(f'<span class="font-label-xs text-label-xs {"text-on-surface" if l == "Now" else "text-on-surface-variant"}">{l}</span>' for l in chart['x_labels'])}
          </div>
          <svg class="absolute inset-0 w-full h-full z-10 pl-14 pb-6 pt-2" preserveAspectRatio="none" viewBox="0 0 100 100">
            <defs>
              <linearGradient id="chartGradient" x1="0" x2="0" y1="0" y2="1">
                <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.15"></stop>
                <stop offset="100%" stop-color="#00f0ff" stop-opacity="0"></stop>
              </linearGradient>
            </defs>
            <polygon fill="url(#chartGradient)" points="{chart['polygon']}"></polygon>
            <polyline fill="none" points="{chart['polyline']}" stroke="#00dbe9" stroke-width="1.5" vector-effect="non-scaling-stroke"></polyline>
            <circle cx="{chart['current_x']}" cy="{chart['current_y']}" fill="#00f0ff" r="2.5"></circle>
          </svg>
        </div>
      </div>
    </div>
  </div>

  <!-- ===================== PAGE: HISTORY ===================== -->
  <div id="page-history" class="page">
    <header class="mb-xl border-b border-outline-variant pb-md">
      <h2 class="font-display-lg text-display-lg text-on-surface mb-1">Price History</h2>
      <p class="font-label-xs text-label-xs text-on-surface-variant uppercase tracking-wider">Full history per product</p>
    </header>
    <select id="historySelect" onchange="renderHistoryChart()" class="w-full md:max-w-sm bg-surface-container border border-outline-variant text-on-surface font-data-md text-data-md rounded-lg px-3 py-2.5 mb-lg"></select>
    <div class="clean-card p-lg h-[400px] relative">
      <svg id="historySvg" class="w-full h-full" preserveAspectRatio="none" viewBox="0 0 100 100">
        <defs>
          <linearGradient id="histGradient" x1="0" x2="0" y1="0" y2="1">
            <stop offset="0%" stop-color="#00f0ff" stop-opacity="0.15"></stop>
            <stop offset="100%" stop-color="#00f0ff" stop-opacity="0"></stop>
          </linearGradient>
        </defs>
        <polygon id="histPolygon" fill="url(#histGradient)" points=""></polygon>
        <polyline id="histPolyline" fill="none" points="" stroke="#00dbe9" stroke-width="1.5" vector-effect="non-scaling-stroke"></polyline>
      </svg>
    </div>
  </div>

  <!-- ===================== PAGE: LOGS ===================== -->
  <div id="page-logs" class="page">
    <header class="mb-xl border-b border-outline-variant pb-md">
      <h2 class="font-display-lg text-display-lg text-on-surface mb-1">Scraper Health Log</h2>
      <p class="font-label-xs text-label-xs text-on-surface-variant uppercase tracking-wider">Every run — success, failure, or self-healed recovery</p>
    </header>
    <div class="clean-card overflow-hidden" id="healthLog"></div>
  </div>

  <!-- ===================== PAGE: SNAPSHOTS ===================== -->
  <div id="page-snapshots" class="page">
    <header class="mb-xl border-b border-outline-variant pb-md">
      <h2 class="font-display-lg text-display-lg text-on-surface mb-1">Current Snapshot</h2>
      <p class="font-label-xs text-label-xs text-on-surface-variant uppercase tracking-wider">Latest price per tracked product</p>
    </header>
    <div class="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-gutter" id="snapshotGrid"></div>
  </div>

</main>

<script>
const productsData = {products_json};
const healthData = {health_json};

function formatRupee(v) {{ return '₹' + Number(v).toLocaleString('en-IN'); }}

function showPage(name, el) {{
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + name).classList.add('active');
  document.querySelectorAll('.nav-link').forEach(n => n.classList.remove('active'));
  if (el) el.classList.add('active');
  if (name === 'history') renderHistoryChart();
}}

function populateHistorySelect() {{
  const sel = document.getElementById('historySelect');
  Object.keys(productsData).forEach(name => {{
    const opt = document.createElement('option');
    opt.value = name;
    opt.textContent = name.length > 70 ? name.slice(0, 70) + '…' : name;
    sel.appendChild(opt);
  }});
}}

function renderHistoryChart() {{
  const sel = document.getElementById('historySelect');
  const rows = productsData[sel.value] || [];
  if (rows.length === 0) return;

  const values = rows.map(r => r.price_value);
  const vmin = Math.min(...values);
  const vmax = Math.max(...values) === vmin ? vmin + 1 : Math.max(...values);
  const range = vmax - vmin;
  const n = rows.length;
  const step = 100 / n;

  let pts = [];
  values.forEach((v, i) => {{
    const y = 90 - ((v - vmin) / range) * 80;
    pts.push([i * step, y]);
    pts.push([(i + 1) * step, y]);
  }});

  const polyline = pts.map(p => p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
  const polygon = polyline + ' 100,100 0,100';

  document.getElementById('histPolyline').setAttribute('points', polyline);
  document.getElementById('histPolygon').setAttribute('points', polygon);
}}

function renderSnapshots(filter) {{
  const grid = document.getElementById('snapshotGrid');
  let entries = Object.entries(productsData);
  if (filter) {{
    const f = filter.toLowerCase();
    entries = entries.filter(([name]) => name.toLowerCase().includes(f));
  }}

  if (entries.length === 0) {{
    grid.innerHTML = '<div class="font-label-xs text-label-xs text-on-surface-variant text-center py-10 col-span-full">No matching products.</div>';
    return;
  }}

  grid.innerHTML = entries.map(([name, rows]) => {{
    const latest = rows[rows.length - 1];
    const prev = rows.length > 1 ? rows[rows.length - 2] : null;
    let trendHtml = '<span class="font-label-xs text-label-xs text-on-surface-variant">—</span>';
    if (prev) {{
      const diff = latest.price_value - prev.price_value;
      if (diff > 0) trendHtml = `<span class="font-data-md text-data-md text-error flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">arrow_upward</span>${{formatRupee(Math.abs(diff))}}</span>`;
      else if (diff < 0) trendHtml = `<span class="font-data-md text-data-md text-secondary-container flex items-center gap-1"><span class="material-symbols-outlined text-[14px]">arrow_downward</span>${{formatRupee(Math.abs(diff))}}</span>`;
    }}
    return `
      <a href="${{latest.product_url}}" target="_blank" class="product-row clean-card p-md flex flex-col gap-2 block">
        <div class="font-body-md text-body-md text-on-surface leading-snug">${{name}}</div>
        <div class="flex items-baseline justify-between">
          <span class="font-data-lg text-headline-sm text-primary-container">${{formatRupee(latest.price_value)}}</span>
          ${{trendHtml}}
        </div>
        <div class="flex items-center justify-between">
          <span class="font-label-xs text-label-xs text-on-surface-variant">${{latest.discount || 'No discount'}}</span>
          <span class="font-label-xs text-label-xs text-outline uppercase">${{latest.stock_availability || '—'}}</span>
        </div>
      </a>
    `;
  }}).join('');
}}

function filterSnapshots() {{
  const val = document.getElementById('searchBox').value;
  renderSnapshots(val);
}}

function renderHealth() {{
  const log = document.getElementById('healthLog');
  if (healthData.length === 0) {{
    log.innerHTML = '<div class="font-label-xs text-label-xs text-on-surface-variant text-center py-10">No health log entries yet.</div>';
    return;
  }}
  const colorFor = (s) => s === 'success' ? 'text-primary-container' : (s === 'failed' ? 'text-error' : 'text-secondary-container');
  log.innerHTML = healthData.map(h => `
    <div class="log-row flex items-center gap-4 px-md py-3 font-data-md text-data-md">
      <span class="${{colorFor(h.status)}} font-bold w-20 flex-shrink-0 text-[12px]">${{h.status.toUpperCase()}}</span>
      <span class="text-on-surface-variant w-40 flex-shrink-0 text-[12px]">${{h.run_at.slice(0,19).replace('T',' ')}}</span>
      <span class="text-on-surface-variant/80 flex-1 truncate text-[12px]">${{h.details || ''}}</span>
    </div>
  `).join('');
}}

populateHistorySelect();
renderSnapshots();
renderHealth();
</script>

</body></html>
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
