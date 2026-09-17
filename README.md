# NANDTrack

[![Build Windows executable](https://github.com/YOUR-USERNAME/nand-price-tracker/actions/workflows/build-windows.yml/badge.svg)](https://github.com/YOUR-USERNAME/nand-price-tracker/actions/workflows/build-windows.yml)

A Windows desktop app that tracks what the memory shortage has done to PC
hardware prices since September 2025 — RAM, graphics cards, SATA SSDs and NVMe
drives, on one screen, updating while it runs.

Not a console tool: it opens as a proper window with a navigation rail, live
charts you can zoom and pan, a watchlist, threshold alerts in the notification
area, and a dark/light toggle.

---

## Get it

Grab `NANDTrack.exe` from the [Releases](../../releases) page, or from the
latest green run on the [Actions](../../actions) tab if you want the newest
build. One file, nothing to install, no Python needed.

Or build it yourself:

---

## Build the .exe

You need 64-bit Python 3.10 or newer on PATH. Nothing else.

```
build_exe.bat
```

About three minutes later you have `dist\NANDTrack.exe` — one file, roughly
60 MB, no installer and no Python needed on the machine you copy it to. It
keeps its database in `%APPDATA%\NANDTrack`, so the exe itself can live on a
USB stick.

To run from source while you edit it: `run_dev.bat`, or `python run.py`.

If you would rather ship an installer than a loose .exe, point Inno Setup at
`dist\NANDTrack.exe`; nothing in the app assumes an install location.

Every push to `main` builds the same executable on a Windows runner and leaves
it as a downloadable artifact. Push a tag starting with `v` — `git tag v1.0.0
&& git push --tags` — and it publishes a release with the .exe attached.

---

## About the price data — read this part

The app ships with a **modelled reconstruction** of the shortage, not scraped
retailer archives. That is a deliberate choice, and it is the one thing about
this build you should know before you trust a number on screen.

No free public API serves a year of per-SKU retail history. PCPartPicker has no
public API and blocks scrapers, Keepa charges for one, and Amazon and Newegg
both forbid scraping in their terms. So `nandtrack/market.py` reconstructs the
period from published contract-price data instead, and every point it writes is
tagged `modelled` in the database and labelled as such in the status bar.

The curves are anchored to real figures:

| Period | What actually happened | Source |
|---|---|---|
| Q4 2025 | NAND contract prices +33–38%; November NAND wafer contracts +60% MoM | TrendForce |
| Q1 2026 | Conventional DRAM +90–95% QoQ; NAND +85–90% | TrendForce |
| Q2 2026 | DRAM +58–63% QoQ; NAND +70–75% QoQ | TrendForce |
| Q3 2026 | DRAM +13–18%; NAND +10–15% — the first real deceleration | TrendForce via Igor's Lab |
| GPUs | Insulated until fixed memory contracts expired, then three 2026 hikes: January +10–15%, a May round aimed at the flagship, July/August +20–30% | Economic Daily News, Tom's Hardware |

Retail checkpoints the model is fitted to: a 32GB DDR5-6000 CL30 kit at roughly
€70–90 in late 2025, ~€127 by December, €282–309 by April 2026; DDR4 32GB kits
landing at €150–210; 1TB entry Gen4 NVMe from about €50 to €140–250; RTX 5090
from a ~€2,000 launch price to €4,300 in June 2026 and past €5,000 by September;
RTX 5080 to about €1,595; RX 9070 XT to about €1,037.

So the shape, the timing and the magnitude are right, and an individual
Tuesday is not a receipt. Which brings us to:

## Wiring up real prices

Settings → Price sources → **Create a starter sources.json**, then fill in URLs
for the shops you actually buy from. Live quotes take priority over the model,
get stored alongside it, and are labelled with the retailer's name in the status
bar. `sources.example.json` in this folder shows the format:

```json
{
  "retailer": "my-retailer",
  "timeout": 12,
  "products": {
    "nvme-sn850x-2tb": {
      "url": "https://shop.example/wd-black-sn850x-2tb",
      "selector": "span.product-price",
      "regex": "([0-9][0-9.,]*)"
    }
  }
}
```

`selector` is any CSS selector; `regex` is optional and runs on whatever the
selector matched (or the whole page if you leave the selector out). Prices are
parsed in both `1.299,00` and `1,299.00` styles. Check the shop's terms before
you point it anywhere — some allow this, some don't, and that call is yours.

To add a source that isn't a web page at all — an affiliate API, a price-feed,
a CSV a colleague maintains — write a class with `available()`, `fetch()` and
`describe()` in `nandtrack/sources.py` and add it to `build_sources()`.

---

## What's in the window

**Dashboard** — one card per category with the current average, the cheapest
tracked product, the change since 1 September 2025 and a sparkline; a combined
index chart where 100 is each product's own baseline price; the ten products
that moved most this week; and what a mid-range build's memory bill now costs
against what it cost a year ago.

**Category views** (RAM, graphics cards, SATA SSDs, NVMe SSDs) — a sortable
table with filters for brand, capacity and form factor, and a chart that
overlays every row you select, up to ten at once. Switch between absolute price
and percentage change, turn on a log scale, drag to pan, scroll to zoom, and
hover for the exact price and date of the nearest sample. Export the selection
as CSV or save the chart as a PNG.

**Watchlist** — the products you starred, same view.

**Settings** — polling interval, background polling, close-to-tray, theme,
currency symbol, notifications, live sources, and your armed alerts.

Alerts: select one product, press *Alert me when this moves*, and set a
percentage. It fires a Windows notification when the price moves that far from
where it was when you set it, then re-arms from the new price — so a drifting
price notifies you once per threshold crossed rather than once per poll.

---

## How it fits together

```
run.py                  launcher
nandtrack/
  app.py                startup, first-run backfill, splash
  config.py             settings, saved as JSON in %APPDATA%
  db.py                 SQLite: products, prices, alerts (WAL, one conn per thread)
  catalog.py            the 29 tracked SKUs and their September 2025 baselines
  market.py             the surge curves and where each anchor comes from
  seed.py               first-run backfill, and the top-up on every later launch
  sources.py            ModelledSource and HttpSource, both pluggable
  fetcher.py            QThread worker, polls on a timer, reports what moved
  alerts.py             threshold rules
  analytics.py          category stats, movers, index series
  ui/
    theme.py            palette and Qt stylesheet for both themes
    widgets.py          sparkline, category card, change pill
    charts.py           pyqtgraph chart: overlay, crosshair, log/percent modes
    dashboard.py        the landing view
    category.py         table + chart, used for all four categories and the watchlist
    settings_view.py    settings and alert management
    main_window.py      shell, navigation, status strip, tray
```

Design notes, since the colours carry meaning: rising prices read copper-warm
and falling prices read mint-cool — deliberately the opposite of a stock
ticker, because on this screen a rising line is the bad news. Prices and
percentages are set in a tabular monospace so decimal points line up down a
column; everything else uses the system UI face.

Backfilling a year of daily history for 29 products takes about a tenth of a
second and lands at roughly 11,000 rows, and pyqtgraph draws ten overlaid
year-long series without dropping frames. The database grows by 29 rows per
poll, so at the default ten-minute interval that's about 1.5 MB a month.

Network failures, unreadable pages, a missing `sources.json` and a read-only
profile are all handled quietly: the app falls back to the modelled curve, says
so in the status bar, and keeps the charts up.

---

## Adding your own products

Press **Add product** in any category view. Give it a name and what the part
costs today, and it works the September 2025 baseline backwards off that
category's curve, then backfills a year of history so the new line starts where
every other line starts. Paste a shop URL in the optional live-price box and it
registers the scraping rule for you as well.

Products you add yourself can be removed again with the **Remove** button next
to it. The ones that ship with the app can't — they're rebuilt from
`catalog.py` on every launch.

If you would rather add a batch of them in code, append to `CATALOG` in
`nandtrack/catalog.py`:

```python
_p("nvme-990evo-1tb", "Samsung 990 EVO 1TB", "nvme_ssd",
   "Samsung", 79.0, 1.00, 1000, "M.2 2280", "PCIe 4.0 x4"),
```

`baseline` is what it cost on 1 September 2025; `surge_scale` is how hard it
rides its category curve — `1.0` tracks it exactly, `0.5` moves half as far
above the baseline, `1.9` nearly twice as far. Restart, and history is
backfilled for the new entry automatically.

Licence: MIT. Do what you like with it.
