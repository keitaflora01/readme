#!/usr/bin/env python3
"""Generate the GitHub profile dashboards (SVG) and their text snapshot (STATS.md).

Only the Python standard library is used. Data sources (public, no scraping of private data):
  - REST API  /users/<user>/repos            -> original (non-fork) public repositories
  - Public contribution calendar HTML        -> daily contribution counts for the last year

Set GITHUB_TOKEN to raise the REST rate limit (done automatically in GitHub Actions).
If any source fails to parse, the script exits with an error and leaves existing files untouched.
"""
import datetime as dt
import html
import json
import os
import re
import sys
import urllib.request
from collections import Counter, OrderedDict

USER = os.environ.get("GH_USER", "keitaflora01")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "stats")

# Brand tokens per theme. "dark" -> <name>.svg, "light" -> <name>-light.svg (README picks via <picture>).
# HEAT is sequential, one hue: level 0 (none) -> 4 (most); the most active cell is the most prominent.
THEMES = {
    "dark": dict(BG0="#0B2348", BG1="#173D70", INK="#FFFFFF", INK2="#D7E3F4", MUTED="#9FB3CF", ACCENT="#8FD3B0",
                 BAR="#3FAE6E", NEUTRAL="#5B6F8C", SURF="#FFFFFF", BORDER=None,
                 HEAT=["#2A4C7F", "#1B5E45", "#23824F", "#3FAE6E", "#7FDCA4"]),
    "light": dict(BG0="#FFFFFF", BG1="#EEF5F1", INK="#0B2348", INK2="#2F4565", MUTED="#5A6B85", ACCENT="#1F7A4A",
                  BAR="#278653", NEUTRAL="#A3B1C4", SURF="#0B2348", BORDER="#D6E0EA",
                  HEAT=["#E4EAF1", "#BFE3CF", "#7CC29C", "#3A9A66", "#1E6B45"]),
}


def set_theme(name):
    globals().update(THEMES[name])


set_theme("dark")
FONT = "'Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"


def fetch(url, accept="application/vnd.github+json"):
    req = urllib.request.Request(url, headers={"User-Agent": "profile-stats-generator", "Accept": accept})
    token = os.environ.get("GITHUB_TOKEN")
    if token and "api.github.com" in url:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8")


def get_repos():
    repos, page = [], 1
    while True:
        batch = json.loads(fetch(f"https://api.github.com/users/{USER}/repos?type=owner&per_page=100&page={page}"))
        if not isinstance(batch, list):
            raise RuntimeError(f"Unexpected repos response: {batch}")
        repos += batch
        if len(batch) < 100:
            return [r for r in repos if not r["fork"]]
        page += 1


def get_contributions():
    page = fetch(f"https://github.com/users/{USER}/contributions", accept="text/html")
    total_m = re.search(r'id="js-contribution-activity-description"[^>]*>\s*([\d,]+)\s*contribution', page)
    cells = dict(re.findall(r'data-date="(\d{4}-\d{2}-\d{2})"\s+id="(contribution-day-component-[\d-]+)"', page))
    cells = {cid: d for d, cid in cells.items()}
    tips = re.findall(r'for="(contribution-day-component-[\d-]+)"[^>]*>([^<]*)</tool-tip>', page)
    days = {}
    for cid, text in tips:
        if cid not in cells:
            continue
        m = re.match(r"\s*(No|[\d,]+) contribution", text)
        if not m:
            continue
        days[cells[cid]] = 0 if m.group(1) == "No" else int(m.group(1).replace(",", ""))
    lv = {}
    for tag in re.findall(r"<td[^>]*ContributionCalendar-day[^>]*>", page):
        d = re.search(r'data-date="([\d-]+)"', tag)
        l = re.search(r'data-level="(\d)"', tag)
        if d and l:
            lv[d.group(1)] = int(l.group(1))
    if not total_m or len(days) < 300:
        raise RuntimeError(f"Could not parse contribution calendar (days parsed: {len(days)})")
    days = OrderedDict(sorted(days.items()))
    return int(total_m.group(1).replace(",", "")), days, lv


def streaks(days):
    longest = run = 0
    for c in days.values():
        run = run + 1 if c > 0 else 0
        longest = max(longest, run)
    vals = list(days.values())
    if vals and vals[-1] == 0:  # today not counted yet: streak may end yesterday
        vals = vals[:-1]
    current = 0
    for c in reversed(vals):
        if c == 0:
            break
        current += 1
    return current, longest


def esc(s):
    return html.escape(str(s), quote=True)


def card(w, h, label, body):
    border = f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="16" fill="none" stroke="{BORDER}"/>' if BORDER else ''
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{esc(label)}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{BG0}"/><stop offset="1" stop-color="{BG1}"/></linearGradient>
<clipPath id="c"><rect width="{w}" height="{h}" rx="16"/></clipPath></defs>
<style>text{{font-family:{FONT}}}</style>
<g clip-path="url(#c)"><rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="6" height="{h}" fill="#278653"/></g>
{body}
{border}
</svg>'''


def kpi(x, y, w, value, label):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="78" rx="12" fill="{SURF}" fill-opacity=".05" stroke="{SURF}" stroke-opacity=".12"/>'
            f'<text x="{x+18}" y="{y+40}" font-size="28" font-weight="800" fill="{INK}">{esc(value)}</text>'
            f'<text x="{x+18}" y="{y+62}" font-size="12.5" fill="{MUTED}">{esc(label)}</text>')


def header(eyebrow, title, asof, w):
    return (f'<text x="36" y="42" font-size="12" font-weight="700" letter-spacing="2" fill="{ACCENT}">{esc(eyebrow)}</text>'
            f'<text x="36" y="72" font-size="24" font-weight="800" fill="{INK}">{esc(title)}</text>'
            f'<text x="{w-32}" y="42" text-anchor="end" font-size="12.5" fill="{MUTED}">As of {esc(asof)}</text>')


def repos_svg(repos, asof):
    w = 1000
    counts = Counter(r["language"] or "Not detected" for r in repos)
    detected = sorted(((k, v) for k, v in counts.items() if k != "Not detected"), key=lambda kv: (-kv[1], kv[0]))
    rows = detected + ([("Not detected", counts["Not detected"])] if counts.get("Not detected") else [])
    newest = max(repos, key=lambda r: r["created_at"])
    tiles_y = 100
    body = header("REPOSITORY SNAPSHOT", "Original public repositories", asof, w)
    tw = (w - 72 - 3 * 16) / 4
    for i, (v, l) in enumerate([(len(repos), "original public repos"),
                                (len(detected), "primary languages"),
                                (sum(r["stargazers_count"] for r in repos), "stars received"),
                                (dt.date.fromisoformat(newest["created_at"][:10]).strftime("%d %b %Y"), f"latest: {newest['name']}")]):
        body += kpi(36 + i * (tw + 16), tiles_y, tw, v, l)
    by = tiles_y + 120
    body += f'<text x="36" y="{by}" font-size="14" font-weight="700" fill="{INK2}">Primary language by repository</text>'
    maxv = max(v for _, v in rows)
    lx, bx, bw_max, rh = 36, 190, w - 190 - 90, 34
    for i, (name, v) in enumerate(rows):
        y = by + 22 + i * rh
        bw = max(6, bw_max * v / maxv)
        col = NEUTRAL if name == "Not detected" else BAR
        body += (f'<text x="{lx}" y="{y+17}" font-size="13.5" fill="{INK2}">{esc(name)}</text>'
                 f'<rect x="{bx}" y="{y+4}" width="{bw:.1f}" height="18" rx="4" fill="{col}"/>'
                 f'<text x="{bx+bw+10:.1f}" y="{y+18}" font-size="13.5" font-weight="700" fill="{INK}">{v}</text>')
    fy = by + 22 + len(rows) * rh + 22
    body += (f'<text x="36" y="{fy}" font-size="12" fill="{MUTED}">Forks excluded. Bars count repositories by their primary language, not proficiency. '
             f'“Not detected” = no code GitHub can classify.</text>')
    h = fy + 26
    label = f"Original public repositories as of {asof}: {len(repos)}. " + ", ".join(f"{k}: {v}" for k, v in rows) + ". Forks excluded."
    return card(w, h, label, body), rows


def contrib_svg(total, days, lv, asof):
    w = 1000
    cur, longest = streaks(days)
    active = sum(1 for c in days.values() if c)
    best_day, best = max(days.items(), key=lambda kv: kv[1])
    body = header("CONTRIBUTIONS", "Total contributions · last 12 months", asof, w)
    tw = (w - 72 - 4 * 16) / 5
    for i, (v, l) in enumerate([(f"{total:,}", "total contributions"),
                                (active, "active days"),
                                (f"{longest} d", "longest streak"),
                                (f"{cur} d", "current streak"),
                                (best, f"best day · {dt.date.fromisoformat(best_day).strftime('%d %b %Y')}")]):
        body += kpi(36 + i * (tw + 16), 100, tw, v, l)

    # Heatmap (weeks as columns, Sunday first like GitHub)
    dates = list(days.keys())
    first = dt.date.fromisoformat(dates[0])
    start = first - dt.timedelta(days=(first.weekday() + 1) % 7)
    cell, gap = 13, 3
    gx, gy = 72, 236
    month_seen = set()
    for d_s, c in days.items():
        d = dt.date.fromisoformat(d_s)
        col = (d - start).days // 7
        row = (d.weekday() + 1) % 7
        level = lv.get(d_s, 0 if c == 0 else 2)
        x, y = gx + col * (cell + gap), gy + row * (cell + gap)
        body += f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{HEAT[level]}"/>'
        key = (d.year, d.month)
        if d.day <= 7 and row == 0 and key not in month_seen:
            month_seen.add(key)
            body += f'<text x="{x}" y="{gy-8}" font-size="11.5" fill="{MUTED}">{d.strftime("%b")}</text>'
    for row, name in ((1, "Mon"), (3, "Wed"), (5, "Fri")):
        body += f'<text x="36" y="{gy + row*(cell+gap) + 11}" font-size="11" fill="{MUTED}">{name}</text>'
    ly = gy + 7 * (cell + gap) + 18
    lx = w - 36 - 5 * (cell + gap) - 70
    body += f'<text x="{lx-8}" y="{ly+11}" text-anchor="end" font-size="11.5" fill="{MUTED}">Less</text>'
    for i, ccol in enumerate(HEAT):
        body += f'<rect x="{lx + i*(cell+gap)}" y="{ly}" width="{cell}" height="{cell}" rx="3" fill="{ccol}"/>'
    body += f'<text x="{lx + 5*(cell+gap) + 5}" y="{ly+11}" font-size="11.5" fill="{MUTED}">More</text>'

    # Monthly totals (single series, labels on max and latest only)
    months = OrderedDict()
    for d_s, c in days.items():
        months[d_s[:7]] = months.get(d_s[:7], 0) + c
    my = ly + 52
    body += f'<text x="36" y="{my}" font-size="14" font-weight="700" fill="{INK2}">Contributions per month</text>'
    keys = list(months.keys())
    mx = max(months.values()) or 1
    ch, base = 110, my + 26 + 110
    slot = (w - 72) / len(keys)
    bw = min(44, slot - 10)
    body += f'<line x1="36" x2="{w-36}" y1="{base}" y2="{base}" stroke="{SURF}" stroke-opacity=".18"/>'
    for i, k in enumerate(keys):
        v = months[k]
        bh = ch * v / mx
        x = 36 + i * slot + (slot - bw) / 2
        if bh > 0:
            r = min(4, bh)
            body += (f'<path d="M{x:.1f},{base} V{base-bh+r:.1f} Q{x:.1f},{base-bh:.1f} {x+r:.1f},{base-bh:.1f} '
                     f'H{x+bw-r:.1f} Q{x+bw:.1f},{base-bh:.1f} {x+bw:.1f},{base-bh+r:.1f} V{base} Z" fill="{BAR}"/>')
        if v == mx or i == len(keys) - 1:
            body += f'<text x="{x+bw/2:.1f}" y="{base-bh-7:.1f}" text-anchor="middle" font-size="12" font-weight="700" fill="{INK}">{v}</text>'
        lbl = dt.date.fromisoformat(k + "-01").strftime("%b")
        body += f'<text x="{x+bw/2:.1f}" y="{base+18}" text-anchor="middle" font-size="11.5" fill="{MUTED}">{lbl}</text>'
    fy = base + 46
    body += f'<text x="36" y="{fy}" font-size="12" fill="{MUTED}">Public contribution calendar: commits, pull requests, issues and reviews counted by GitHub over the last 12 months.</text>'
    h = fy + 26
    label = (f"{total} contributions in the last 12 months as of {asof}. {active} active days, longest streak {longest} days, "
             f"current streak {cur} days, best day {best} contributions on {best_day}.")
    return card(w, h, label, body), dict(total=total, active=active, longest=longest, current=cur,
                                         best=best, best_day=best_day, months=months)


def stats_md(repos, rows, c, asof):
    lines = [f"# GitHub snapshot — {USER}", "", f"*As of {asof}. Regenerated automatically every day by "
             "[`.github/workflows/stats.yml`](.github/workflows/stats.yml).*", "",
             "## Definitions", "",
             "- **Original public repositories**: public repositories owned by the account, **forks excluded**.",
             "- **Primary language**: the language GitHub detects as dominant in a repository. "
             "Bars count *repositories*, not lines of code and not proficiency. "
             "*Not detected* means GitHub found no classifiable code (e.g. README-only repositories).",
             "- **Contributions**: what GitHub counts on the public contribution calendar over the last 12 months "
             "(commits to default branches, pull requests, issues, reviews).",
             "- **Streak**: consecutive days with at least one contribution. The current streak ignores today if nothing has been pushed yet.",
             "", "## Repositories by primary language", "", "| Language | Repositories |", "|:--|--:|"]
    lines += [f"| {k} | {v} |" for k, v in rows]
    lines += [f"| **Total** | **{len(repos)}** |", "", "## All original public repositories", "",
              "| Repository | Primary language | Created | Stars |", "|:--|:--|:--|--:|"]
    for r in sorted(repos, key=lambda r: r["created_at"], reverse=True):
        desc = f" — {r['description']}" if r.get("description") else ""
        lines.append(f"| [{r['name']}]({r['html_url']}){desc} | {r['language'] or 'Not detected'} | {r['created_at'][:10]} | {r['stargazers_count']} |")
    lines += ["", "## Contributions (last 12 months)", "", "| Metric | Value |", "|:--|--:|",
              f"| Total contributions | {c['total']:,} |", f"| Active days | {c['active']} |",
              f"| Longest streak | {c['longest']} days |", f"| Current streak | {c['current']} days |",
              f"| Best day | {c['best']} ({c['best_day']}) |", "", "### Per month", "", "| Month | Contributions |", "|:--|--:|"]
    lines += [f"| {k} | {v} |" for k, v in c["months"].items()]
    return "\n".join(lines) + "\n"


def main():
    repos = get_repos()
    total, days, lv = get_contributions()
    asof = dt.date.today().strftime("%d %b %Y")
    os.makedirs(OUT, exist_ok=True)
    for theme, suffix in (("dark", ""), ("light", "-light")):
        set_theme(theme)
        svg_r, rows = repos_svg(repos, asof)
        svg_c, c = contrib_svg(total, days, lv, asof)
        for name, data in ((f"repositories{suffix}.svg", svg_r), (f"contributions{suffix}.svg", svg_c)):
            with open(os.path.join(OUT, name), "w", encoding="utf-8") as f:
                f.write(data)
    with open(os.path.join(ROOT, "STATS.md"), "w", encoding="utf-8") as f:
        f.write(stats_md(repos, rows, c, asof))
    print(f"OK: {len(repos)} repos, {total} contributions, {len(days)} days")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # keep previous files on any failure
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
