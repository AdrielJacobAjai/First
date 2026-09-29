"""Measure a PRINTED reference card and save its real patch colours.

Web: an admin does this at /calibration. Command line:
    python calibrate_card.py photo1.jpg [photo2.jpg ...] [--out card_calibration.json]

Photograph the finished card (no strip needed) in good, even daylight -- near a window, no direct
sun, no flash, no glare -- several times, or scan it on a flatbed scanner. The median colour of every
patch is measured and averaged across the photos. Those averages become this card's stored "true"
values, so later photos under any light are corrected back to how the card looks in daylight.

This is a disclosed approximation: it is only as good as the calibration lighting. A spectrophotometer
would be better. Re-run it whenever you print a new card.
"""
import argparse
from datetime import datetime, timezone

import cv2
import numpy as np

import colour_pipeline as cp
import reference_card as card

MAX_SPREAD_WARNING = 6.0   # sRGB levels; photos that disagree more than this had different lighting


class CalibrationError(Exception):
    """A calibration photo is unusable; the message says how to retake it."""


def measure_image(img_bgr):
    """Median sRGB (0-255) of each patch in one photo of the empty card."""
    gray = cp._gate_gray(img_bgr)
    if cp.is_blurry(gray)[0]:
        raise CalibrationError("too blurry - retake")
    if cp.has_glare(gray)[0]:
        raise CalibrationError("too much glare - retake in softer light")
    board = cp.locate_board(img_bgr, "file")
    if board is None:
        raise CalibrationError("could not find the whole card - keep the black border fully in frame")
    rgb = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    out = {}
    for name, box in card.patch_boxes(w, h).items():
        med, clipped = cp.sample_patch(rgb, box)
        if clipped > cp.MAX_CLIPPED_FRACTION:
            raise CalibrationError(f"patch '{name}' is overexposed - retake in softer light")
        out[name] = med * 255.0
    return out


def combine(runs):
    """Average several measurements. Returns (patches, worst_spread)."""
    patches, worst = {}, 0.0
    for name in card.PATCH_ORDER:
        vals = np.array([r[name] for r in runs])
        patches[name] = [round(float(v), 1) for v in vals.mean(axis=0)]
        worst = max(worst, float(vals.std(axis=0).max()))
    return patches, worst


def make_meta(n_photos, spread, by="command line"):
    return {"created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "photos": n_photos, "max_spread": round(spread, 2), "calibrated_by": by}


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--out", default=card.CALIBRATION_PATH)
    args = ap.parse_args()

    runs = []
    for p in args.photos:
        img = cv2.imread(p)
        if img is None:
            raise SystemExit(f"Cannot read image: {p}")
        try:
            runs.append(measure_image(img))
        except CalibrationError as e:
            raise SystemExit(f"{p}: {e}")
    patches, worst = combine(runs)
    for name in card.PATCH_ORDER:
        print(f"{name:22} nominal {card.NOMINAL_SRGB[name]!s:16} measured {tuple(int(round(v)) for v in patches[name])}")
    if len(runs) > 1 and worst > MAX_SPREAD_WARNING:
        print(f"WARNING: photos disagree by up to {worst:.1f} levels - lighting was not consistent. Retake.")
    if len(runs) < 3:
        print("Tip: use 3 or more photos taken at slightly different angles for a steadier average.")
    card.save_calibration(patches, make_meta(len(runs), worst), args.out)
    print(f"Saved {args.out}. Restart the app to use it.")


if __name__ == "__main__":
    main()
