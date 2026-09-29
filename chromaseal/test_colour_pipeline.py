import numpy as np
import pytest

import colour_pipeline as cp
import reference_card as card
import synth
from kit_profiles import KIT_PROFILES

PROFILE = KIT_PROFILES["marquis_mdma_v1"]


def test_fit_rejects_neutrals_only():
    greys = np.array([[0.9] * 3, [0.5] * 3, [0.1] * 3, [0.3] * 3])
    with pytest.raises(ValueError, match="span enough"):
        cp.fit_correction(greys * 0.7, greys)


def test_fit_needs_four_patches():
    with pytest.raises(ValueError):
        cp.fit_correction(np.eye(3), np.eye(3))


def test_held_out_colour_improves_after_correction():
    A = np.array([[0.6, 0.10, 0.0], [0.05, 0.5, 0.08], [0.0, 0.12, 0.4]])
    true = np.array([[0.9, 0.9, 0.9], [0.2, 0.2, 0.2], [0.7, 0.05, 0.05],
                     [0.05, 0.6, 0.05], [0.05, 0.05, 0.7], [0.5, 0.5, 0.5]])
    M = cp.fit_correction(true @ A.T + 0.01, true)
    held_true = np.array([0.5, 0.2, 0.6])          # not used in the fit
    held_obs = held_true @ A.T + 0.01
    before = cp.color_distance(cp.to_lab(held_obs), cp.to_lab(held_true))
    after = cp.color_distance(cp.to_lab(cp.apply_correction(M, held_obs)), cp.to_lab(held_true))
    assert after < before / 5


def test_srgb_linear_round_trip():
    x = np.linspace(0, 1, 11)
    assert np.allclose(cp.linear_to_srgb(cp.srgb_to_linear(x)), x)


def test_decision_rule_four_behaviours():
    t, b = PROFILE["target_lab"], PROFILE["blank_lab"]
    near_t = t + np.array([2, 1, -1])
    near_b = b + np.array([-2, 1, 1])
    assert cp.decide(near_t, t, b)[0] == "POSITIVE"
    assert cp.decide(near_b, t, b)[0] == "NEGATIVE"
    mid = (t + b) / 2
    o, _, _, margin, why = cp.decide(mid, t, b, max_distance=100)
    assert o == "INCONCLUSIVE" and margin < 5 and "close" in why
    far = np.array([60.0, 70.0, 60.0])
    o, _, _, _, why = cp.decide(far, t, b)
    assert o == "INCONCLUSIVE" and "far" in why


@pytest.mark.parametrize("light", list(synth.LIGHTS))
@pytest.mark.parametrize("strip,expected", [("positive", "POSITIVE"),
                                            ("unreacted", "NEGATIVE"),
                                            ("intermediate", "INCONCLUSIVE")])
def test_same_strip_same_result_under_every_light(strip, expected, light):
    r = cp.analyze(synth.photograph(strip, light), PROFILE)
    assert r["outcome"] == expected, r


def test_blurred_photo_is_invalid():
    r = cp.analyze(synth.photograph(blur=6), PROFILE)
    assert r["outcome"] == "INVALID_CAPTURE" and "blurry" in r["reject_reason"]


def test_glare_photo_is_invalid():
    r = cp.analyze(synth.photograph(light="flashlight", exposure=1.6), PROFILE)
    assert r["outcome"] == "INVALID_CAPTURE" and "glare" in r["reject_reason"]


def test_missing_card_is_invalid():
    import cv2
    blank = np.full((600, 960, 3), 90, np.uint8)
    blank = cv2.circle(blank, (400, 300), 200, (30, 200, 30), -1)
    r = cp.analyze(blank, PROFILE, source="file")
    assert r["outcome"] == "INVALID_CAPTURE"


def test_contour_fallback_finds_board_on_table():
    r = cp.analyze(synth.photograph("positive", "warm_lamp", margin=120), PROFILE, source="file")
    assert r["outcome"] == "POSITIVE"
