#!/usr/bin/env python3
"""Generate the "GitHub at a glance" card: total commits and total repositories.

Outputs assets/stats/summary.svg (dark), assets/stats/summary-light.svg (light) and STATS.md.
Standard library only. Set GITHUB_TOKEN to raise the API rate limit (automatic in GitHub Actions).
On any error the script exits without touching the existing files.

Definitions
  - Total commits: commits authored by the account in public repositories, as counted by the
    GitHub commit search API (query "author:<user>").
  - Total repositories: public repositories owned by the account, forks excluded.
"""
import datetime as dt
import html
import json
import os
import sys
import urllib.request

USER = os.environ.get("GH_USER", "keitaflora01")
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "assets", "stats")
FONT = "'Segoe UI',-apple-system,BlinkMacSystemFont,'Helvetica Neue',Arial,sans-serif"

THEMES = {
    "dark": dict(bg0="#0B2348", bg1="#173D70", ink="#FFFFFF", muted="#9FB3CF", accent="#8FD3B0",
                 tile="#FFFFFF", icon_bg="#278653", icon="#FFFFFF", border=None),
    "light": dict(bg0="#FFFFFF", bg1="#EEF5F1", ink="#0B2348", muted="#5A6B85", accent="#1F7A4A",
                  tile="#0B2348", icon_bg="#278653", icon="#FFFFFF", border="#D6E0EA"),
}


def api(path):
    req = urllib.request.Request("https://api.github.com" + path,
                                 headers={"User-Agent": "profile-stats-generator", "Accept": "application/vnd.github+json"})
    if os.environ.get("GITHUB_TOKEN"):
        req.add_header("Authorization", f"Bearer {os.environ['GITHUB_TOKEN']}")
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def get_repos():
    repos, page = [], 1
    while True:
        batch = api(f"/users/{USER}/repos?type=owner&per_page=100&page={page}")
        repos += batch
        if len(batch) < 100:
            return [r for r in repos if not r["fork"]]
        page += 1


def get_commit_total():
    total = api(f"/search/commits?q=author:{USER}&per_page=1").get("total_count")
    if not isinstance(total, int):
        raise RuntimeError("commit search returned no total")
    return total


# Simple 24x24 glyphs drawn in the icon colour
COMMIT_ICON = ('<line x1="2" y1="12" x2="7.5" y2="12" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
               '<line x1="16.5" y1="12" x2="22" y2="12" stroke="{c}" stroke-width="2.4" stroke-linecap="round"/>'
               '<circle cx="12" cy="12" r="4.5" fill="none" stroke="{c}" stroke-width="2.4"/>')
REPO_ICON = ('<path d="M5 4.5A2.5 2.5 0 0 1 7.5 2H19v16H7.5A2.5 2.5 0 0 0 5 20.5z" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>'
             '<path d="M5 20.5A2.5 2.5 0 0 0 7.5 23H19v-5" fill="none" stroke="{c}" stroke-width="2.2" stroke-linejoin="round"/>'
             '<line x1="9" y1="7" x2="15" y2="7" stroke="{c}" stroke-width="2" stroke-linecap="round"/>')


def tile(x, y, w, h, t, icon, value, label, note):
    return (f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="16" fill="{t["tile"]}" fill-opacity=".05" stroke="{t["tile"]}" stroke-opacity=".12"/>'
            f'<rect x="{x+28}" y="{y+(h-64)/2}" width="64" height="64" rx="16" fill="{t["icon_bg"]}"/>'
            f'<g transform="translate({x+28+14},{y+(h-64)/2+14}) scale(1.5)">{icon.format(c=t["icon"])}</g>'
            f'<text x="{x+118}" y="{y+h/2+6}" font-size="50" font-weight="800" fill="{t["ink"]}">{value:,}</text>'
            f'<text x="{x+118}" y="{y+h/2+34}" font-size="15" font-weight="600" fill="{t["ink"]}">{html.escape(label)}</text>'
            f'<text x="{x+w-24}" y="{y+30}" text-anchor="end" font-size="12" fill="{t["muted"]}">{html.escape(note)}</text>')


def summary_svg(commits, repos, asof, t):
    w, h = 1000, 250
    tw, th, ty = (w - 72 - 24) / 2, 150, 72
    border = f'<rect x=".5" y=".5" width="{w-1}" height="{h-1}" rx="16" fill="none" stroke="{t["border"]}"/>' if t["border"] else ""
    label = f"As of {asof}: {commits} total commits and {repos} public repositories (forks excluded)."
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{html.escape(label)}">
<defs><linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="{t["bg0"]}"/><stop offset="1" stop-color="{t["bg1"]}"/></linearGradient>
<clipPath id="c"><rect width="{w}" height="{h}" rx="16"/></clipPath></defs>
<style>text{{font-family:{FONT}}}</style>
<g clip-path="url(#c)"><rect width="{w}" height="{h}" fill="url(#bg)"/><rect width="6" height="{h}" fill="#278653"/></g>
<text x="36" y="44" font-size="12" font-weight="700" letter-spacing="2" fill="{t["accent"]}">GITHUB AT A GLANCE</text>
<text x="{w-36}" y="44" text-anchor="end" font-size="12.5" fill="{t["muted"]}">As of {asof}</text>
{tile(36, ty, tw, th, t, COMMIT_ICON, commits, "Total commits", "public repositories")}
{tile(36 + tw + 24, ty, tw, th, t, REPO_ICON, repos, "Total repositories", "public · forks excluded")}
{border}
</svg>'''


def main():
    repos = get_repos()
    commits = get_commit_total()
    asof = dt.date.today().strftime("%d %b %Y")
    os.makedirs(OUT, exist_ok=True)
    for theme, suffix in (("dark", ""), ("light", "-light")):
        with open(os.path.join(OUT, f"summary{suffix}.svg"), "w", encoding="utf-8") as f:
            f.write(summary_svg(commits, len(repos), asof, THEMES[theme]))
    lines = [f"# GitHub at a glance — {USER}", "", f"*As of {asof}. Updated daily by "
             "[`.github/workflows/stats.yml`](.github/workflows/stats.yml).*", "",
             "| Metric | Value |", "|:--|--:|", f"| Total commits | {commits:,} |", f"| Total repositories | {len(repos)} |", "",
             "## Definitions", "",
             "- **Total commits**: commits authored by the account in public repositories, as counted by GitHub commit search.",
             "- **Total repositories**: public repositories owned by the account, forks excluded.", "",
             "## Repositories", "", "| Repository | Created |", "|:--|:--|"]
    lines += [f"| [{r['name']}]({r['html_url']}) | {r['created_at'][:10]} |"
              for r in sorted(repos, key=lambda r: r["created_at"], reverse=True)]
    with open(os.path.join(ROOT, "STATS.md"), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    print(f"OK: {commits} commits, {len(repos)} repositories")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)
