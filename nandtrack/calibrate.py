"""Learning a product's parameters from prices that were actually observed.

When you add a product you tell the app what it costs today and roughly how hard
it follows its category. Both are guesses, and both stop mattering the moment
there is real data: every quote a retailer feed returns is a point the app can
check itself against.

Given observations (t, price) and the category curve idx(t), the model says

    price(t) = baseline * (1 + scale * (idx(t) - 1))

which is linear in `baseline` and `baseline * scale`, so it fits in closed form
with no solver. One observation pins the baseline against the assumed scale; a
handful spread over a few weeks pins both, and the typed-in numbers get
overwritten by measurement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Sequence, Tuple

from .db import Database
from .market import category_index

MIN_DAYS = 3          # distinct days before the baseline alone will move
MIN_DAYS_FULL = 8     # distinct days before the trend factor is fitted too
MIN_SPAN_DAYS = 10    # observations need to straddle some actual price movement
MIN_SPREAD = 0.05     # ...and the curve must have moved 5% while we watched


@dataclass
class Fit:
    product_id: int
    baseline: float
    scale: float
    points: int
    span_days: int
    residual_pct: float       # typical distance between fit and observation
    full: bool                # was the trend factor fitted, or only the baseline

    def summary(self) -> str:
        what = "baseline and trend" if self.full else "baseline only"
        return (f"{what} from {self.points} observed day(s) over {self.span_days} days, "
                f"typical error {self.residual_pct:.1f}%")

    def note(self) -> str:
        """What this fit can and cannot claim, in words for the status bar."""
        if self.full:
            return "matched against real prices"
        return ("matched to today's real price; the curve has not moved enough yet "
                "to separate the trend factor")


def _daily(observations: Sequence[Tuple[datetime, float]]) -> List[Tuple[datetime, float]]:
    """One point per day - the day's low - so a busy poller cannot outvote a quiet one."""
    best: dict = {}
    for when, price in observations:
        key = when.date()
        if key not in best or price < best[key][1]:
            best[key] = (when, price)
    return [best[k] for k in sorted(best)]


def fit_product(db: Database, product_id: int,
                assumed_scale: Optional[float] = None) -> Optional[Fit]:
    row = db.product(product_id)
    if not row:
        return None
    points = _daily(db.observed(product_id))
    if len(points) < MIN_DAYS:
        return None

    category = row["category"]
    scale_now = float(assumed_scale if assumed_scale is not None else row["surge_scale"])
    span = (points[-1][0].date() - points[0][0].date()).days

    xs = [category_index(category, when.date()) - 1.0 for when, _ in points]
    ys = [price for _, price in points]

    # Separating the baseline from the trend factor is only possible if the
    # curve actually moved while we were watching. Over a flat fortnight any
    # number of (baseline, scale) pairs fit the same prices equally well, and
    # the regression will happily return a confident, wrong answer. So the test
    # is relative: the model factor has to have shifted by a few percent across
    # the observation window, not by some absolute amount.
    mean_x = sum(xs) / len(xs)
    spread = (max(xs) - min(xs)) / max(1.0 + mean_x, 0.05)
    full = (len(points) >= MIN_DAYS_FULL and span >= MIN_SPAN_DAYS
            and spread >= MIN_SPREAD)

    if full:
        # least squares on price = a + b*x, then baseline = a, scale = b / a
        n = float(len(xs))
        sx = sum(xs)
        sy = sum(ys)
        sxx = sum(x * x for x in xs)
        sxy = sum(x * y for x, y in zip(xs, ys))
        det = n * sxx - sx * sx
        if abs(det) < 1e-9:
            full = False
        else:
            a = (sy * sxx - sx * sxy) / det
            b = (n * sxy - sx * sy) / det
            if a > 0.01 and 0.05 <= (b / a) <= 6.0:
                baseline, scale = a, b / a
            else:
                full = False

    if not full:
        # hold the trend factor, move the baseline so the curve passes through
        # the observations: baseline = mean(price / (1 + scale*x))
        adjusted = [y / max(1.0 + scale_now * x, 0.05) for x, y in zip(xs, ys)]
        baseline, scale = sum(adjusted) / len(adjusted), scale_now

    errors = []
    for x, y in zip(xs, ys):
        predicted = baseline * (1.0 + scale * x)
        if predicted > 0:
            errors.append(abs(y - predicted) / predicted * 100.0)
    residual = sorted(errors)[len(errors) // 2] if errors else 0.0

    if not (0.01 < baseline < 1_000_000):
        return None

    return Fit(product_id=product_id, baseline=baseline, scale=scale,
               points=len(points), span_days=span, residual_pct=residual, full=full)


def apply_fit(db: Database, fit: Fit, rewrite_history: bool = True) -> None:
    """Store the fit and, optionally, redraw the modelled history under it."""
    db.set_fit(fit.product_id, fit.baseline, fit.scale,
               datetime.now(timezone.utc).isoformat())
    if not rewrite_history:
        return
    from .seed import rebuild_modelled

    rebuild_modelled(db, fit.product_id)


def calibrate_all(db: Database, min_days: int = MIN_DAYS) -> List[Fit]:
    """Re-fit every product that has collected enough real quotes."""
    counts = db.observed_counts()
    fits: List[Fit] = []
    for product_id, days in counts.items():
        if days < min_days:
            continue
        fit = fit_product(db, product_id)
        if fit:
            apply_fit(db, fit)
            fits.append(fit)
    if fits:
        db.set_meta("last_calibration", datetime.now(timezone.utc).isoformat())
    return fits


def candidates(db: Database) -> Tuple[int, int]:
    """(products with enough data to fit, products with some real data)."""
    counts = db.observed_counts()
    return sum(1 for n in counts.values() if n >= MIN_DAYS), len(counts)
