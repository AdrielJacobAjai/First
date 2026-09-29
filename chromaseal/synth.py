"""Synthetic board photos for tests and the demo (no real photos needed).

Renders the reference board plus a mock strip, then simulates a lighting
distortion (per-channel gain + cross-channel leak + flare offset) in linear
light, adds sensor noise, and optionally blur. Run `python synth.py` to write
a demo set into demo_images/.
"""
import os

import cv2
import numpy as np

import reference_card as card
from colour_pipeline import linear_to_srgb, srgb_to_linear

W, H = 960, 600
PAPER = (232, 230, 225)

# name -> (3x3 leak matrix applied to linear RGB, offset)
LIGHTS = {
    "daylight": (np.diag([1.00, 1.00, 1.00]), 0.000),
    "warm_lamp": (np.array([[0.94, 0.04, 0.00], [0.04, 0.78, 0.03], [0.00, 0.05, 0.46]]), 0.004),
    "tubelight": (np.array([[0.85, 0.10, 0.00], [0.05, 0.90, 0.05], [0.00, 0.12, 0.80]]), 0.006),
    "flashlight": (np.array([[0.98, 0.02, 0.00], [0.02, 0.96, 0.02], [0.00, 0.03, 0.98]]), 0.010),
    "shade": (np.array([[0.55, 0.03, 0.00], [0.03, 0.62, 0.05], [0.00, 0.06, 0.85]]), 0.002),
}

STRIPS = {
    "positive": card.PATCH_TRUE_SRGB["reagent_positive"],
    "unreacted": card.PATCH_TRUE_SRGB["reagent_pale"],
    "intermediate": card.PATCH_TRUE_SRGB["reagent_intermediate"],
}


def render_board(strip_rgb, patches=None):
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = PAPER
    bw = int(0.035 * H)
    cv2.rectangle(img, (0, 0), (W - 1, H - 1), (0, 0, 0), bw * 2)  # thick black border
    for name, box in card.patch_boxes(W, H).items():
        x, y, w, h = box
        img[y:y + h, x:x + w] = (patches or card.PATCH_TRUE_SRGB)[name]
    x, y, w, h = card.strip_box(W, H)
    img[y:y + h, x:x + w] = strip_rgb
    return img  # RGB


def photograph(strip="positive", light="daylight", blur=0, exposure=1.0,
               seed=0, margin=0, patches=None, strip_rgb=None):
    """Return a BGR uint8 'photo'. margin>0 adds a dark table around the board."""
    rng = np.random.default_rng(seed)
    A, off = LIGHTS[light]
    lin = srgb_to_linear(render_board(strip_rgb if strip_rgb is not None else STRIPS[strip], patches).astype(np.float64) / 255.0)
    lin = (lin @ A.T) * exposure + off
    lin += rng.normal(0, 0.002, lin.shape)
    rgb = (linear_to_srgb(lin) * 255 + 0.5).astype(np.uint8)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if blur:
        bgr = cv2.GaussianBlur(bgr, (0, 0), blur)
    if margin:
        bgr = cv2.copyMakeBorder(bgr, margin, margin, margin * 2, margin * 2,
                                 cv2.BORDER_CONSTANT, value=(60, 90, 70))
    return bgr


def encode_jpeg(bgr):
    ok, buf = cv2.imencode(".jpg", bgr, [cv2.IMWRITE_JPEG_QUALITY, 92])
    assert ok
    return buf.tobytes()


def write_demo_set(out="demo_images"):
    os.makedirs(out, exist_ok=True)
    for strip in STRIPS:
        for light in LIGHTS:
            cv2.imwrite(f"{out}/{strip}_{light}.jpg", photograph(strip, light))
    cv2.imwrite(f"{out}/positive_blurred.jpg", photograph("positive", "daylight", blur=6))
    cv2.imwrite(f"{out}/positive_overexposed.jpg", photograph("positive", "flashlight", exposure=1.6))
    cv2.imwrite(f"{out}/positive_on_table_file.jpg", photograph("positive", "warm_lamp", margin=120))


if __name__ == "__main__":
    write_demo_set()
    print("wrote demo_images/")
