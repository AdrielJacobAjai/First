import copy
import json

import cv2
import numpy as np
import pytest

import calibrate_card
import colour_pipeline as cp
import kit_profiles
import reference_card as card
import synth


@pytest.fixture()
def restore_card():
    saved = copy.deepcopy(card.PATCH_TRUE_SRGB)
    yield
    card.PATCH_TRUE_SRGB.clear()
    card.PATCH_TRUE_SRGB.update(saved)
    card.CALIBRATION_INFO = None


def printed_card():
    """A printer that shifts every colour differently (gamut loss), modelled on a real inkjet print:
    red goes pink, green goes teal, blacks go grey. Not a transform the lighting fit can absorb."""
    return {
        "neutral_white": (236, 236, 232), "neutral_grey": (150, 152, 150), "neutral_black": (75, 75, 78),
        "primary_red": (178, 110, 130), "primary_green": (110, 165, 140), "primary_blue": (90, 120, 190),
        "reagent_pale": (225, 225, 205), "reagent_intermediate": (135, 120, 180),
        "reagent_positive": (75, 80, 105),
    }


def test_uncalibrated_printed_card_is_rejected_then_calibration_fixes_it(tmp_path, restore_card):
    printed = printed_card()
    strip = printed["reagent_positive"]
    photo = synth.photograph(light="warm_lamp", patches=printed, strip_rgb=strip)
    assert cp.analyze(photo, kit_profiles.build_profiles()["marquis_mdma_v1"])["outcome"] == "INVALID_CAPTURE"

    paths = []
    for i, seed in enumerate((1, 2, 3)):                       # 'even daylight' calibration photos
        p = tmp_path / f"cal{i}.png"
        cv2.imwrite(str(p), synth.photograph(light="daylight", patches=printed, seed=seed))
        paths.append(str(p))
    out = tmp_path / "cal.json"
    import sys
    sys.argv = ["calibrate_card.py", *paths, "--out", str(out)]
    calibrate_card.main()
    card.load_calibration(str(out))
    profile = kit_profiles.build_profiles()["marquis_mdma_v1"]

    for light in synth.LIGHTS:
        r = cp.analyze(synth.photograph(light=light, patches=printed, strip_rgb=strip), profile)
        assert r["outcome"] == "POSITIVE", (light, r["reject_reason"])
    pale = cp.analyze(synth.photograph(light="tubelight", patches=printed, strip_rgb=printed["reagent_pale"]), profile)
    assert pale["outcome"] == "NEGATIVE"


def test_calibration_file_overrides_only_listed_patches(tmp_path, restore_card):
    f = tmp_path / "c.json"
    f.write_text(json.dumps({"created_utc": "x", "patches": {"primary_red": [10.4, 20.6, 30]}}))
    info = card.load_calibration(str(f))
    assert card.PATCH_TRUE_SRGB["primary_red"] == (10, 21, 30) and info["created_utc"] == "x"
    assert card.PATCH_TRUE_SRGB["primary_blue"] == (56, 61, 150)


def test_missing_calibration_file_is_fine(tmp_path, restore_card):
    assert card.load_calibration(str(tmp_path / "nope.json")) is None
