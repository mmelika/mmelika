#!/usr/bin/env python3
"""Render the GitHub contribution calendar as an SVG that slides in diagonally.

Reads the public contributions fragment GitHub serves for any user. That page
needs no token and has no rate limit worth worrying about, which is why this can
run unattended in CI every day.

    python scripts/gen_heatmap.py --user mmelika
"""

import argparse
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

SRC = "https://github.com/users/{user}/contributions"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) profile-art/1.0"

# GitHub's own five contribution levels, none -> most.
PALETTE = ["#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"]

CELL = 11
GAP = 3
STEP = CELL + GAP

PAD = 16
TOP = 34  # room for month labels
LEFT = 30  # room for weekday labels
BG = "#0d1117"
LABEL = "#8b949e"

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}

# Each diagonal band of cells lights up together, so the wave sweeps from the
# top-left corner to the bottom-right one.
BAND_STAGGER = 0.018
CELL_DUR = 0.42


def fetch_calendar(user: str) -> tuple[dict[tuple[int, int], tuple[str, int]], int]:
    """Return {(col, row): (date, level)} plus the headline contribution count."""
    resp = requests.get(
        SRC.format(user=user),
        headers={"User-Agent": UA, "Accept": "text/html", "X-Requested-With": "XMLHttpRequest"},
        timeout=30,
    )
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    grid: dict[tuple[int, int], tuple[str, int]] = {}
    for td in soup.select("td.ContributionCalendar-day"):
        date, level, cell_id = td.get("data-date"), td.get("data-level"), td.get("id", "")
        if not (date and level is not None):
            continue
        # id looks like contribution-day-component-<row>-<col>, which is the
        # only place the grid position is stated outright.
        m = re.search(r"-(\d+)-(\d+)$", cell_id)
        if not m:
            continue
        row, col = int(m.group(1)), int(m.group(2))
        grid[(col, row)] = (date, int(level))

    if not grid:
        raise RuntimeError(
            f"no contribution cells found for {user!r} — GitHub's markup may have changed"
        )

    total = 0
    if (m := re.search(r"([\d,]+)\s+contributions", soup.get_text())):
        total = int(m.group(1).replace(",", ""))

    return grid, total


# A label is about 3 characters wide, so ticks closer together than this would
# overprint each other. The first column is usually a part-week, which is what
# puts its label right on top of the next month's.
MIN_TICK_GAP = 3


def month_ticks(grid: dict[tuple[int, int], tuple[str, int]]) -> list[tuple[int, str]]:
    """First column of each month, for the labels along the top."""
    ticks: list[tuple[int, str]] = []
    seen: set[str] = set()
    for col in sorted({c for c, _ in grid}):
        dates = [grid[(col, r)][0] for r in range(7) if (col, r) in grid]
        if not dates:
            continue
        month = dates[0][:7]
        if month in seen:
            continue
        seen.add(month)
        if ticks and col - ticks[-1][0] < MIN_TICK_GAP:
            ticks[-1] = (col, MONTHS[int(month[5:7]) - 1])  # let the newer one win
        else:
            ticks.append((col, MONTHS[int(month[5:7]) - 1]))
    return ticks


def build_svg(grid, total, user) -> str:
    cols = max(c for c, _ in grid) + 1
    width = LEFT + cols * STEP + PAD
    height = TOP + 7 * STEP + PAD

    bands = sorted({c + r for c, r in grid})
    rules = [f".b{b}{{animation-delay:{b * BAND_STAGGER:.3f}s}}" for b in bands]

    cells = []
    for (col, row), (date, level) in sorted(grid.items()):
        x = LEFT + col * STEP
        y = TOP + row * STEP
        cells.append(
            f'<rect class="c b{col + row}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" '
            f'rx="2" fill="{PALETTE[level]}"><title>{date}: level {level}</title></rect>'
        )

    labels = [
        f'<text class="lbl" x="{LEFT + col * STEP}" y="{TOP - 8}">{name}</text>'
        for col, name in month_ticks(grid)
    ]
    labels += [
        f'<text class="lbl" x="{LEFT - 8}" y="{TOP + row * STEP + CELL - 1}" '
        f'text-anchor="end">{name}</text>'
        for row, name in WEEKDAYS.items()
    ]

    headline = f"{total:,} contributions in the last year" if total else "contributions"

    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{headline} for {user}">
<style>
.c {{
  opacity: 0;
  transform: translate(-5px, -5px) scale(0.55);
  transform-origin: center;
  transform-box: fill-box;
  animation: pop {CELL_DUR}s cubic-bezier(.2,.9,.3,1) forwards;
}}
@keyframes pop {{ to {{ opacity: 1; transform: translate(0,0) scale(1); }} }}
.lbl {{
  font-family: ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
  font-size: 10px;
  fill: {LABEL};
  opacity: 0;
  animation: fade .5s ease-out .35s forwards;
}}
@keyframes fade {{ to {{ opacity: 1; }} }}
{chr(10).join(rules)}
</style>
<rect width="100%" height="100%" fill="{BG}" rx="6"/>
{chr(10).join(labels)}
{chr(10).join(cells)}
</svg>
"""


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--user", default="mmelika")
    ap.add_argument(
        "-o",
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "assets" / "contrib-heatmap.svg",
    )
    args = ap.parse_args()

    grid, total = fetch_calendar(args.user)

    # A healthy year is 365-371 cells. Anything far short means the scrape only
    # caught part of the calendar, and a truncated graph is worse than no commit.
    if len(grid) < 350:
        print(
            f"error: only {len(grid)} days parsed, expected ~365 — refusing to write",
            file=sys.stderr,
        )
        return 1

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(build_svg(grid, total, args.user), encoding="utf-8")

    active = sum(1 for _, lvl in grid.values() if lvl > 0)
    print(
        f"wrote {args.out} ({len(grid)} days, {active} active, "
        f"{total:,} contributions, {args.out.stat().st_size / 1024:.1f} KB)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
