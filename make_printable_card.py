"""Write printable_card.png: the reference board with labelled patches and an empty strip slot.

Print at ~16 x 10 cm on matte paper (no scaling to 'fit', no colour enhancement), laminate matte.
Printed colours will not match the stored true values exactly; see README (metamerism).
"""
import cv2

import reference_card as card
import synth

W, H = 1920, 1200  # 2x the analysis size: prints sharply


def main(out="printable_card.png"):
    img = cv2.resize(synth.render_board(synth.PAPER), (W, H), interpolation=cv2.INTER_NEAREST)
    bgr = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    for i, name in enumerate(card.PATCH_ORDER):
        x, y, w, h = card.patch_boxes(W, H)[name]
        label = f"{i + 1}"
        cv2.putText(bgr, label, (x + w // 2 - 12, y + h + 55), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (60, 60, 60), 3)
    x, y, w, h = card.strip_box(W, H)
    cv2.rectangle(bgr, (x - 6, y - 6), (x + w + 6, y + h + 6), (60, 60, 60), 4)  # outside sampled area
    cv2.putText(bgr, "PLACE STRIP HERE", (x + w // 2 - 210, y + h + 70), cv2.FONT_HERSHEY_SIMPLEX, 1.4, (60, 60, 60), 3)
    cv2.imwrite(out, bgr)


if __name__ == "__main__":
    main()
