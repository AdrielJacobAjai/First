"""Colour pipeline: quality gate, card location, correction fit, classification.

Implements brief sections 3-5. Everything that touches colour maths works on
linear RGB (0..1); values are converted back to gamma-encoded sRGB only for
skimage.color.rgb2lab, which expects sRGB.
"""
import cv2
import numpy as np
from skimage.color import deltaE_ciede2000, rgb2lab

import reference_card as card

# --- tunable placeholders (set from real test photos) -----------------------
BLUR_THRESHOLD = 100.0        # Laplacian variance, on image resized to GATE_WIDTH
GATE_WIDTH = 800
GLARE_BRIGHTNESS = 250
GLARE_AREA = 0.02
MAX_CLIPPED_FRACTION = 0.20   # per patch
MAX_FIT_RESIDUAL = 5.0        # mean dE2000 on the validated patches
MIN_CARD_AREA_FRACTION = 0.25  # contour fallback only


# --- 3.1 linearisation ------------------------------------------------------
def srgb_to_linear(c):
    c = np.asarray(c, dtype=np.float64)
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def linear_to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, 12.92 * c, 1.055 * c ** (1 / 2.4) - 0.055)


# --- 3.2 patch sampling -----------------------------------------------------
def sample_patch(image_rgb_uint8, box):  # box = (x, y, w, h)
    x, y, w, h = box
    x0, x1 = x + int(0.2 * w), x + int(0.8 * w)
    y0, y1 = y + int(0.2 * h), y + int(0.8 * h)
    region = image_rgb_uint8[y0:y1, x0:x1].reshape(-1, 3)
    clipped_fraction = np.mean(np.any(region >= 250, axis=1))
    median_rgb = np.median(region, axis=0) / 255.0  # 0..1, still sRGB/gamma
    return median_rgb, clipped_fraction


# --- 3.3 correction fit -----------------------------------------------------
def fit_correction(observed_linear, true_linear):
    """
    observed_linear, true_linear: (N, 3) arrays, N >= 4, values in linear RGB.
    Returns a (4, 3) matrix M with [R, G, B, 1] @ M ~= true.
    Raises if patches don't span enough of colour space (e.g. neutrals only).
    """
    observed_linear = np.asarray(observed_linear, dtype=np.float64)
    true_linear = np.asarray(true_linear, dtype=np.float64)
    if len(observed_linear) < 4:
        raise ValueError("Need at least 4 calibration patches for an affine fit")
    P = np.hstack([observed_linear, np.ones((len(observed_linear), 1))])
    M, residuals, rank, _ = np.linalg.lstsq(P, true_linear, rcond=None)
    if rank < 4:
        raise ValueError(
            "Calibration patches don't span enough of colour space "
            "(e.g. neutrals only — need patches where R, G, B genuinely differ)"
        )
    return M


def apply_correction(M, rgb_linear):
    v = np.append(np.asarray(rgb_linear, dtype=np.float64), 1.0)
    return v @ M


def apply_correction_image(M, image_rgb_uint8):
    """Correct a whole image (used only for the 'corrected' preview)."""
    lin = srgb_to_linear(image_rgb_uint8.astype(np.float64) / 255.0)
    flat = lin.reshape(-1, 3)
    out = np.hstack([flat, np.ones((len(flat), 1))]) @ M
    out = linear_to_srgb(out).reshape(image_rgb_uint8.shape)
    return (out * 255 + 0.5).astype(np.uint8)


# --- 3.4 Lab and distance ---------------------------------------------------
def to_lab(rgb_linear):
    srgb = linear_to_srgb(np.asarray(rgb_linear, dtype=np.float64))
    return rgb2lab(srgb.reshape(1, 1, 3))[0, 0]


def srgb_uint8_to_lab(rgb):
    return to_lab(srgb_to_linear(np.asarray(rgb, dtype=np.float64) / 255.0))


def color_distance(lab1, lab2):
    a = np.asarray(lab1, dtype=np.float64).reshape(1, 1, 3)
    b = np.asarray(lab2, dtype=np.float64).reshape(1, 1, 3)
    return float(deltaE_ciede2000(a, b)[0, 0])


# --- 3.5 decision rule ------------------------------------------------------
def decide(strip_lab, target_lab, blank_lab, max_distance=20.0, min_margin=5.0):
    """max_distance, min_margin: placeholders. Set from real test-swatch photos."""
    d_target = color_distance(strip_lab, target_lab)
    d_blank = color_distance(strip_lab, blank_lab)
    margin = abs(d_target - d_blank)

    if min(d_target, d_blank) > max_distance:
        return "INCONCLUSIVE", d_target, d_blank, margin, "far from both reference colours"
    if margin < min_margin:
        return "INCONCLUSIVE", d_target, d_blank, margin, "too close to call"
    if d_target < d_blank:
        return "POSITIVE", d_target, d_blank, margin, "closest to target colour"
    return "NEGATIVE", d_target, d_blank, margin, "closest to unreacted (blank) colour"


# --- 4 quality gate ---------------------------------------------------------
def is_blurry(gray_image, threshold=BLUR_THRESHOLD):
    variance = cv2.Laplacian(gray_image, cv2.CV_64F).var()
    return bool(variance < threshold), float(variance)


def has_glare(gray_image, brightness_thresh=GLARE_BRIGHTNESS, area_thresh=GLARE_AREA):
    bright_fraction = np.mean(gray_image > brightness_thresh)
    return bool(bright_fraction > area_thresh), float(bright_fraction)


def _gate_gray(image_bgr):
    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    if w > GATE_WIDTH:  # make the blur measure resolution-independent
        gray = cv2.resize(gray, (GATE_WIDTH, int(h * GATE_WIDTH / w)),
                          interpolation=cv2.INTER_AREA)
    return gray


# --- 5 finding the card -----------------------------------------------------
def find_card(gray_image):
    edges = cv2.Canny(gray_image, 50, 150)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return None
    card_contour = max(contours, key=cv2.contourArea)
    return cv2.boundingRect(card_contour)  # (x, y, w, h)


def _aspect_ok(w, h):
    return abs((w / h) / card.BOARD_ASPECT - 1) <= 0.25


def locate_board(image_bgr, source):
    """Return the board crop (BGR) or None.

    source='guide': the client already cropped to the on-screen alignment
    frame, so the whole image is the board. source='file': (1) look for the
    thick black border as the largest dark blob; (2) if that fails and the
    image itself has the card's proportions, assume it was already cropped to
    the card; (3) otherwise give up.
    """
    if source == "guide":
        return image_bgr
    ih, iw = image_bgr.shape[:2]
    gray = cv2.GaussianBlur(cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY), (5, 5), 0)
    dark = (gray < 35).astype(np.uint8)
    n, _, stats, _ = cv2.connectedComponentsWithStats(dark, connectivity=8)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        x, y, w, h = (int(v) for v in stats[k, :4])
        if w * h >= MIN_CARD_AREA_FRACTION * iw * ih and _aspect_ok(w, h):
            return image_bgr[y:y + h, x:x + w]
    if _aspect_ok(iw, ih):
        return image_bgr
    return None


# --- full pipeline ----------------------------------------------------------
def _invalid(reason, **extra):
    r = {"outcome": "INVALID_CAPTURE", "reject_reason": reason,
         "distance_to_target": None, "distance_to_blank": None,
         "margin": None, "fit_residual": None, "detail": reason,
         "corrected_bgr": None}
    r.update(extra)
    return r


def analyze(image_bgr, profile, source="guide"):
    """Run the whole pipeline on a decoded photo. Never classifies a rejected photo."""
    gray = _gate_gray(image_bgr)
    blurry, blur_var = is_blurry(gray)
    if blurry:
        return _invalid("photo too blurry, retake", blur_variance=blur_var)
    glare, frac = has_glare(gray)
    if glare:
        return _invalid("too much glare, retake", glare_fraction=frac)

    board = locate_board(image_bgr, source)
    if board is None or min(board.shape[:2]) < 100:
        return _invalid("reference card not fully visible")
    rgb = cv2.cvtColor(board, cv2.COLOR_BGR2RGB)
    bh, bw = rgb.shape[:2]

    boxes = card.patch_boxes(bw, bh)
    observed, true = [], []
    for name in card.VALIDATED:
        med, clipped = sample_patch(rgb, boxes[name])
        if clipped > MAX_CLIPPED_FRACTION:
            return _invalid("photo overexposed on the reference card, retake")
        observed.append(srgb_to_linear(med))
        true.append(srgb_to_linear(np.array(card.PATCH_TRUE_SRGB[name]) / 255.0))

    try:
        M = fit_correction(observed, true)
    except ValueError:
        return _invalid("reference card colours not readable, retake")

    residual = float(np.mean([
        color_distance(to_lab(apply_correction(M, o)), to_lab(t))
        for o, t in zip(observed, true)
    ]))
    if residual > MAX_FIT_RESIDUAL:
        return _invalid("could not calibrate colours from the card, retake",
                        fit_residual=residual)

    strip_med, strip_clipped = sample_patch(rgb, card.strip_box(bw, bh))
    if strip_clipped > MAX_CLIPPED_FRACTION:
        return _invalid("test strip overexposed, retake", fit_residual=residual)
    strip_lab = to_lab(apply_correction(M, srgb_to_linear(strip_med)))

    outcome, d_t, d_b, margin, why = decide(
        strip_lab, profile["target_lab"], profile["blank_lab"],
        profile["max_distance"], profile["min_margin"])
    corrected = cv2.cvtColor(apply_correction_image(M, rgb), cv2.COLOR_RGB2BGR)
    return {"outcome": outcome, "reject_reason": None,
            "distance_to_target": d_t, "distance_to_blank": d_b,
            "margin": margin, "fit_residual": residual, "detail": why,
            "corrected_bgr": corrected, "strip_lab": strip_lab.tolist()}
