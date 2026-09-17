# Changelog

## v1.2.0

- The curve can now be driven by a live market index instead of stopping at its
  hardcoded anchors. FRED (free, official, with a free API key) and any CSV
  address are both supported, configured under Settings → Market index.
- Rather than substituting the fetched index for the curve, the app fits how far
  each category moved per point of index movement over the overlapping window,
  and extrapolates on that. History before 15 September 2026 is unaffected.
- Products are re-fitted against prices your own sources report, replacing the
  baseline and trend factor you typed in with measured ones. Marked with ◉ in
  the tables.
- The fit refuses to claim a trend factor when the curve has not moved enough to
  separate it from the baseline, and says so, instead of returning a confident
  wrong answer.
- Observed prices are never rewritten by a re-fit; only modelled points are
  redrawn.
- The dashboard now states where its numbers came from and up to what date.
- Databases from v1.0.0 and v1.1.0 migrate in place.

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
