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


def render_board(strip_rgb, patches=None, border=True):
    img = np.zeros((H, W, 3), np.uint8)
    img[:] = PAPER
    bw = int(0.035 * H)
    if border:
        cv2.rectangle(img, (0, 0), (W - 1, H - 1), (0, 0, 0), bw * 2)  # thick black border
    for name, box in card.patch_boxes(W, H).items():
        x, y, w, h = box
        img[y:y + h, x:x + w] = (patches or card.PATCH_TRUE_SRGB)[name]
    x, y, w, h = card.strip_box(W, H)
    img[y:y + h, x:x + w] = strip_rgb
    return img  # RGB


def _light(rgb_uint8, light, seed=0, exposure=1.0):
    """Apply a lighting distortion in linear light, add sensor noise. RGB uint8 in, RGB uint8 out."""
    rng = np.random.default_rng(seed)
    A, off = LIGHTS[light]
    lin = srgb_to_linear(rgb_uint8.astype(np.float64) / 255.0)
    lin = (lin @ A.T) * exposure + off
    lin += rng.normal(0, 0.002, lin.shape)
    return (linear_to_srgb(lin) * 255 + 0.5).astype(np.uint8)


def photograph(strip="positive", light="daylight", blur=0, exposure=1.0,
               seed=0, margin=0, patches=None, strip_rgb=None):
    """Return a BGR uint8 'photo'. margin>0 adds a dark table around the board."""
    rng = np.random.default_rng(seed)
    rgb = _light(render_board(strip_rgb if strip_rgb is not None else STRIPS[strip], patches), light, seed, exposure)
    bgr = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR)
    if blur:
        bgr = cv2.GaussianBlur(bgr, (0, 0), blur)
    if margin:
        bgr = cv2.copyMakeBorder(bgr, margin, margin, margin * 2, margin * 2,
                                 cv2.BORDER_CONSTANT, value=(60, 90, 70))
    return bgr


def in_scene(board_bgr, angle=0.0, skew=0.0, bg=(60, 90, 70), out=(1600, 1200), fill=0.6, quarter_turns=0,
             border_grey=None, wood_bg=None):
    """Put the board into a larger 'real world' photo: rotated, seen at an angle, on a background.

    skew: perspective strength (0..0.25); border_grey: repaint the near-black border with this grey
    level to mimic a printer that cannot print true black.
    """
    board = board_bgr.copy()
    if border_grey is not None:
        m = np.all(board < 12, axis=2)
        board[m] = border_grey
    h, w = board.shape[:2]
    ow, oh = out
    sc = fill * min(ow / w, oh / h)
    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
    dst = (src - [w / 2, h / 2]) * sc
    dst[:, 0] *= 1 - skew * np.array([1, 1, -1, -1]) * 0.0                       # keep x scale
    dst[:, 1] *= 1 + skew * np.array([-1, -1, 1, 1]) * np.array([1, 1, 1, 1]) * 0.5   # top edge shorter/longer
    dst[:, 0] *= 1 - skew * np.array([1, 1, 0, 0])                              # narrower at the top
    ang = np.deg2rad(angle)
    R = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    dst = dst @ R.T + [ow / 2, oh / 2]
    M = cv2.getPerspectiveTransform(src, dst.astype(np.float32))
    scene = np.zeros((oh, ow, 3), np.uint8)
    scene[:] = bg
    if wood_bg is not None:
        scene = wood_bg.copy()
    warped = cv2.warpPerspective(board, M, (ow, oh), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_TRANSPARENT,
                                 dst=scene)
    return np.rot90(warped, quarter_turns).copy()


def wood(size=(1600, 1200), seed=0):
    """Sunlit, low-chroma, streaky table surface about as bright as paper (a hard background)."""
    rng = np.random.default_rng(seed)
    w, h = size
    streaks = cv2.GaussianBlur(rng.normal(0, 1, (h, w)).astype(np.float32), (0, 0), sigmaX=40, sigmaY=2.5)
    streaks = 28 * streaks / (streaks.std() + 1e-6)
    base = np.array([150, 176, 196], np.float32)                      # BGR tan, bright
    return np.clip(base + streaks[..., None] + rng.normal(0, 3, (h, w, 1)), 0, 255).astype(np.uint8)


def print_photo(strip="positive", light="daylight", patches=None, strip_rgb=None, angle=5.0, skew=0.05,
                seed=0, quarter_turns=0):
    """A phone photo of a home print: no thick border, white page margin, hairline outline, on a wood table."""
    board = render_board(strip_rgb if strip_rgb is not None else STRIPS[strip], patches, border=False)
    page = np.full((int(H * 1.32), int(W * 1.14), 3), 250, np.uint8)
    y0, x0 = (page.shape[0] - H) // 2, (page.shape[1] - W) // 2
    page[y0:y0 + H, x0:x0 + W] = board
    cv2.rectangle(page, (x0 + 6, y0 + 6), (x0 + W - 7, y0 + H - 7), (40, 40, 40), 2)      # hairline outline
    rgb_lit = _light(page, light, seed)
    scene = in_scene(cv2.cvtColor(rgb_lit, cv2.COLOR_RGB2BGR), angle=angle, skew=skew, bg=(0, 0, 0),
                     fill=0.75, quarter_turns=0, wood_bg=wood(seed=seed))
    return np.rot90(scene, quarter_turns).copy()


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
