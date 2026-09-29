"""Kit profiles: target (reacted) and blank (unreacted) reference colours.

All colour values here are PLACEHOLDER ESTIMATES derived from published colour
descriptions (Marquis + MDMA/MDA: instant purple to purple-black), not lab
measurements. Thresholds must be tuned from real swatch photos.
"""
import numpy as np

from colour_pipeline import srgb_uint8_to_lab
from reference_card import PATCH_TRUE_SRGB



def build_profiles():
    """Built from the card's current true values (nominal, or the saved per-card calibration)."""
    return {
        "marquis_mdma_v1": {
            "label": "Marquis reagent / MDMA (mock swatches)",
            "target_lab": srgb_uint8_to_lab(PATCH_TRUE_SRGB["reagent_positive"]),
            "blank_lab": srgb_uint8_to_lab(PATCH_TRUE_SRGB["reagent_pale"]),
            "max_distance": 20.0,   # placeholder
            "min_margin": 5.0,      # placeholder
        },
    }


KIT_PROFILES = build_profiles()
DEFAULT_PROFILE = "marquis_mdma_v1"
