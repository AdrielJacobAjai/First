"""Measure a PRINTED reference card and save its real patch colours.

Usage:  python calibrate_card.py photo1.jpg [photo2.jpg ...] [--out card_calibration.json]

Photograph the finished card (no strip needed) in good, even daylight -- near a window, no direct
sun, no flash, no glare -- several times, or scan it on a flatbed scanner. The median colour of every
patch is measured and averaged across the photos. Those averages become this card's stored "true"
values, so later photos under any light are corrected back to how the card looks in daylight.

This is a disclosed approximation: it is only as good as the calibration lighting. A spectrophotometer
would be better. Re-run it whenever you print a new card.
"""
import argparse
import json
from datetime import datetime, timezone

import cv2
import numpy as np

import colour_pipeline as cp
import reference_card as card


def measure(path):
    img = cv2.imread(path)
    if img is None:
        raise SystemExit(f"Cannot read image: {path}")
    gray = cp._gate_gray(img)
    blurry, var = cp.is_blurry(gray)
    glare, frac = cp.has_glare(gray)
    if blurry or glare:
        raise SystemExit(f"{path}: {'too blurry' if blurry else 'too much glare'} - retake this photo.")
    board = cp.locate_board(img, "file")
    if board is None:
        raise SystemExit(f"{path}: could not find the whole card - keep the black border in frame.")
    rgb = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
    h, w = rgb.shape[:2]
    out = {}
    for name, box in card.patch_boxes(w, h).items():
        med, clipped = cp.sample_patch(rgb, box)
        if clipped > cp.MAX_CLIPPED_FRACTION:
            raise SystemExit(f"{path}: patch '{name}' is overexposed - retake in softer light.")
        out[name] = med * 255.0
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("photos", nargs="+")
    ap.add_argument("--out", default=card.CALIBRATION_PATH)
    args = ap.parse_args()

    runs = [measure(p) for p in args.photos]
    patches, worst = {}, 0.0
    for name in card.PATCH_ORDER:
        vals = np.array([r[name] for r in runs])
        patches[name] = [round(float(v), 1) for v in vals.mean(axis=0)]
        worst = max(worst, float(vals.std(axis=0).max()))
        print(f"{name:22} nominal {card.PATCH_TRUE_SRGB[name]!s:16} measured {tuple(int(round(v)) for v in patches[name])}")
    if len(runs) > 1 and worst > 6:
        print(f"WARNING: photos disagree by up to {worst:.1f} levels - lighting was not consistent. Retake.")
    if len(runs) < 3:
        print("Tip: use 3 or more photos taken at slightly different angles for a steadier average.")

    with open(args.out, "w") as fh:
        json.dump({"created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "photos": len(runs), "max_spread": round(worst, 2), "patches": patches}, fh, indent=2)
    print(f"Saved {args.out}. Restart the app to use it.")


if __name__ == "__main__":
    main()
