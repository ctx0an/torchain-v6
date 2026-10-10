#!/usr/bin/env python3
"""Track GitHub release download counts and generate an SVG chart."""
import csv
import datetime
import json
import os
import sys
import urllib.request

REPO_OWNER = "ctx0an"
REPO_NAME = "torchain-v6"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
STATS_DIR = os.path.join(REPO_ROOT, "stats")
CSV_PATH = os.path.join(STATS_DIR, "downloads.csv")
SVG_PATH = os.path.join(STATS_DIR, "downloads_chart.svg")

def get_downloads():
    token = os.environ.get("GITHUB_TOKEN")
    headers = {"User-Agent": "curl/8.0"}
    if token:
        headers["Authorization"] = f"token {token}"
    
    url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req) as resp:
            releases = json.loads(resp.read().decode())
    except Exception as e:
        print(f"Error fetching releases: {e}", file=sys.stderr)
        return None

    total = 0
    breakdown = {
        "torchain.exe": 0,
        "torchain-portable.zip": 0,
        "Torchain-x86_64.AppImage": 0,
        "app-debug.apk": 0
    }

    for r in releases:
        for a in r.get("assets", []):
            count = a.get("download_count", 0)
            total += count
            name = a.get("name")
            if name in breakdown:
                breakdown[name] += count

    return total, breakdown

def update_csv(today_str, total, breakdown):
    os.makedirs(STATS_DIR, exist_ok=True)
    rows = []
    fieldnames = ["date", "total", "torchain.exe", "torchain-portable.zip", "Torchain-x86_64.AppImage", "app-debug.apk"]

    if os.path.isfile(CSV_PATH):
        with open(CSV_PATH, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for r in reader:
                if r.get("date") != today_str:
                    rows.append(r)

    rows.append({
        "date": today_str,
        "total": str(total),
        "torchain.exe": str(breakdown.get("torchain.exe", 0)),
        "torchain-portable.zip": str(breakdown.get("torchain-portable.zip", 0)),
        "Torchain-x86_64.AppImage": str(breakdown.get("Torchain-x86_64.AppImage", 0)),
        "app-debug.apk": str(breakdown.get("app-debug.apk", 0))
    })

    with open(CSV_PATH, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    return rows

def generate_svg(rows):
    width = 800
    height = 360
    margin_top = 70
    margin_bottom = 60
    margin_left = 65
    margin_right = 35

    plot_width = width - margin_left - margin_right
    plot_height = height - margin_top - margin_bottom

    # Extract data
    dates = [r["date"] for r in rows]
    totals = [int(r.get("total", 0)) for r in rows]

    max_val = max(totals) if totals else 10
    max_y = max(int(max_val * 1.25) + 5, 20)

    # Calculate coordinates
    n = len(rows)
    points = []
    for i, val in enumerate(totals):
        x = margin_left if n == 1 else margin_left + (i / (n - 1)) * plot_width
        y = margin_top + plot_height - (val / max_y) * plot_height
        points.append((x, y, val, dates[i]))

    # Gridlines & Y-ticks
    grid_lines = []
    y_ticks_count = 5
    for i in range(y_ticks_count + 1):
        tick_val = int((max_y / y_ticks_count) * i)
        y = margin_top + plot_height - (tick_val / max_y) * plot_height
        grid_lines.append(
            f'<line x1="{margin_left}" y1="{y:.1f}" x2="{width - margin_right}" y2="{y:.1f}" stroke="#1e293b" stroke-width="1" stroke-dasharray="3,3"/>'
            f'<text x="{margin_left - 12}" y="{y + 4:.1f}" fill="#64748b" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11" text-anchor="end">{tick_val}</text>'
        )

    # Path construction
    if n == 1:
        x, y, val, dt = points[0]
        line_path = f"M {margin_left} {y:.1f} L {width - margin_right} {y:.1f}"
        area_path = f"M {margin_left} {margin_top + plot_height} L {margin_left} {y:.1f} L {width - margin_right} {y:.1f} L {width - margin_right} {margin_top + plot_height} Z"
    else:
        line_path = "M " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in points)
        area_path = f"M {points[0][0]:.1f} {margin_top + plot_height} L " + " L ".join(f"{p[0]:.1f} {p[1]:.1f}" for p in points) + f" L {points[-1][0]:.1f} {margin_top + plot_height} Z"

    # X-axis ticks (sample up to 6 labels)
    x_ticks = []
    step = max(1, n // 6)
    indices = list(range(0, n, step))
    if (n - 1) not in indices:
        indices.append(n - 1)
    for idx in indices:
        p = points[idx]
        x_ticks.append(
            f'<text x="{p[0]:.1f}" y="{height - margin_bottom + 22}" fill="#64748b" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11" text-anchor="middle">{p[3]}</text>'
        )

    # Data markers
    circles = []
    for p in points:
        circles.append(
            f'<circle cx="{p[0]:.1f}" cy="{p[1]:.1f}" r="4" fill="#00f2fe" stroke="#0f172a" stroke-width="2"/>'
            f'<text x="{p[0]:.1f}" y="{p[1] - 10:.1f}" fill="#38bdf8" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11" font-weight="600" text-anchor="middle">{p[2]}</text>'
        )

    latest_total = totals[-1] if totals else 0
    latest_breakdown = rows[-1] if rows else {}

    svg_content = f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {height}" width="100%" height="100%">
  <defs>
    <linearGradient id="areaGradient" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#00f2fe" stop-opacity="0.3"/>
      <stop offset="100%" stop-color="#00f2fe" stop-opacity="0.0"/>
    </linearGradient>
    <linearGradient id="lineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#00f2fe"/>
    </linearGradient>
  </defs>

  <!-- Background card -->
  <rect width="{width}" height="{height}" rx="12" fill="#0b0f19" stroke="#1e293b" stroke-width="1"/>

  <!-- Title & Total Badge -->
  <text x="{margin_left}" y="36" fill="#f8fafc" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="16" font-weight="700">Release Downloads History</text>
  <text x="{margin_left}" y="54" fill="#64748b" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="12">Total Cumulative Downloads: <tspan fill="#38bdf8" font-weight="bold">{latest_total}</tspan></text>

  <!-- Legend -->
  <g transform="translate({width - margin_right - 440}, 24)">
    <circle cx="0" cy="8" r="4" fill="#38bdf8"/>
    <text x="10" y="12" fill="#94a3b8" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11">.exe: {latest_breakdown.get('torchain.exe', 0)}</text>
    
    <circle cx="95" cy="8" r="4" fill="#a78bfa"/>
    <text x="105" y="12" fill="#94a3b8" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11">.zip: {latest_breakdown.get('torchain-portable.zip', 0)}</text>

    <circle cx="190" cy="8" r="4" fill="#4ade80"/>
    <text x="200" y="12" fill="#94a3b8" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11">.apk: {latest_breakdown.get('app-debug.apk', 0)}</text>

    <circle cx="285" cy="8" r="4" fill="#fb923c"/>
    <text x="295" y="12" fill="#94a3b8" font-family="-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif" font-size="11">AppImage: {latest_breakdown.get('Torchain-x86_64.AppImage', 0)}</text>
  </g>

  <!-- Grid -->
  {"".join(grid_lines)}

  <!-- Area fill & Line path -->
  <path d="{area_path}" fill="url(#areaGradient)"/>
  <path d="{line_path}" fill="none" stroke="url(#lineGradient)" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"/>

  <!-- Markers & X-ticks -->
  {"".join(circles)}
  {"".join(x_ticks)}
</svg>"""

    with open(SVG_PATH, "w", encoding="utf-8") as f:
        f.write(svg_content)
    print(f"Generated {SVG_PATH}")

def main():
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    data = get_downloads()
    if not data:
        print("Failed to get download stats")
        return 1
    total, breakdown = data
    print(f"Today: {today}, Total Downloads: {total}")
    rows = update_csv(today, total, breakdown)
    generate_svg(rows)
    return 0

if __name__ == "__main__":
    sys.exit(main())
