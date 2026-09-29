"""PDF report for one record. Uses reportlab (an addition to the brief's original requirements list)."""
import io
import os
from datetime import datetime, timezone
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.platypus import Image, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

OUTCOME_COLOURS = {"POSITIVE": "#b3261e", "NEGATIVE": "#1e7a3c",
                   "INCONCLUSIVE": "#a86a00", "INVALID_CAPTURE": "#555555"}
CHECK_LABELS = [("image_intact", "Image intact (photo matches its SHA-256)"),
                ("record_intact", "Record intact (fields match the sealed hash)"),
                ("chain_linked", "Chain linked (points at previous record's current contents)")]


def _p(text, style):
    return Paragraph(escape(str(text)), style)


def _img(path, max_w, max_h):
    if not path or not os.path.exists(path):
        return None
    w, h = ImageReader(path).getSize()
    s = min(max_w / w, max_h / h)
    return Image(path, width=w * s, height=h * s)


def build_report(record_id, fields, hashes, checks, raw_path, corrected_path, prev_id=None):
    """Return PDF bytes. `hashes` = dict(record_hash, prev_hash, image_hash)."""
    ss = getSampleStyleSheet()
    body = ParagraphStyle("b", parent=ss["BodyText"], fontSize=9.5, leading=13)
    small = ParagraphStyle("s", parent=body, fontSize=8, leading=10)
    mono = ParagraphStyle("m", parent=small, fontName="Courier", fontSize=7.5, leading=9.5)
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=12, spaceBefore=10, spaceAfter=4)
    f = fields
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm,
                            topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"ChromaSeal report {f['test_id']}", author="ChromaSeal")
    S = []
    S.append(Paragraph("ChromaSeal — Field Test Report", ss["Title"]))
    S.append(Paragraph("<b>PRESUMPTIVE RESULT ONLY.</b> This tool removes human-reading and lighting error from "
                       "colorimetric tests. It cannot fix chemical cross-reactivity (some legal substances give the "
                       "same colour as illegal ones) and is not a substitute for laboratory confirmation.", body))
    S.append(Spacer(1, 6))

    colour = OUTCOME_COLOURS.get(f["outcome"], "#333333")
    S.append(Paragraph(f'Outcome: <font color="{colour}"><b>{escape(f["outcome"].replace("_", " "))}</b></font>',
                       ParagraphStyle("o", parent=ss["Heading1"], fontSize=18)))
    if f["reject_reason"]:
        S.append(_p(f"Reason: {f['reject_reason']}. No classification was attempted on this photo.", body))

    def num(v, fmt):
        return "n/a" if v is None else format(v, fmt)

    if f["gps_status"] == "available":
        gps = f"{f['gps_lat']:.6f}, {f['gps_lon']:.6f}"
        gps_link = f"https://www.openstreetmap.org/?mlat={f['gps_lat']}&mlon={f['gps_lon']}#map=17/{f['gps_lat']}/{f['gps_lon']}"
        gps_cell = Paragraph(f'{escape(gps)}<br/><font size="7" color="#3b3f9e"><link href="{gps_link}">Open in OpenStreetMap</link></font>', body)
    else:
        gps_cell = _p("Unavailable (not provided by the device at capture time)", body)

    rows = [
        ["Record number", f"#{record_id}"], ["Test ID", f["test_id"]],
        ["Operator ID", f["operator_id"]], ["Captured (UTC)", f["timestamp_utc"]],
        ["GPS location", gps_cell], ["Kit profile", f["kit_profile"]],
        ["Distance to target colour (ΔE2000)", num(f["distance_to_target"], ".1f")],
        ["Distance to unreacted colour (ΔE2000)", num(f["distance_to_blank"], ".1f")],
        ["Margin", num(f["margin"], ".1f")],
        ["Calibration residual (ΔE2000)", num(f["fit_residual"], ".2f")],
    ]
    rows = [[_p(k, body), v if not isinstance(v, str) else _p(v, body)] for k, v in rows]
    t = Table(rows, colWidths=[62 * mm, 112 * mm])
    t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ccd4")),
                           ("BACKGROUND", (0, 0), (0, -1), colors.HexColor("#f0f1f6")),
                           ("VALIGN", (0, 0), (-1, -1), "TOP")]))
    S.append(t)

    imgs = [(_img(raw_path, 82 * mm, 48 * mm), "Original photo"),
            (_img(corrected_path, 82 * mm, 48 * mm), "Lighting-corrected")]
    top = [i for i, _ in imgs if i]
    if top:
        cap = [_p(c, small) for i, c in imgs if i]
        it = Table([top, cap], colWidths=[87 * mm] * len(top))
        it.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP")]))
        S.append(KeepTogether([Paragraph("Images", h2), it]))

    seal = [Paragraph("Tamper-evidence seal", h2)]
    ck = [[_p(label, body), Paragraph(f'<font color="{"#1e7a3c" if checks[k] else "#b3261e"}"><b>{"PASS" if checks[k] else "FAIL"}</b></font>', body)]
          for k, label in CHECK_LABELS]
    ct = Table(ck, colWidths=[140 * mm, 34 * mm])
    ct.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c8ccd4"))]))
    seal.append(ct)
    seal.append(Spacer(1, 4))
    seal.append(_p("Record hash (SHA-256)", small)); seal.append(_p(hashes["record_hash"], mono))
    seal.append(_p(f"Previous hash{' (record #%d)' % prev_id if prev_id else ' (genesis)'}", small)); seal.append(_p(hashes["prev_hash"], mono))
    seal.append(_p("Image hash (SHA-256)", small)); seal.append(_p(hashes["image_hash"], mono))
    seal.append(Spacer(1, 4))
    seal.append(_p("A hash chain makes tampering detectable, not impossible: someone with full database access could "
                   "edit a record and recompute every later hash. To anchor this record externally, keep this printed "
                   "record hash with the case file.", small))
    S.append(KeepTogether(seal))
    S.append(Spacer(1, 6))
    S.append(_p("Report generated " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%SZ") +
                ". The verification status above was computed at generation time.", small))
    doc.build(S)
    return buf.getvalue()
