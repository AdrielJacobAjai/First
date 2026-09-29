"""Reference card ("board") definition: nine patches plus a strip window.

The board is a black-bordered matte card. Its top part holds nine patches in
three groups of three (neutrals, primaries, reagent outcomes); its lower part
has an empty window where the mock test strip is placed. All geometry is given
as fractions of the board rectangle so the same layout works at any resolution.

TRUE VALUES: neutrals and primaries are nominal sRGB values (colour-checker
style). The three reagent patches are PLACEHOLDER ESTIMATES: printed patches
should be re-measured with the daylight-averaging procedure (brief section 6)
and these numbers replaced. This is a disclosed approximation, not
spectrophotometer-grade.
"""

BOARD_ASPECT = 1.6  # width / height

PATCH_ORDER = [
    "neutral_white", "neutral_grey", "neutral_black",
    "primary_red", "primary_green", "primary_blue",
    "reagent_pale", "reagent_intermediate", "reagent_positive",
]
VALIDATED = PATCH_ORDER[:6]   # used for the correction fit
REAGENT = PATCH_ORDER[6:]     # estimates: never used to fit

PATCH_TRUE_SRGB = {
    "neutral_white": (243, 243, 242),
    "neutral_grey": (122, 122, 121),
    "neutral_black": (52, 52, 52),
    "primary_red": (175, 54, 60),
    "primary_green": (70, 148, 73),
    "primary_blue": (56, 61, 150),
    "reagent_pale": (232, 224, 200),          # placeholder estimate
    "reagent_intermediate": (120, 72, 130),   # placeholder estimate
    "reagent_positive": (40, 22, 52),         # placeholder estimate
}

# --- per-card calibration -----------------------------------------------------
# A printer never reproduces the nominal values above, so each PRINTED card should be measured
# once (admin page "Calibration", or `python calibrate_card.py photos...`). The result is stored in
# card_calibration.json and overrides the nominal values for every patch it contains.
import json
import os

NOMINAL_SRGB = dict(PATCH_TRUE_SRGB)
CALIBRATION_PATH = os.environ.get(
    "CHROMASEAL_CARD_CAL", os.path.join(os.path.dirname(os.path.abspath(__file__)), "card_calibration.json"))
CALIBRATION_INFO = None
_loaded_mtime = "unset"


def _mtime(path):
    try:
        return os.path.getmtime(path)
    except OSError:
        return None


def load_calibration(path=None):
    """Apply a saved card calibration over the nominal values. Returns its metadata or None."""
    global CALIBRATION_INFO, _loaded_mtime
    path = path or CALIBRATION_PATH
    PATCH_TRUE_SRGB.update(NOMINAL_SRGB)
    _loaded_mtime = _mtime(path)
    if _loaded_mtime is None:
        CALIBRATION_INFO = None
        return None
    with open(path) as fh:
        data = json.load(fh)
    for name, rgb in data["patches"].items():
        if name in PATCH_TRUE_SRGB:
            PATCH_TRUE_SRGB[name] = tuple(int(round(v)) for v in rgb)
    CALIBRATION_INFO = {k: v for k, v in data.items() if k != "patches"}
    return CALIBRATION_INFO


def save_calibration(patches, meta, path=None):
    """Write a calibration file (atomically) and apply it immediately."""
    path = path or CALIBRATION_PATH
    tmp = path + ".tmp"
    with open(tmp, "w") as fh:
        json.dump({**meta, "patches": patches}, fh, indent=2)
    os.replace(tmp, path)
    load_calibration(path)


def reset_calibration(path=None):
    path = path or CALIBRATION_PATH
    if os.path.exists(path):
        os.remove(path)
    load_calibration(path)


def sync_calibration():
    """Reload if the file changed on disk (another worker saved it). True if values were reloaded."""
    if _mtime(CALIBRATION_PATH) != _loaded_mtime:
        load_calibration()
        return True
    return False


load_calibration()

# Layout, fractions of the board (x, y, w, h)
_ROW_X0, _ROW_X1 = 0.06, 0.94
_ROW_Y, _ROW_H = 0.10, 0.34
_GAP = 0.008
# Black border thickness that is visible around the paper, as a fraction of the board height
BORDER_INSET_H = 0.035
STRIP_WINDOW = (0.30, 0.56, 0.40, 0.32)


def patch_boxes(board_w, board_h):
    """Pixel boxes (x, y, w, h) for each patch, keyed by name."""
    n = len(PATCH_ORDER)
    pw = (_ROW_X1 - _ROW_X0 - _GAP * (n - 1)) / n
    boxes = {}
    for i, name in enumerate(PATCH_ORDER):
        fx = _ROW_X0 + i * (pw + _GAP)
        boxes[name] = _to_px((fx, _ROW_Y, pw, _ROW_H), board_w, board_h)
    return boxes


def strip_box(board_w, board_h):
    return _to_px(STRIP_WINDOW, board_w, board_h)


def _to_px(frac, w, h):
    fx, fy, fw, fh = frac
    return (int(fx * w), int(fy * h), int(fw * w), int(fh * h))
