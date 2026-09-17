# Changelog

## v1.1.0

- Add and remove products from inside the app, in any category view. You give it
  the price today and it works the September 2025 baseline backwards off the
  category curve, then backfills the history so the new line starts alongside
  the others. Optionally registers a shop URL in `sources.json` at the same time.
- Fixed the hover readout being clipped at the right-hand edge of a chart. The
  box now flips to whichever side has room.
- Existing databases are migrated in place on first launch; nothing is lost.

## v1.0.0

- First release. Dashboard, four category views, watchlist, threshold alerts,
  dark and light themes, CSV and PNG export, background polling.
- Ships with a modelled reconstruction of the memory shortage from 1 September
  2025, anchored to published DRAM and NAND contract pricing.
- Optional live prices from retailers you nominate in `sources.json`.
