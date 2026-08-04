#!/usr/bin/env python3
"""Render a neofetch-style info card as an SVG whose lines fade in one by one.

Everything except the public repo count is hand-written below; edit FIELDS to
change what the card says.

    python scripts/gen_card.py --user mmelika
"""

import argparse
import os
from pathlib import Path

import requests

API = "https://api.github.com/users/{user}"

# label, value. A value of None is filled in live from the GitHub API.
FIELDS: list[tuple[str, str | None]] = [
    ("Role", "Student @ Cal Poly SLO"),
    ("Building", "MemBridge — shared memory for AI coding agents"),
    ("Stack", "Node · Electron · React · Supabase"),
    ("Location", "Los Angeles"),
    ("Repos", None),
]

BG = "#0d1117"
FG = "#c9d1d9"
ACCENT = "#39d353"
DIM = "#8b949e"

FONT = 13
LINE_H = 24
PAD = 22
LABEL_W = 96
WIDTH = 620

# Same green ramp as the contribution graph, so the two panels feel related.
SWATCHES = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353", "#c9d1d9"]

LINE_STAGGER = 0.11
LINE_DUR = 0.45


def repo_count(user: str) -> str:
    """Public repo count, or a dash if GitHub is unreachable."""
    headers = {"Accept": "application/vnd.github+json"}
    # Actions hands us a token; using it just avoids the anonymous rate limit.
    if token := os.environ.get("GITHUB_TOKEN"):
        headers["Authorization"] = f"Bearer {token}"
    try:
        resp = requests.get(API.format(user=user), headers=headers, timeout=20)
        resp.raise_for_status()
        return f"{resp.json()['public_repos']} public"
    except (requests.RequestException, KeyError, ValueError) as exc:
        print(f"warning: could not read repo count ({exc}); leaving it blank")
        return "—"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def build_svg(user: str, fields: list[tuple[str, str]]) -> str:
    height = PAD * 2 + LINE_H * (len(fields) + 3) + 24

    rows = []
    n = 0

    def line(content: str) -> None:
        nonlocal n
        y = PAD + FONT + n * LINE_H
        rows.append(f'<g class="l" style="animation-delay:{n * LINE_STAGGER:.2f}s">'
                    f'{content.format(y=y)}</g>')
        n += 1

    line(f'<text class="hdr" x="{PAD}" y="{{y}}">marco<tspan class="dim">@</tspan>github</text>')
    line(f'<text class="rule" x="{PAD}" y="{{y}}">{"─" * 34}</text>')

    for label, value in fields:
        line(
            f'<text class="key" x="{PAD}" y="{{y}}">{esc(label)}</text>'
            f'<text class="val" x="{PAD + LABEL_W}" y="{{y}}">{esc(value)}</text>'
        )

    sw = "".join(
        f'<rect x="{PAD + i * 26}" y="{{y}}" width="20" height="10" rx="2" fill="{c}"/>'
        for i, c in enumerate(SWATCHES)
    )
    line(sw)

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}" role="img" aria-label="Profile info card for {user}">
<style>
text {{
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: {FONT}px;
  fill: {FG};
}}
.hdr {{ fill: {ACCENT}; font-weight: 700; }}
.dim {{ fill: {DIM}; font-weight: 400; }}
.rule {{ fill: {DIM}; }}
.key {{ fill: {ACCENT}; }}
.val {{ fill: {FG}; }}
.l {{
  opacity: 0;
  animation: rise {LINE_DUR}s cubic-bezier(.2,.8,.3,1) forwards;
}}
@keyframes rise {{
  from {{ opacity: 0; transform: translateY(6px); }}
  to   {{ opacity: 1; transform: translateY(0); }}
}}
</style>
<rect width="100%" height="100%" fill="{BG}" rx="6"/>
{chr(10).join(rows)}
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", default="mmelika")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets" / "info-card.svg",
    )
    args = ap.parse_args()

    resolved = [(k, v if v is not None else repo_count(args.user)) for k, v in FIELDS]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_svg(args.user, resolved), encoding="utf-8")
    print(f"wrote {args.out} ({args.out.stat().st_size / 1024:.1f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
