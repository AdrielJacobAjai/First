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


def test_file_already_cropped_to_card_without_full_border():
    import cv2
    img = synth.photograph("positive", "shade")
    cropped = img[:-30, 30:]          # border partly cut off on two sides
    assert cp.analyze(cropped, PROFILE, source="file")["outcome"] == "POSITIVE"


@pytest.mark.parametrize("name,kw", [
    ("tilted", dict(angle=15)), ("seen at an angle", dict(angle=5, skew=0.15)),
    ("phone in portrait", dict(quarter_turns=1)), ("upside down", dict(angle=180)),
    ("white desk", dict(angle=8, bg=(235, 235, 235))), ("dark table", dict(angle=8, bg=(20, 20, 20))),
    ("black table, rotated", dict(quarter_turns=3, angle=10, bg=(5, 5, 5))),
    ("printer-grey border", dict(angle=10, border_grey=70)), ("card small in frame", dict(fill=0.35, angle=12)),
])
@pytest.mark.parametrize("light", ["warm_lamp", "shade"])
def test_card_found_in_real_world_scenes(name, kw, light):
    photo = synth.in_scene(synth.photograph("positive", light), **kw)
    r = cp.analyze(photo, PROFILE, source="file")
    assert r["outcome"] == "POSITIVE", (name, r["reject_reason"])


def test_no_card_in_scene_is_rejected_with_clear_message():
    import cv2
    rng = np.random.default_rng(0)
    scene = np.clip(120 + rng.normal(0, 25, (1200, 1600, 3)), 0, 255).astype(np.uint8)   # textured, sharp
    cv2.rectangle(scene, (300, 300), (900, 800), (30, 30, 30), -1)     # a dark box that is not the card
    r = cp.analyze(scene, PROFILE, source="file")
    assert r["outcome"] == "INVALID_CAPTURE" and "whole reference card" in r["reject_reason"]


@pytest.mark.parametrize("kw", [dict(), dict(angle=-12, skew=0.1), dict(angle=8, quarter_turns=1), dict(angle=180)])
@pytest.mark.parametrize("light", ["warm_lamp", "tubelight", "shade"])
def test_home_print_without_thick_border_on_wood_table(light, kw):
    """A home print (hairline outline, white page margin, no black band) on a bright wooden table."""
    r = cp.analyze(synth.print_photo(light=light, **kw), PROFILE, source="file")
    assert r["outcome"] == "POSITIVE", r["reject_reason"]


def test_calibration_measures_home_print_photos():
    import calibrate_card as cc
    runs = [cc.measure_image(synth.print_photo(light="daylight", seed=s, angle=a)) for s, a in ((1, 3), (2, -6), (3, 10))]
    patches, spread = cc.combine(runs)
    assert spread < 3
    assert all(abs(patches[n][i] - card.PATCH_TRUE_SRGB[n][i]) < 4 for n in card.PATCH_ORDER for i in range(3))


def _card_with(**overrides):
    p = dict(card.PATCH_TRUE_SRGB)
    p.update(overrides)
    return p


def test_clipped_white_patch_is_dropped_from_fit_not_fatal(monkeypatch):
    monkeypatch.setattr(cp, "has_glare", lambda g: (False, 0.0))     # isolate the patch-clipping rule
    photo = synth.photograph("positive", "warm_lamp", patches=_card_with(neutral_white=(255, 255, 255)))
    r = cp.analyze(photo, PROFILE)
    assert r["outcome"] == "POSITIVE", r["reject_reason"]
    assert r["dropped_patches"] == ["neutral_white"]


def test_two_clipped_patches_is_rejected_as_overexposed(monkeypatch):
    monkeypatch.setattr(cp, "has_glare", lambda g: (False, 0.0))
    photo = synth.photograph("positive", "daylight",
                             patches=_card_with(neutral_white=(255, 255, 255), primary_green=(70, 255, 73)))
    r = cp.analyze(photo, PROFILE)
    assert r["outcome"] == "INVALID_CAPTURE" and "overexposed" in r["reject_reason"]


def test_clipped_strip_is_still_rejected(monkeypatch):
    monkeypatch.setattr(cp, "has_glare", lambda g: (False, 0.0))
    photo = synth.photograph(strip_rgb=(255, 255, 255))
    r = cp.analyze(photo, PROFILE)
    assert r["outcome"] == "INVALID_CAPTURE" and "strip overexposed" in r["reject_reason"]
