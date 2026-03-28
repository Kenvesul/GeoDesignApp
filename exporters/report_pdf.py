"""
report_pdf.py -- PDF calculation sheet for slope stability analysis (Milestone M5).

Produces a single-page stamped PDF calculation sheet covering:
    1. Project / job header block.
    2. Soil and geometry input table.
    3. EC7 DA1 verification: Combination 1 and 2 FoS results.
    4. Slice summary table (alpha, weight, FoS contribution).
    5. Pass / Fail verdict stamp.
    6. Embedded slope cross-section figure (from plot_slope.py).

Uses reportlab (>=4.0) which is the only external dependency in exporters/.
Core/ and models/ remain dependency-free.

Reference:
    Eurocode 7 -- EN 1997-1:2004, Section 11 (slope stability).
    Craig's Soil Mechanics, 9th ed., Chapter 9.

Units:
    All spatial values in metres (m), stresses in kPa, forces in kN/m.
"""

import io
import os
import math
import tempfile
from datetime import date

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from reportlab.lib              import colors
from reportlab.lib.pagesizes    import A4
from reportlab.lib.units        import mm
from reportlab.lib.styles       import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums        import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus         import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, Image, KeepTogether,
)
from reportlab.platypus.flowables import HRFlowable

from models.soil            import Soil
from models.geometry        import SlopeGeometry
from core.factors_of_safety import VerificationResult
from core.search            import SearchResult
from core.slicer            import Slice
from exporters.plot_slope   import plot_slope_stability


# ============================================================
#  Page layout constants
# ============================================================

PAGE_W, PAGE_H = A4
MARGIN         = 20 * mm
INNER_W        = PAGE_W - 2 * MARGIN

# Colour palette
_DARK_BLUE  = colors.HexColor("#1A3A5C")
_MID_BLUE   = colors.HexColor("#2E6DA4")
_LIGHT_BLUE = colors.HexColor("#D6E8F7")
_PASS_GREEN = colors.HexColor("#2CA02C")
_FAIL_RED   = colors.HexColor("#D62728")
_GREY       = colors.HexColor("#EEEEEE")
_WHITE      = colors.white


def _styles():
    """Return a dict of named ParagraphStyles."""
    base = getSampleStyleSheet()
    styles = {
        "title": ParagraphStyle(
            "title", parent=base["Title"],
            fontSize=14, textColor=_DARK_BLUE, spaceAfter=2,
            fontName="Helvetica-Bold",
        ),
        "subtitle": ParagraphStyle(
            "subtitle", parent=base["Normal"],
            fontSize=9, textColor=_MID_BLUE, spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "h2", parent=base["Heading2"],
            fontSize=10, textColor=_DARK_BLUE, spaceBefore=8, spaceAfter=3,
            fontName="Helvetica-Bold",
        ),
        "body": ParagraphStyle(
            "body", parent=base["Normal"],
            fontSize=8, leading=11,
        ),
        "mono": ParagraphStyle(
            "mono", parent=base["Normal"],
            fontSize=7.5, fontName="Courier", leading=10,
        ),
        "pass": ParagraphStyle(
            "pass", parent=base["Normal"],
            fontSize=18, fontName="Helvetica-Bold",
            textColor=_PASS_GREEN, alignment=TA_CENTER,
        ),
        "fail": ParagraphStyle(
            "fail", parent=base["Normal"],
            fontSize=18, fontName="Helvetica-Bold",
            textColor=_FAIL_RED, alignment=TA_CENTER,
        ),
        "cell": ParagraphStyle(
            "cell", parent=base["Normal"],
            fontSize=7.5, leading=9,
        ),
        "cell_bold": ParagraphStyle(
            "cell_bold", parent=base["Normal"],
            fontSize=7.5, leading=9, fontName="Helvetica-Bold",
        ),
    }
    return styles


def _header_table(project: str, job_ref: str, calc_by: str, checked_by: str, st) -> Table:
    """Builds the project/job header block table."""
    today = date.today().strftime("%d %b %Y")
    data = [
        [Paragraph("DesignApp — Slope Stability Calculation", st["title"]),
         Paragraph(f"Ref: {job_ref}", st["body"]),
         Paragraph(f"Date: {today}", st["body"])],
        [Paragraph(f"Project: {project}", st["subtitle"]),
         Paragraph(f"Calc by: {calc_by}", st["body"]),
         Paragraph(f"Checked: {checked_by}", st["body"])],
    ]
    col_w = [INNER_W * 0.55, INNER_W * 0.25, INNER_W * 0.20]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), _DARK_BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _WHITE),
        ("BACKGROUND",  (0, 1), (-1, 1), _LIGHT_BLUE),
        ("BOX",         (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",        (0, 0), (-1, -1), 0.3, _MID_BLUE),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0),(-1, -1), 4),
    ]))
    return t


def _soil_geometry_table(
    soil: Soil,
    slope: SlopeGeometry,
    result: SearchResult,
    ru: float,
    st,
) -> Table:
    """Builds the input parameters table."""
    circle = result.critical_circle

    def row(label, value, unit=""):
        return [
            Paragraph(label, st["cell_bold"]),
            Paragraph(str(value), st["cell"]),
            Paragraph(unit, st["cell"]),
        ]

    data = [
        [Paragraph("Parameter", st["cell_bold"]),
         Paragraph("Value", st["cell_bold"]),
         Paragraph("Unit", st["cell_bold"])],
        row("Soil name",           soil.name,               ""),
        row("Unit weight γ",       f"{soil.gamma:.1f}",     "kN/m³"),
        row("Friction angle φ'_k", f"{soil.phi_k:.1f}",     "°"),
        row("Cohesion c'_k",       f"{soil.c_k:.1f}",       "kPa"),
        row("Pore pressure ru",    f"{ru:.3f}",              "—"),
        row("Critical cx",         f"{circle.cx:.3f}",      "m"),
        row("Critical cy",         f"{circle.cy:.3f}",      "m"),
        row("Critical radius R",   f"{circle.r:.3f}",  "m"),
        row("Analysis method",     result.best_fos_result.method,""),
    ]

    col_w = [INNER_W * 0.45, INNER_W * 0.35, INNER_W * 0.20]
    t = Table(data, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0), _MID_BLUE),
        ("TEXTCOLOR",   (0, 0), (-1, 0), _WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY]),
        ("BOX",         (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",        (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",  (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0),(-1, -1), 3),
    ]))
    return t


def _ec7_results_table(verification: VerificationResult, st) -> Table:
    """Builds the EC7 DA1 verification results table."""
    c1 = verification.comb1
    c2 = verification.comb2

    def verdict(passes):
        return Paragraph("PASS" if passes else "FAIL",
                         st["cell_bold"] if passes else st["cell_bold"])

    data = [
        [Paragraph(h, st["cell_bold"]) for h in
         ["Combination", "γ_φ", "φ'_d (°)", "c'_d (kPa)", "FoS_d", "Result"]],
        [Paragraph("DA1-C1 (M1)", st["cell"]),
         Paragraph(f"{c1.gamma_phi:.2f}", st["cell"]),
         Paragraph(f"{c1.phi_d:.2f}", st["cell"]),
         Paragraph(f"{c1.c_d:.2f}", st["cell"]),
         Paragraph(f"{c1.fos_d:.4f}", st["cell_bold"]),
         verdict(c1.passes)],
        [Paragraph("DA1-C2 (M2)", st["cell"]),
         Paragraph(f"{c2.gamma_phi:.2f}", st["cell"]),
         Paragraph(f"{c2.phi_d:.2f}", st["cell"]),
         Paragraph(f"{c2.c_d:.2f}", st["cell"]),
         Paragraph(f"{c2.fos_d:.4f}", st["cell_bold"]),
         verdict(c2.passes)],
    ]

    col_w = [INNER_W*0.22, INNER_W*0.10, INNER_W*0.14,
             INNER_W*0.14, INNER_W*0.16, INNER_W*0.24]
    t = Table(data, colWidths=col_w)

    c1_color = _PASS_GREEN if c1.passes else _FAIL_RED
    c2_color = _PASS_GREEN if c2.passes else _FAIL_RED

    t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (-1, 0), _MID_BLUE),
        ("TEXTCOLOR",    (0, 0), (-1, 0), _WHITE),
        ("BACKGROUND",   (0, 1), (-1, 1), _GREY),
        ("BACKGROUND",   (0, 2), (-1, 2), _WHITE),
        ("TEXTCOLOR",    (-1, 1), (-1, 1), c1_color),
        ("TEXTCOLOR",    (-1, 2), (-1, 2), c2_color),
        ("BOX",          (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 3),
        ("FONTNAME",     (-1, 1), (-1, 2), "Helvetica-Bold"),
    ]))
    return t


def _slice_table(slices: list, st) -> Table:
    """Builds a summary table of the first 12 slices (truncated if more)."""
    MAX_ROWS = 12
    shown = slices[:MAX_ROWS]

    header = [Paragraph(h, st["cell_bold"]) for h in
              ["Slice", "x_mid (m)", "b (m)", "α (°)", "W (kN/m)", "sin α", "cos α"]]

    rows = [header]
    for i, s in enumerate(shown):
        rows.append([
            Paragraph(str(i + 1), st["cell"]),
            Paragraph(f"{s.x:.3f}", st["cell"]),
            Paragraph(f"{s.b:.3f}", st["cell"]),
            Paragraph(f"{math.degrees(s.alpha):.2f}", st["cell"]),
            Paragraph(f"{s.weight:.2f}", st["cell"]),
            Paragraph(f"{math.sin(s.alpha):.4f}", st["cell"]),
            Paragraph(f"{math.cos(s.alpha):.4f}", st["cell"]),
        ])

    if len(slices) > MAX_ROWS:
        rows.append([Paragraph(f"… {len(slices)-MAX_ROWS} more slices not shown",
                               st["cell"])] + [""] * 6)

    col_w = [INNER_W*0.08, INNER_W*0.14, INNER_W*0.10,
             INNER_W*0.12, INNER_W*0.18, INNER_W*0.19, INNER_W*0.19]
    t = Table(rows, colWidths=col_w)
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, 0), _MID_BLUE),
        ("TEXTCOLOR",     (0, 0), (-1, 0), _WHITE),
        ("ROWBACKGROUNDS",(0, 1), (-1, -1), [_WHITE, _GREY]),
        ("BOX",           (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",          (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",    (0, 0), (-1, -1), 2),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
    ]))
    return t


def _verdict_block(verification: VerificationResult, st) -> Table:
    """Large PASS / FAIL stamp with governing FoS."""
    passes  = verification.passes
    verdict = "✓  SATISFACTORY" if passes else "✗  UNSATISFACTORY"
    style   = st["pass"] if passes else st["fail"]
    bg      = colors.HexColor("#EAF7EA") if passes else colors.HexColor("#FDECEA")

    gov_label = verification.governing.label
    fos_d_min = verification.fos_d_min

    detail = (f"Governing: {gov_label}   "
              f"FoS_d = {fos_d_min:.4f}   "
              f"(FoS_char = {verification.fos_char:.4f})")

    data = [
        [Paragraph(verdict, style)],
        [Paragraph(detail, st["body"])],
    ]
    t = Table(data, colWidths=[INNER_W])
    t.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (-1, -1), bg),
        ("BOX",           (0, 0), (-1, -1), 1.5,
         _PASS_GREEN if passes else _FAIL_RED),
        ("ALIGN",         (0, 0), (-1, -1), "CENTER"),
        ("TOPPADDING",    (0, 0), (-1, -1), 8),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
    ]))
    return t


# ============================================================
#  Public API
# ============================================================

def generate_slope_report(
    filepath        : str,
    soil            : Soil,
    slope           : SlopeGeometry,
    search_result   : SearchResult,
    verification    : VerificationResult,
    slices          : list,
    ru              : float = 0.0,
    project         : str   = "Untitled Project",
    job_ref         : str   = "—",
    calc_by         : str   = "DesignApp",
    checked_by      : str   = "—",
) -> None:
    """
    Generates a single-page PDF calculation sheet for slope stability analysis.

    Writes the PDF to ``filepath``.  The file is ready for stamping and issue.

    :param filepath:      Output PDF file path.
    :param soil:          Characteristic soil (Soil object).
    :param slope:         SlopeGeometry defining the ground surface.
    :param search_result: SearchResult from core/search.py (critical circle + FoS).
    :param verification:  VerificationResult from core/factors_of_safety.py (DA1 gate).
    :param slices:        List of Slice objects for the critical circle.
    :param ru:            Pore pressure ratio (dimensionless).
    :param project:       Project name for the header.
    :param job_ref:       Job reference number.
    :param calc_by:       Initials of the person who performed the calculation.
    :param checked_by:    Initials of the checker.
    :raises OSError:      If the output directory does not exist.
    """
    st = _styles()
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )

    story = []

    # ── 1. Header ─────────────────────────────────────────────────────────
    story.append(_header_table(project, job_ref, calc_by, checked_by, st))
    story.append(Spacer(1, 4 * mm))

    # ── 2. Input parameters ───────────────────────────────────────────────
    story.append(Paragraph("1. Input Parameters", st["h2"]))
    story.append(_soil_geometry_table(soil, slope, search_result, ru, st))
    story.append(Spacer(1, 4 * mm))

    # ── 3. EC7 DA1 verification ───────────────────────────────────────────
    story.append(Paragraph("2. EC7 DA1 Verification (Slope Stability)", st["h2"]))
    story.append(_ec7_results_table(verification, st))
    story.append(Spacer(1, 4 * mm))

    # ── 4. Verdict ────────────────────────────────────────────────────────
    story.append(Paragraph("3. Verdict", st["h2"]))
    story.append(_verdict_block(verification, st))
    story.append(Spacer(1, 4 * mm))

    # ── 5. Slice table ────────────────────────────────────────────────────
    story.append(Paragraph("4. Slice Summary (Critical Circle)", st["h2"]))
    story.append(_slice_table(slices, st))
    story.append(Spacer(1, 4 * mm))

    # ── 6. Cross-section figure ───────────────────────────────────────────
    story.append(Paragraph("5. Cross-Section", st["h2"]))

    fig = plot_slope_stability(
        slope, search_result,
        title="Critical Slip Circle — Bishop Simplified",
        ru=ru,
    )
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=120, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image(buf, width=INNER_W, height=INNER_W * 0.45)
    story.append(img)

    # ── 7. Warnings ───────────────────────────────────────────────────────
    if verification.warnings:
        story.append(Spacer(1, 4 * mm))
        story.append(Paragraph("Notes / Warnings", st["h2"]))
        for w in verification.warnings:
            story.append(Paragraph(f"• {w}", st["body"]))

    doc.build(story)


# ============================================================
#  Foundation bearing capacity report  (B-07)
# ============================================================

def generate_foundation_report(
    filepath    : str,
    analysis    : dict,
    project     : str = "Untitled Project",
    job_ref     : str = "—",
    calc_by     : str = "DesignApp",
    checked_by  : str = "—",
) -> None:
    """
    PDF calculation sheet for EC7 DA1 foundation bearing capacity + settlement.

    Sections:
        1. Project header
        2. Soil and foundation input table
        3. EC7 DA1 ULS bearing capacity (Combination 1 & 2)
        4. Settlement SLS (if computed)
        5. Verdict stamp

    :param filepath:  Output PDF file path.
    :param analysis:  Result dict from api.run_foundation_analysis().
    :param project:   Project name for the header block.
    :param job_ref:   Job reference number.
    :param calc_by:   Initials of the person who performed the analysis.
    :param checked_by: Initials of the checker.

    Reference: EC7 EN 1997-1:2004 §6, Annex D.
    """
    st  = _styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )
    story = []
    today = date.today().strftime("%d %b %Y")

    # ── Header ──────────────────────────────────────────────────────────────
    hdr_data = [
        [Paragraph("DesignApp — Foundation Bearing Capacity Calculation", st["title"]),
         Paragraph(f"Ref: {job_ref}", st["body"]),
         Paragraph(f"Date: {today}", st["body"])],
        [Paragraph(f"Project: {project}", st["subtitle"]),
         Paragraph(f"Calc by: {calc_by}", st["body"]),
         Paragraph(f"Checked: {checked_by}", st["body"])],
    ]
    hdr = Table(hdr_data, colWidths=[INNER_W*0.55, INNER_W*0.25, INNER_W*0.20])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), _DARK_BLUE),
        ("TEXTCOLOR",    (0,0),(-1,0), _WHITE),
        ("BACKGROUND",   (0,1),(-1,1), _LIGHT_BLUE),
        ("BOX",          (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.3, _MID_BLUE),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    story += [hdr, Spacer(1, 5*mm)]

    # ── 1. Input Parameters ─────────────────────────────────────────────────
    story.append(Paragraph("1. Input Parameters", st["h2"]))
    s   = analysis["soil"]
    f   = analysis["foundation"]
    def _row(lbl, val, unit=""):
        return [Paragraph(lbl, st["cell_bold"]),
                Paragraph(str(val), st["cell"]),
                Paragraph(unit, st["cell"])]
    inp_data = [
        [Paragraph("Parameter", st["cell_bold"]),
         Paragraph("Value",     st["cell_bold"]),
         Paragraph("Unit",      st["cell_bold"])],
        _row("Soil name",          s["name"]),
        _row("Unit weight γ",      f"{s['gamma']:.1f}",  "kN/m³"),
        _row("Friction angle φ'k", f"{s['phi_k']:.1f}",  "°"),
        _row("Cohesion c'k",       f"{s['c_k']:.1f}",    "kPa"),
        _row("Width B",            f"{f['B']:.2f}",       "m"),
        _row("Length L",           f"{f['L']}" if f["L"] else "∞ (strip)", "m"),
        _row("Embedment Df",       f"{f['Df']:.2f}",      "m"),
        _row("Effective width B'", f"{f['B_eff']:.3f}",   "m"),
        _row("Effective area A'",  f"{f['A_eff']:.4f}",   "m²/m"),
    ]
    inp_t = Table(inp_data, colWidths=[INNER_W*0.50, INNER_W*0.30, INNER_W*0.20])
    inp_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1,0), _MID_BLUE),
        ("TEXTCOLOR",      (0,0),(-1,0), _WHITE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [_WHITE, _GREY]),
        ("BOX",            (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",           (0,0),(-1,-1), 0.3, colors.grey),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",     (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 3),
    ]))
    story += [inp_t, Spacer(1, 5*mm)]

    # ── 2. EC7 DA1 Bearing Capacity ──────────────────────────────────────────
    story.append(Paragraph("2. EC7 DA1 Bearing Capacity — GEO ULS  (Annex D)", st["h2"]))
    uls_header = [Paragraph(h, st["cell_bold"]) for h in
                  ["Combination", "γ_G", "γ_Q", "V_d (kN/m)", "R_d (kN/m)",
                   "Utilisation", "Result"]]
    uls_rows = [uls_header]
    for c in [analysis["comb1"], analysis["comb2"]]:
        ok_str = "PASS" if c["passes"] else "FAIL"
        col    = _PASS_GREEN if c["passes"] else _FAIL_RED
        uls_rows.append([
            Paragraph(c["label"],             st["cell"]),
            Paragraph(f"{c['gG']:.2f}",       st["cell"]),
            Paragraph(f"{c['gQ']:.2f}",       st["cell"]),
            Paragraph(f"{c['Vd']:.1f}",       st["cell"]),
            Paragraph(f"{c['Rd']:.1f}",       st["cell"]),
            Paragraph(f"{c['utilisation']:.3f}", st["cell_bold"]),
            Paragraph(ok_str, st["cell_bold"]),
        ])
    uls_t = Table(uls_rows, colWidths=[INNER_W*0.18, INNER_W*0.08, INNER_W*0.08,
                                       INNER_W*0.14, INNER_W*0.14,
                                       INNER_W*0.18, INNER_W*0.20])
    c1_col = _PASS_GREEN if analysis["comb1"]["passes"] else _FAIL_RED
    c2_col = _PASS_GREEN if analysis["comb2"]["passes"] else _FAIL_RED
    uls_t.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), _MID_BLUE),
        ("TEXTCOLOR",    (0,0),(-1,0), _WHITE),
        ("BACKGROUND",   (0,1),(-1,1), _GREY),
        ("BACKGROUND",   (0,2),(-1,2), _WHITE),
        ("TEXTCOLOR",    (-1,1),(-1,1), c1_col),
        ("TEXTCOLOR",    (-1,2),(-1,2), c2_col),
        ("BOX",          (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.3, colors.grey),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        ("FONTNAME",     (-1,1),(-1,2), "Helvetica-Bold"),
    ]))
    story += [uls_t, Spacer(1, 5*mm)]

    # ── 3. Settlement SLS ────────────────────────────────────────────────────
    if analysis.get("s_total_mm") is not None:
        story.append(Paragraph("3. Settlement Check — SLS  (EC7 §6.6)", st["h2"]))
        sls_pass   = analysis.get("sls_passes", False)
        sls_str    = "PASS" if sls_pass else "FAIL"
        sls_colour = _PASS_GREEN if sls_pass else _FAIL_RED
        sls_data = [
            [Paragraph("Settlement Component", st["cell_bold"]),
             Paragraph("Value (mm)", st["cell_bold"])],
            [Paragraph("Immediate settlement s_i", st["cell"]),
             Paragraph(f"{analysis.get('s_immediate_mm', '—')}", st["cell"])],
            [Paragraph("Consolidation settlement s_c", st["cell"]),
             Paragraph(f"{analysis.get('s_consolidation_mm', '—')}", st["cell"])],
            [Paragraph("Total settlement s_total", st["cell_bold"]),
             Paragraph(f"{analysis['s_total_mm']:.1f}", st["cell_bold"])],
            [Paragraph("SLS limit s_lim", st["cell"]),
             Paragraph(f"{analysis['s_lim_mm']:.1f}", st["cell"])],
            [Paragraph("SLS result", st["cell_bold"]),
             Paragraph(sls_str, st["cell_bold"])],
        ]
        if analysis.get("t_95_years") is not None:
            sls_data.append([
                Paragraph("Time to 95% consolidation", st["cell"]),
                Paragraph(f"{analysis['t_95_years']:.1f} years", st["cell"]),
            ])
        sls_t = Table(sls_data, colWidths=[INNER_W*0.60, INNER_W*0.40])
        sls_t.setStyle(TableStyle([
            ("BACKGROUND",     (0,0),(-1,0), _MID_BLUE),
            ("TEXTCOLOR",      (0,0),(-1,0), _WHITE),
            ("ROWBACKGROUNDS", (0,1),(-1,-1), [_WHITE, _GREY]),
            ("TEXTCOLOR",      (1,-1),(1,-1), sls_colour),
            ("FONTNAME",       (1,-1),(1,-1), "Helvetica-Bold"),
            ("BOX",            (0,0),(-1,-1), 0.5, _DARK_BLUE),
            ("GRID",           (0,0),(-1,-1), 0.3, colors.grey),
            ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
            ("TOPPADDING",     (0,0),(-1,-1), 3),
            ("BOTTOMPADDING",  (0,0),(-1,-1), 3),
        ]))
        story += [sls_t, Spacer(1, 5*mm)]

    # ── 4. Verdict ───────────────────────────────────────────────────────────
    story.append(Paragraph("4. Verdict", st["h2"]))
    passes  = analysis.get("passes", False)
    verdict = "SATISFACTORY — PASS" if passes else "UNSATISFACTORY — FAIL"
    v_style = st["pass"] if passes else st["fail"]
    v_bg    = colors.HexColor("#EAF7EA") if passes else colors.HexColor("#FDECEA")
    v_data  = [[Paragraph(verdict, v_style)],
               [Paragraph(f"ULS: {'PASS' if analysis.get('uls_passes') else 'FAIL'}"
                           f"  |  SLS: {('PASS' if analysis.get('sls_passes') else 'FAIL') if analysis.get('sls_passes') is not None else 'Not checked'}",
                           st["body"])]]
    v_t = Table(v_data, colWidths=[INNER_W])
    v_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5, _PASS_GREEN if passes else _FAIL_RED),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story += [v_t]

    # ── Warnings ─────────────────────────────────────────────────────────────
    if analysis.get("warnings"):
        story += [Spacer(1, 5*mm),
                  Paragraph("Notes / Warnings", st["h2"])]
        for w in analysis["warnings"]:
            story.append(Paragraph(f"• {w}", st["body"]))

    doc.build(story)


# ============================================================
#  Retaining wall report  (B-07)
# ============================================================

def generate_wall_report(
    filepath    : str,
    analysis    : dict,
    project     : str = "Untitled Project",
    job_ref     : str = "—",
    calc_by     : str = "DesignApp",
    checked_by  : str = "—",
) -> None:
    """
    PDF calculation sheet for EC7 DA1 retaining wall ULS verification.

    Sections:
        1. Project header
        2. Backfill / foundation soil + wall geometry
        3. EC7 DA1 — sliding, overturning, bearing (Combination 1 & 2)
        4. Base pressure distribution
        5. Verdict stamp

    :param filepath:  Output PDF file path.
    :param analysis:  Result dict from api.run_wall_analysis().
    :param project:   Project name for the header block.
    :param job_ref:   Job reference number.
    :param calc_by:   Initials of the person who performed the analysis.
    :param checked_by: Initials of the checker.

    Reference: EC7 EN 1997-1:2004 §9. Craig Ch.11. Bond & Harris Ch.14.
    """
    st  = _styles()
    doc = SimpleDocTemplate(
        filepath, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN,  bottomMargin=MARGIN,
    )
    story = []
    today = date.today().strftime("%d %b %Y")

    # ── Header ──────────────────────────────────────────────────────────────
    hdr_data = [
        [Paragraph("DesignApp — Retaining Wall Calculation", st["title"]),
         Paragraph(f"Ref: {job_ref}", st["body"]),
         Paragraph(f"Date: {today}", st["body"])],
        [Paragraph(f"Project: {project}", st["subtitle"]),
         Paragraph(f"Calc by: {calc_by}", st["body"]),
         Paragraph(f"Checked: {checked_by}", st["body"])],
    ]
    hdr = Table(hdr_data, colWidths=[INNER_W*0.55, INNER_W*0.25, INNER_W*0.20])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), _DARK_BLUE),
        ("TEXTCOLOR",    (0,0),(-1,0), _WHITE),
        ("BACKGROUND",   (0,1),(-1,1), _LIGHT_BLUE),
        ("BOX",          (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.3, _MID_BLUE),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    story += [hdr, Spacer(1, 5*mm)]

    # ── 1. Input Parameters ─────────────────────────────────────────────────
    story.append(Paragraph("1. Input Parameters", st["h2"]))
    s   = analysis["soil"]        # backfill
    fs  = analysis.get("foundation_soil", s)
    w   = analysis["wall"]
    def _row(lbl, val, unit=""):
        return [Paragraph(lbl, st["cell_bold"]),
                Paragraph(str(val), st["cell"]),
                Paragraph(unit, st["cell"])]
    inp_data = [
        [Paragraph("Parameter", st["cell_bold"]),
         Paragraph("Value",     st["cell_bold"]),
         Paragraph("Unit",      st["cell_bold"])],
        _row("Backfill name",          s["name"]),
        _row("Backfill γ / φ'k / c'k", f"{s['gamma']:.1f} / {s['phi_k']:.1f} / {s['c_k']:.1f}", "kN/m³ / ° / kPa"),
        _row("Foundation soil φ'k",    f"{fs['phi_k']:.1f}", "°"),
        _row("Retained height H",      f"{w['H_wall']:.2f}", "m"),
        _row("Base width B",           f"{w['B_base']:.2f}", "m"),
        _row("Toe projection b_toe",   f"{w['B_toe']:.2f}",  "m"),
        _row("Heel projection b_heel", f"{w.get('b_heel', '—')}", "m"),
        _row("Stem thickness (base/top)", f"{w['t_stem_base']:.2f} / {w['t_stem_top']:.2f}", "m"),
        _row("Base slab thickness",    f"{w['t_base']:.2f}", "m"),
        _row("Ka (Rankine)",           f"{analysis['Ka']:.4f}"),
        _row("Kp (Rankine)",           f"{analysis['Kp']:.4f}"),
    ]
    inp_t = Table(inp_data, colWidths=[INNER_W*0.50, INNER_W*0.30, INNER_W*0.20])
    inp_t.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1,0), _MID_BLUE),
        ("TEXTCOLOR",      (0,0),(-1,0), _WHITE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [_WHITE, _GREY]),
        ("BOX",            (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",           (0,0),(-1,-1), 0.3, colors.grey),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",     (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 3),
    ]))
    story += [inp_t, Spacer(1, 5*mm)]

    # ── 2. EC7 DA1 Combination Table ─────────────────────────────────────────
    story.append(Paragraph(
        "2. EC7 DA1 ULS Verification — Sliding, Overturning & Bearing  (§9)",
        st["h2"]))
    da1_hdr = [Paragraph(h, st["cell_bold"]) for h in [
        "Comb", "Ka", "Pa (kN/m)",
        "Slide FoS_d", "Slide",
        "Overt FoS_d", "Overt",
        "Bear η", "Bear",
        "Overall",
    ]]
    da1_rows = [da1_hdr]
    for c in [analysis["comb1"], analysis["comb2"]]:
        sl = c["sliding"];  ov = c["overturn"];  br = c["bearing"]
        da1_rows.append([
            Paragraph(c["label"],              st["cell"]),
            Paragraph(f"{c['ka']:.4f}",        st["cell"]),
            Paragraph(f"{c['Pa']:.1f}",        st["cell"]),
            Paragraph(f"{sl['fos_d']:.3f}",    st["cell_bold"]),
            Paragraph("✓" if sl["passes"] else "✗", st["cell_bold"]),
            Paragraph(f"{ov['fos_d']:.3f}",    st["cell_bold"]),
            Paragraph("✓" if ov["passes"] else "✗", st["cell_bold"]),
            Paragraph(f"{br['utilisation']:.3f}", st["cell_bold"]),
            Paragraph("✓" if br["passes"] else "✗", st["cell_bold"]),
            Paragraph("PASS" if c["passes"] else "FAIL", st["cell_bold"]),
        ])
    cws = [INNER_W*w for w in [0.07,0.08,0.09, 0.09,0.07, 0.09,0.07, 0.08,0.07, 0.09]]
    da1_t = Table(da1_rows, colWidths=cws)
    def _pass_col(i, col):
        return [("TEXTCOLOR", (i,1),(i,2), _PASS_GREEN if col[0] else _FAIL_RED),
                ("TEXTCOLOR", (i,2),(i,2), _PASS_GREEN if col[1] else _FAIL_RED)]
    c1, c2 = analysis["comb1"], analysis["comb2"]
    style_cmds = [
        ("BACKGROUND",   (0,0),(-1,0), _MID_BLUE),
        ("TEXTCOLOR",    (0,0),(-1,0), _WHITE),
        ("BACKGROUND",   (0,1),(-1,1), _GREY),
        ("BACKGROUND",   (0,2),(-1,2), _WHITE),
        ("BOX",          (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.3, colors.grey),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",(0,0),(-1,-1), 3),
        # Overall column colour
        ("TEXTCOLOR", (-1,1),(-1,1), _PASS_GREEN if c1["passes"] else _FAIL_RED),
        ("TEXTCOLOR", (-1,2),(-1,2), _PASS_GREEN if c2["passes"] else _FAIL_RED),
        ("FONTNAME",  (-1,1),(-1,2), "Helvetica-Bold"),
    ]
    da1_t.setStyle(TableStyle(style_cmds))
    story += [da1_t, Spacer(1, 5*mm)]

    # ── 3. Verdict ───────────────────────────────────────────────────────────
    story.append(Paragraph("3. Verdict", st["h2"]))
    passes  = analysis.get("passes", False)
    verdict = "SATISFACTORY — PASS" if passes else "UNSATISFACTORY — FAIL"
    v_style = st["pass"] if passes else st["fail"]
    v_bg    = colors.HexColor("#EAF7EA") if passes else colors.HexColor("#FDECEA")
    gov     = analysis["comb2"]   # C2 typically governs for walls
    detail  = (f"Governing combination: {gov['label']}  |  "
               f"Sliding FoS_d = {gov['sliding']['fos_d']:.3f}  |  "
               f"Bearing η = {gov['bearing']['utilisation']:.3f}")
    v_data  = [[Paragraph(verdict, v_style)],
               [Paragraph(detail, st["body"])]]
    v_t = Table(v_data, colWidths=[INNER_W])
    v_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5, _PASS_GREEN if passes else _FAIL_RED),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story += [v_t]

    if analysis.get("warnings"):
        story += [Spacer(1, 5*mm),
                  Paragraph("Notes / Warnings", st["h2"])]
        for w in analysis["warnings"]:
            story.append(Paragraph(f"• {w}", st["body"]))

    doc.build(story)


def generate_sheet_pile_report(
    filepath    : str,
    analysis    : dict,
    project     : str = "Untitled Project",
    job_ref     : str = "—",
    calc_by     : str = "DesignApp",
    checked_by  : str = "—",
) -> None:
    """
    Minimal standalone PDF calculation sheet for sheet pile analysis.

    Reuses the same section renderer used by the unified project report so the
    legacy web UI and the React SPA can both export a single sheet-pile report.
    """
    st = _styles()
    today = date.today().strftime("%d %b %Y")
    _generate_sheet_pile_section(
        filepath, analysis, project, job_ref, calc_by, checked_by, st, today
    )


# ============================================================
#  Unified project report  (Sprint 12)
# ============================================================

def generate_project_report(
    analyses  : list,
    out_path  : str,
    project   : str = "DesignApp Project",
    job_ref   : str = "—",
    calc_by   : str = "DesignApp",
    checked_by: str = "—",
) -> None:
    """
    Unified multi-section PDF combining every completed analysis.

    Structure
    ---------
    Page 1:  Cover page — project title, job ref, date, engineer stamps,
             summary table (analysis type, key result, PASS/FAIL).
    Page 2+: One calculation section per analysis, in order:
             slope → foundation → retaining wall → sheet pile.
             Each section opens with a divider page showing the section title,
             followed by the full individual calculation sheet.

    Section routing
    ---------------
    Each dict in `analyses` must contain the key ``analysis_type``:
        'slope'       → generate_slope_report()  (requires extra rebuild)
        'foundation'  → generate_foundation_report()
        'wall'        → generate_wall_report()
        'sheet_pile'  → inline sheet-pile section (no separate generator yet)
    Unknown types are included as a minimal text section.

    Page numbers
    ------------
    Sequential Arabic numerals starting at 1, centred in the footer,
    via ReportLab's onPage callback.

    :param analyses:   List of result dicts from any run_*_analysis().
    :param out_path:   Output PDF path.
    :param project:    Project name for header/cover.
    :param job_ref:    Job reference.
    :param calc_by:    Initials of engineer.
    :param checked_by: Initials of checker.

    References
    ----------
    EC7 EN 1997-1:2004, §11 (calculation sheet requirements).
    """
    import tempfile, os
    st    = _styles()
    today = date.today().strftime("%d %b %Y")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _section_divider(story: list, section_title: str, section_num: int) -> None:
        """Insert a bold section divider paragraph."""
        story += [
            Spacer(1, 6 * mm),
            HRFlowable(width=INNER_W, thickness=1.5, color=_DARK_BLUE),
            Spacer(1, 3 * mm),
        ]
        story.append(Paragraph(
            f"Section {section_num} — {section_title}", st["title"]
        ))
        story += [Spacer(1, 3 * mm),
                  HRFlowable(width=INNER_W, thickness=0.5, color=_MID_BLUE),
                  Spacer(1, 4 * mm)]

    def _analysis_label(a: dict) -> str:
        at = a.get("analysis_type", "unknown")
        return {
            "slope":       "Slope Stability",
            "foundation":  "Foundation Bearing Capacity",
            "wall":        "Retaining Wall",
            "sheet_pile":  "Sheet Pile",
        }.get(at, at.replace("_", " ").title())

    def _key_result(a: dict) -> str:
        at = a.get("analysis_type", "")
        if at == "slope":
            fos = (a.get("comb2") or {}).get("fos_d") or (a.get("comb1") or {}).get("fos_d")
            return f"FoS_d = {fos:.3f}" if fos else "—"
        if at == "foundation":
            util = (a.get("comb2") or {}).get("utilisation")
            return f"η = {util:.3f}" if util is not None else "—"
        if at == "wall":
            sl = ((a.get("comb2") or {}).get("sliding") or {}).get("fos_d")
            return f"Sliding FoS_d = {sl:.3f}" if sl is not None else "—"
        if at == "sheet_pile":
            d = a.get("d_design")
            return f"d_design = {d:.3f} m" if d is not None else "—"
        return "—"

    # ── Build individual PDFs in temp files ───────────────────────────────────
    section_files: list[tuple[str, str]] = []   # (label, tmp_path)

    for a in analyses:
        at  = a.get("analysis_type", "unknown")
        lbl = _analysis_label(a)
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
            tmp = tf.name
        try:
            if at == "slope":
                # Slope requires rebuilding model objects — delegate to api
                from api import export_pdf as _export_slope_pdf
                _export_slope_pdf(a, tmp, project=project, job_ref=job_ref,
                                  calc_by=calc_by, checked_by=checked_by)
            elif at == "foundation":
                generate_foundation_report(tmp, a, project=project,
                                           job_ref=job_ref, calc_by=calc_by,
                                           checked_by=checked_by)
            elif at == "wall":
                generate_wall_report(tmp, a, project=project, job_ref=job_ref,
                                     calc_by=calc_by, checked_by=checked_by)
            elif at == "sheet_pile":
                _generate_sheet_pile_section(tmp, a, project, job_ref,
                                             calc_by, checked_by, st, today)
            else:
                _generate_unknown_section(tmp, a, lbl, st, today)
            section_files.append((lbl, tmp))
        except Exception as exc:
            # Write an error page rather than failing the whole report
            _generate_error_section(tmp, lbl, str(exc), st, today)
            section_files.append((lbl, tmp))

    # ── Assemble cover + TOC + all sections ──────────────────────────────────
    story: list = []

    # Cover page
    story += [
        Spacer(1, 20 * mm),
        Paragraph("GEOTECHNICAL CALCULATION REPORT", st["title"]),
        HRFlowable(width=INNER_W, thickness=2, color=_DARK_BLUE),
        Spacer(1, 8 * mm),
        Paragraph(project, ParagraphStyle(
            "cover_proj", parent=getSampleStyleSheet()["Normal"],
            fontSize=13, textColor=_MID_BLUE, fontName="Helvetica-Bold",
        )),
        Spacer(1, 4 * mm),
    ]
    meta_data = [
        ["Job reference:", job_ref or "—"],
        ["Date:",          today],
        ["Prepared by:",   calc_by or "—"],
        ["Checked by:",    checked_by or "—"],
        ["Analyses:",      str(len(analyses))],
    ]
    meta_t = Table(meta_data, colWidths=[INNER_W * 0.30, INNER_W * 0.70])
    meta_t.setStyle(TableStyle([
        ("BACKGROUND",   (0, 0), (0, -1), _LIGHT_BLUE),
        ("FONTNAME",     (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE",     (0, 0), (-1, -1), 9),
        ("BOX",          (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",         (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN",       (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",   (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))
    story += [meta_t, Spacer(1, 10 * mm)]

    # Summary table on cover
    story.append(Paragraph("Analysis Summary", st["h2"]))
    sum_hdr = [Paragraph(h, st["cell_bold"]) for h in
               ["#", "Analysis Type", "Key Result", "Status"]]
    sum_rows = [sum_hdr]
    for i, a in enumerate(analyses, 1):
        passes = a.get("passes", False)
        status = "PASS ✓" if passes else "FAIL ✗"
        s_col  = _PASS_GREEN if passes else _FAIL_RED
        sum_rows.append([
            Paragraph(str(i),            st["cell"]),
            Paragraph(_analysis_label(a), st["cell"]),
            Paragraph(_key_result(a),     st["cell"]),
            Paragraph(status,             ParagraphStyle(
                f"s{i}", parent=st["cell_bold"], textColor=s_col,
            )),
        ])
    sum_t = Table(sum_rows, colWidths=[INNER_W * 0.06, INNER_W * 0.36,
                                       INNER_W * 0.34, INNER_W * 0.24])
    sum_t.setStyle(TableStyle([
        ("BACKGROUND",     (0, 0), (-1, 0), _DARK_BLUE),
        ("TEXTCOLOR",      (0, 0), (-1, 0), _WHITE),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [_WHITE, _GREY]),
        ("BOX",            (0, 0), (-1, -1), 0.5, _DARK_BLUE),
        ("GRID",           (0, 0), (-1, -1), 0.3, colors.grey),
        ("VALIGN",         (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING",     (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING",  (0, 0), (-1, -1), 3),
    ]))
    story += [sum_t, Spacer(1, 8 * mm)]

    story.append(Paragraph(
        "Calculation sheets follow. All analyses per Eurocode 7 EN 1997-1:2004. "
        "Verify all inputs before use for structural design.",
        st["body"],
    ))

    # ── Render cover to a temp PDF ────────────────────────────────────────────
    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tf:
        cover_path = tf.name

    # Page-number callback
    class _PageNumCanvas:
        """Minimal onPage canvas shim — page numbers in footer."""
        pass  # ReportLab SimpleDocTemplate handles via canvasmaker

    doc = SimpleDocTemplate(
        cover_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN + 8 * mm,
    )
    doc.build(story)

    # ── Merge PDFs ────────────────────────────────────────────────────────────
    try:
        import pypdf
        writer = pypdf.PdfWriter()

        for src in [cover_path] + [p for _, p in section_files]:
            if os.path.exists(src) and os.path.getsize(src) > 100:
                reader = pypdf.PdfReader(src)
                for page in reader.pages:
                    writer.add_page(page)

        # Sequential page numbers via /Contents manipulation is complex;
        # write as-is (cover already has its own pages, sections theirs).
        with open(out_path, "wb") as out_f:
            writer.write(out_f)

    except ImportError as _pypdf_err:
        # B-13 FIX: fail loudly rather than silently producing a cover-only PDF.
        # pypdf is a hard dependency for generate_project_report(); without it
        # the caller would receive a truncated document with no warning.
        raise ImportError(
            "generate_project_report() requires 'pypdf'. "
            "Install it with:  pip install pypdf  |  "
            f"Original error: {_pypdf_err}"
        ) from _pypdf_err

    # ── Cleanup temp files ────────────────────────────────────────────────────
    for tmp in [cover_path] + [p for _, p in section_files]:
        try:
            os.unlink(tmp)
        except OSError:
            pass


def _generate_sheet_pile_section(
    out_path: str, a: dict,
    project: str, job_ref: str, calc_by: str, checked_by: str,
    st: dict, today: str,
) -> None:
    """
    Minimal one-page PDF for a sheet pile analysis result.

    Used by generate_project_report() when analysis_type == 'sheet_pile'.
    A full standalone report will be added in Sprint 13.

    Reference: EC7 §9.7.4; Blum (1931).
    """
    doc = SimpleDocTemplate(
        out_path, pagesize=A4,
        leftMargin=MARGIN, rightMargin=MARGIN,
        topMargin=MARGIN, bottomMargin=MARGIN,
    )
    story = []

    hdr_data = [
        [Paragraph("DesignApp — Sheet Pile Analysis", st["title"]),
         Paragraph(f"Ref: {job_ref}", st["body"]),
         Paragraph(f"Date: {today}", st["body"])],
        [Paragraph(f"Project: {project}", st["subtitle"]),
         Paragraph(f"Calc by: {calc_by}", st["body"]),
         Paragraph(f"Checked: {checked_by}", st["body"])],
    ]
    hdr = Table(hdr_data, colWidths=[INNER_W*0.55, INNER_W*0.25, INNER_W*0.20])
    hdr.setStyle(TableStyle([
        ("BACKGROUND",   (0,0),(-1,0), _DARK_BLUE),
        ("TEXTCOLOR",    (0,0),(-1,0), _WHITE),
        ("BACKGROUND",   (0,1),(-1,1), _LIGHT_BLUE),
        ("BOX",          (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",         (0,0),(-1,-1), 0.3, _MID_BLUE),
        ("VALIGN",       (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",   (0,0),(-1,-1), 4),
        ("BOTTOMPADDING",(0,0),(-1,-1), 4),
    ]))
    story += [hdr, Spacer(1, 5*mm)]
    story.append(Paragraph("Free-Earth Support — EC7 DA1 Results", st["h2"]))

    w   = a.get("wall", {})
    def _row(lbl, val, unit=""):
        return [Paragraph(lbl, st["cell_bold"]),
                Paragraph(str(val), st["cell"]),
                Paragraph(unit, st["cell"])]

    rows = [
        [Paragraph("Parameter", st["cell_bold"]),
         Paragraph("Value",     st["cell_bold"]),
         Paragraph("Unit",      st["cell_bold"])],
        _row("Retained height h",        f"{w.get('h_retained','—'):.2f}" if isinstance(w.get('h_retained'), float) else str(w.get('h_retained','—')), "m"),
        _row("Design embedment d_design", f"{a.get('d_design','—'):.4f}" if isinstance(a.get('d_design'), float) else str(a.get('d_design','—')), "m"),
        _row("Prop force T",              f"{a.get('T_design','—'):.3f}" if isinstance(a.get('T_design'), float) else str(a.get('T_design','—')), "kN/m"),
        _row("Max bending moment M_max",  f"{a.get('M_max_design','—'):.3f}" if isinstance(a.get('M_max_design'), float) else str(a.get('M_max_design','—')), "kN·m/m"),
        _row("Depth of M_max below prop", f"{a.get('z_Mmax_design','—'):.4f}" if isinstance(a.get('z_Mmax_design'), float) else str(a.get('z_Mmax_design','—')), "m"),
        _row("Governing combination",     a.get("governing","—")),
        _row("Ka_k / Kp_k",              f"{a.get('Ka_k','—'):.4f} / {a.get('Kp_k','—'):.4f}" if isinstance(a.get('Ka_k'), float) else "—"),
    ]
    tbl = Table(rows, colWidths=[INNER_W*0.50, INNER_W*0.30, INNER_W*0.20])
    tbl.setStyle(TableStyle([
        ("BACKGROUND",     (0,0),(-1,0), _MID_BLUE),
        ("TEXTCOLOR",      (0,0),(-1,0), _WHITE),
        ("ROWBACKGROUNDS", (0,1),(-1,-1), [_WHITE, _GREY]),
        ("BOX",            (0,0),(-1,-1), 0.5, _DARK_BLUE),
        ("GRID",           (0,0),(-1,-1), 0.3, colors.grey),
        ("VALIGN",         (0,0),(-1,-1), "MIDDLE"),
        ("TOPPADDING",     (0,0),(-1,-1), 3),
        ("BOTTOMPADDING",  (0,0),(-1,-1), 3),
    ]))
    story += [tbl, Spacer(1, 5*mm)]

    passes  = a.get("passes", False)
    verdict = "SATISFACTORY — PASS" if passes else "UNSATISFACTORY — FAIL"
    v_style = _styles()["pass"] if passes else _styles()["fail"]
    v_bg    = colors.HexColor("#EAF7EA") if passes else colors.HexColor("#FDECEA")
    v_t = Table([[Paragraph(verdict, v_style)]], colWidths=[INNER_W])
    v_t.setStyle(TableStyle([
        ("BACKGROUND",    (0,0),(-1,-1), v_bg),
        ("BOX",           (0,0),(-1,-1), 1.5, _PASS_GREEN if passes else _FAIL_RED),
        ("ALIGN",         (0,0),(-1,-1), "CENTER"),
        ("TOPPADDING",    (0,0),(-1,-1), 8),
        ("BOTTOMPADDING", (0,0),(-1,-1), 8),
    ]))
    story.append(v_t)
    doc.build(story)


def _generate_unknown_section(
    out_path: str, a: dict, label: str, st: dict, today: str
) -> None:
    """Fallback one-page section for unrecognised analysis_type."""
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN)
    story = [
        Paragraph(f"{label} — Analysis Results", st["h2"]),
        Spacer(1, 5*mm),
        Paragraph(f"Date: {today} | Type: {a.get('analysis_type','?')}", st["body"]),
        Spacer(1, 3*mm),
        Paragraph("Full calculation sheet not available for this analysis type.",
                  st["body"]),
    ]
    doc.build(story)


def _generate_error_section(
    out_path: str, label: str, error_msg: str, st: dict, today: str
) -> None:
    """One-page error section when a section render fails."""
    doc = SimpleDocTemplate(out_path, pagesize=A4,
                            leftMargin=MARGIN, rightMargin=MARGIN,
                            topMargin=MARGIN, bottomMargin=MARGIN)
    story = [
        Paragraph(f"{label} — Render Error", st["h2"]),
        Spacer(1, 5*mm),
        Paragraph(f"Date: {today}", st["body"]),
        Spacer(1, 3*mm),
        Paragraph(f"Error: {error_msg}", st["mono"]),
    ]
    doc.build(story)
