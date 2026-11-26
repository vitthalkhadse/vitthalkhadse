#!/usr/bin/env python3
"""Generate the GitHub stats and top-language cards for the profile README.

Only public data is used, so the workflow's GITHUB_TOKEN is enough.
Usage: profile_stats.py <username> <output-dir>
Writes stats.svg, stats-dark.svg, top-langs.svg and top-langs-dark.svg.
"""

import json
import os
import sys
import urllib.request
from html import escape

THEMES = {
    "": {"text": "#2b2420", "muted": "#76675c", "accent": "#c4552a", "track": "#eadfd4"},
    "-dark": {"text": "#f3ebe3", "muted": "#b3a397", "accent": "#e07a4a", "track": "#3a302a"},
}
FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
EXCLUDED_LANGUAGES = {"HTML", "CSS", "SCSS", "Shell", "Makefile", "Dockerfile", "Batchfile", "PowerShell"}

QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    followers { totalCount }
    pullRequests { totalCount }
    issues { totalCount }
    contributionsCollection { totalCommitContributions }
    repositoriesContributedTo(
      contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, PULL_REQUEST_REVIEW]
      includeUserRepositories: false
    ) { totalCount }
    repositories(
      first: 100, after: $cursor, ownerAffiliations: OWNER, privacy: PUBLIC, isFork: false
    ) {
      pageInfo { hasNextPage endCursor }
      nodes {
        stargazerCount
        languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


def graphql(token, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": QUERY, "variables": variables}).encode(),
        headers={"Authorization": f"bearer {token}", "User-Agent": "profile-stats"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = json.load(resp)
    if body.get("errors"):
        raise SystemExit(f"GraphQL error: {body['errors']}")
    return body["data"]["user"]


def fetch(login, token):
    user, repos, cursor = None, [], None
    while True:
        page = graphql(token, {"login": login, "cursor": cursor})
        user = user or page
        repos += page["repositories"]["nodes"]
        info = page["repositories"]["pageInfo"]
        if not info["hasNextPage"]:
            break
        cursor = info["endCursor"]
    langs = {}
    for repo in repos:
        for edge in repo["languages"]["edges"]:
            name = edge["node"]["name"]
            if name in EXCLUDED_LANGUAGES:
                continue
            size, color = langs.get(name, (0, edge["node"]["color"]))
            langs[name] = (size + edge["size"], color or "#8b8b8b")
    stats = [
        ("Stars earned", sum(r["stargazerCount"] for r in repos)),
        ("Commits (last year)", user["contributionsCollection"]["totalCommitContributions"]),
        ("Pull requests", user["pullRequests"]["totalCount"]),
        ("Issues", user["issues"]["totalCount"]),
        ("Contributed to (last year)", user["repositoriesContributedTo"]["totalCount"]),
    ]
    top = sorted(langs.items(), key=lambda kv: kv[1][0], reverse=True)[:6]
    return stats, top


def svg(width, height, title, body):
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">'
        f"<title>{escape(title)}</title>{body}</svg>\n"
    )


def stats_card(stats, t):
    rows = []
    for i, (label, value) in enumerate(stats):
        y = 62 + i * 22
        rows.append(
            f'<circle cx="30" cy="{y - 4}" r="3" fill="{t["accent"]}"/>'
            f'<text x="42" y="{y}" fill="{t["muted"]}" font-size="13">{escape(label)}</text>'
            f'<text x="330" y="{y}" fill="{t["text"]}" font-size="13" font-weight="600" '
            f'text-anchor="end">{value:,}</text>'
        )
    body = (
        f'<g font-family="{FONT}">'
        f'<text x="24" y="32" fill="{t["accent"]}" font-size="16" font-weight="600">GitHub stats</text>'
        + "".join(rows)
        + "</g>"
    )
    return svg(356, 32 + 22 * len(stats) + 28, "GitHub stats", body)


def langs_card(top, t):
    total = sum(size for _, (size, _) in top) or 1
    bar_x, bar_w, x = 24, 292, 24.0
    segments = []
    for name, (size, color) in top:
        w = bar_w * size / total
        segments.append(f'<rect x="{x:.2f}" y="46" width="{w:.2f}" height="8" fill="{color}"/>')
        x += w
    items = []
    for i, (name, (size, color)) in enumerate(top):
        col, row = i % 2, i // 2
        ix, iy = 24 + col * 150, 82 + row * 24
        items.append(
            f'<circle cx="{ix + 5}" cy="{iy - 4}" r="5" fill="{color}"/>'
            f'<text x="{ix + 16}" y="{iy}" fill="{t["text"]}" font-size="13">{escape(name)} '
            f'<tspan fill="{t["muted"]}">{100 * size / total:.1f}%</tspan></text>'
        )
    body = (
        f'<defs><clipPath id="bar"><rect x="{bar_x}" y="46" width="{bar_w}" height="8" rx="4"/></clipPath></defs>'
        f'<g font-family="{FONT}">'
        f'<text x="24" y="32" fill="{t["accent"]}" font-size="16" font-weight="600">Top languages</text>'
        f'<rect x="{bar_x}" y="46" width="{bar_w}" height="8" rx="4" fill="{t["track"]}"/>'
        f'<g clip-path="url(#bar)">{"".join(segments)}</g>'
        + "".join(items)
        + "</g>"
    )
    return svg(340, 170, "Top languages", body)


def main():
    login, out = sys.argv[1], sys.argv[2]
    token = os.environ.get("GITHUB_TOKEN") or sys.exit("GITHUB_TOKEN is not set")
    stats, top = fetch(login, token)
    os.makedirs(out, exist_ok=True)
    for suffix, theme in THEMES.items():
        with open(os.path.join(out, f"stats{suffix}.svg"), "w") as f:
            f.write(stats_card(stats, theme))
        with open(os.path.join(out, f"top-langs{suffix}.svg"), "w") as f:
            f.write(langs_card(top, theme))
    print(stats, [(n, s) for n, (s, _) in top])


if __name__ == "__main__":
    main()