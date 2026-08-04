# How this profile works

GitHub strips JavaScript out of README markup, so every bit of motion here lives
*inside* self-contained SVG files as CSS keyframes. The README itself is three
`<img>` tags in a terminal-styled table.

Each animation plays once on load and then freezes. Nothing loops.

## The three panels

| File | What it is | Regenerated |
|---|---|---|
| `assets/contrib-heatmap.svg` | Contribution calendar, cells popping in along a diagonal wave | Daily, by Actions |
| `assets/info-card.svg` | neofetch-style panel, lines rising in one at a time | Daily, by Actions |
| `assets/ascii-portrait.svg` | Photo as ASCII art, wiping in row by row | Once, locally |

## Regenerating

The two CI-safe scripts need nothing but `requests` and `beautifulsoup4`:

```bash
pip install -r scripts/requirements.txt
python scripts/gen_heatmap.py --user mmelika
python scripts/gen_card.py --user mmelika
```

Edit `FIELDS` at the top of `scripts/gen_card.py` to change what the card says.

The portrait is separate. It needs a source photo and a background-removal model
(~180MB on first run), which is why Actions never touches it:

```bash
pip install -r scripts/requirements-portrait.txt
python scripts/gen_portrait.py ~/Downloads/photo.jpg
```

**The source photo is never committed** — `.gitignore` blocks image files, and
only the ASCII rendering of it lands in the repo.

Pass `--cache cutout.png` to save the background-removed image and reuse it on
later runs, which skips the slow part while tuning.

## Two things worth knowing before you change the portrait

**The brightness mapping is inverted on purpose.** The intuitive mapping puts
dense characters where the image is bright, since light text on a dark terminal
reads as glowing. That fails on a dark-haired subject: the hair becomes empty
space, and the only thing marking the head is the bright rim studio lighting
leaves around it, which reads as a stray halo. Mapping dark pixels to dense
characters fixes both ends — hair renders solid, and the rim falls to the sparse
end of the ramp where it disappears.

**More columns read better, not worse.** At the size the README renders it, 60
and 80 columns come out as an anonymous skull. 110 resolves into a face.

## Local preview

`preview.html` arranges the three SVGs the way the README does. Serve the folder
and open it — opening the file directly over `file://` works too, but some
browsers won't run SVG animations from there:

```bash
python3 -m http.server 8777
```

## Daily refresh

`.github/workflows/update-profile-art.yml` runs at 06:17 UTC, regenerates the
heatmap and card, and commits them with `[skip ci]`. It can also be triggered by
hand from the Actions tab.

GitHub serves README images through its `camo` proxy, so a refreshed graph
usually shows up within a few hours rather than immediately.
