"""
=============================================================================
ACI 211.1 CONCRETE MIX DESIGN TOOL (Metric)
=============================================================================
Author     : Senior Structural/Materials Engineer + Python Developer
Standard   : ACI 211.1 (SI / Metric Units)
Modification: User-defined cement factor (not derived from w/c alone)
Units      : kg, m³, mm, MPa
Dependencies: tkinter (stdlib), reportlab, matplotlib
=============================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import math
import copy
from datetime import datetime

# ─── Optional imports ────────────────────────────────────────────────────────
try:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import mm
    from reportlab.platypus import (
        SimpleDocTemplate, Table, TableStyle, Paragraph,
        Spacer, HRFlowable
    )
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    REPORTLAB_OK = True
except ImportError:
    REPORTLAB_OK = False

try:
    import matplotlib
    matplotlib.use("TkAgg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    MATPLOTLIB_OK = True
except ImportError:
    MATPLOTLIB_OK = False


# =============================================================================
# ─── 1. ACI 211.1 REFERENCE DATA ────────────────────────────────────────────
# =============================================================================

# ACI Table 6.3.3 — Approximate mixing water (kg/m³) for non-air-entrained
# Rows: slump ranges (25, 50, 75, 100, 150, 175 mm mid-points)
# Cols: max agg size (mm): 9.5, 12.5, 19, 25, 37.5, 50, 75, 150
ACI_WATER_NON_AE = {
    "25-50":   {9.5: 207, 12.5: 199, 19: 190, 25: 179, 37.5: 166, 50: 154, 75: 130, 150: 113},
    "75-100":  {9.5: 228, 12.5: 216, 19: 205, 25: 193, 37.5: 181, 50: 169, 75: 145, 150: 124},
    "150-175": {9.5: 243, 12.5: 228, 19: 216, 25: 202, 37.5: 190, 50: 178, 75: 160, 150: 0  },
}

# ACI Table 6.3.3 — Air-entrained concrete
ACI_WATER_AE = {
    "25-50":   {9.5: 181, 12.5: 175, 19: 168, 25: 160, 37.5: 150, 50: 142, 75: 122, 150: 107},
    "75-100":  {9.5: 202, 12.5: 193, 19: 184, 25: 175, 37.5: 165, 50: 157, 75: 133, 150: 119},
    "150-175": {9.5: 216, 12.5: 205, 19: 197, 25: 184, 37.5: 174, 50: 166, 75: 154, 150: 0  },
}

# ACI recommended air content (%) for non-air-entrained concrete (mild / moderate / severe)
ACI_AIR_NON_AE = {9.5: 3.0, 12.5: 2.5, 19: 2.0, 25: 1.5, 37.5: 1.0, 50: 0.5, 75: 0.3, 150: 0.2}

# Standard max aggregate sizes (mm)
STANDARD_AGG_SIZES = [9.5, 12.5, 19, 25, 37.5, 50, 75, 150]

# Density of water (kg/m³)
WATER_DENSITY = 1000.0

BAG_MASS_DEFAULT = 40.0  # kg/bag


# =============================================================================
# ─── 2. CALCULATION ENGINE ───────────────────────────────────────────────────
# =============================================================================

def get_aci_water(slump_mm: float, max_agg_mm: float, air_entrained: bool) -> float:
    """
    Look up ACI 211.1 Table 6.3.3 mixing water requirement.
    Returns kg/m³ for the given slump and max aggregate size.
    Nearest-key lookup for non-standard sizes.
    """
    table = ACI_WATER_AE if air_entrained else ACI_WATER_NON_AE

    # Map slump to table key
    if slump_mm <= 62:
        row = "25-50"
    elif slump_mm <= 137:
        row = "75-100"
    else:
        row = "150-175"

    # Map aggregate size to nearest standard size
    sizes = STANDARD_AGG_SIZES
    nearest = min(sizes, key=lambda s: abs(s - max_agg_mm))

    water = table[row][nearest]
    if water == 0:
        raise ValueError(
            f"ACI 211.1 does not specify water content for slump {row} mm "
            f"and max agg size {nearest} mm. Choose a smaller slump or aggregate."
        )
    return float(water)


class MixDesignInput:
    """Container for all user inputs — keeps calculation engine clean."""

    def __init__(self):
        # General
        self.project_title: str = "Untitled Project"
        self.target_strength_mpa: float = 28.0
        self.slump_mm: float = 75.0
        self.max_agg_size_mm: float = 19.0
        self.air_content_pct: float = 2.0
        self.air_entrained: bool = False

        # Cementitious
        self.bag_mass_kg: float = BAG_MASS_DEFAULT
        self.cement_factor_mode: str = "kg/m³"   # or "bags"
        self.cement_factor_value: float = 350.0   # in chosen mode
        self.scm_list: list = []  # each: {"name": str, "replacement_pct": float, "sg": float}

        # Water
        self.water_mode: str = "auto"   # or "manual"
        self.water_manual_kg: float = 185.0

        # Aggregates: list of dicts
        self.aggregates: list = []
        # Each dict: {
        #   "name": str, "type": "fine"/"coarse",
        #   "sg": float, "absorption_pct": float,
        #   "moisture_pct": float, "bulk_density": float,
        #   "blend_pct": float   ← % of that type's total
        # }

        # Admixtures
        self.admixtures: list = []
        # Each: {"name": str, "type": str, "dosage_mode": str, "dosage": float}

        # Batch size
        self.batch_volume_m3: float = 1.0

        # Design margin (over-design)
        self.design_margin_mpa: float = 8.3  # ACI 301 default for < 15 samples


class MixDesignResult:
    """Holds all computed mix design outputs."""

    def __init__(self):
        self.cement_kg_m3: float = 0.0
        self.scm_kg_m3: list = []          # parallel to input.scm_list
        self.water_kg_m3: float = 0.0
        self.air_volume_m3: float = 0.0
        self.aggregate_kg_m3: list = []    # parallel to input.aggregates
        self.admixture_kg_m3: list = []    # parallel to input.admixtures

        # Volumes (m³/m³)
        self.vol_cement: float = 0.0
        self.vol_scm: list = []
        self.vol_water: float = 0.0
        self.vol_air: float = 0.0
        self.vol_agg: list = []
        self.vol_total: float = 0.0

        # Derived
        self.wc_ratio_computed: float = 0.0
        self.wcm_ratio_computed: float = 0.0  # w / (c + SCM)
        self.total_cementitious_kg: float = 0.0

        # Moisture-corrected batch masses (per batch volume)
        self.batch_cement_kg: float = 0.0
        self.batch_scm_kg: list = []
        self.batch_water_kg: float = 0.0        # adjusted batch water
        self.batch_agg_kg: list = []            # SSD-corrected
        self.batch_agg_adjusted_kg: list = []   # moisture-corrected (field mass)

        # Warnings
        self.warnings: list = []

        # Admixture volumes (minor, usually ignored in volume check)
        self.admixture_ml_m3: list = []


def calculate_mix(inp: MixDesignInput) -> MixDesignResult:
    """
    Core ACI 211.1 absolute volume mix design with user-defined cement factor.
    Returns a populated MixDesignResult.
    """
    res = MixDesignResult()
    warnings = []

    # ── Step 1: Cement content (kg/m³) ──────────────────────────────────────
    if inp.cement_factor_mode == "bags":
        cement_kg = inp.cement_factor_value * inp.bag_mass_kg
    else:
        cement_kg = inp.cement_factor_value

    # ── Step 2: SCM contents ─────────────────────────────────────────────────
    total_replacement = sum(s["replacement_pct"] for s in inp.scm_list)
    if total_replacement > 60:
        warnings.append(f"Total SCM replacement ({total_replacement:.1f}%) exceeds 60% — verify durability.")
    if total_replacement >= 100:
        raise ValueError("Total SCM replacement cannot be ≥ 100%.")

    # Effective cementitious: cement is reduced by SCM replacement on mass basis
    # SCM replaces cement on equal-mass basis (most conservative / common approach)
    effective_cement = cement_kg * (1.0 - total_replacement / 100.0)
    scm_kg_list = []
    for scm in inp.scm_list:
        scm_mass = cement_kg * (scm["replacement_pct"] / 100.0)
        scm_kg_list.append(scm_mass)

    total_cementitious = effective_cement + sum(scm_kg_list)
    res.cement_kg_m3 = effective_cement
    res.scm_kg_m3 = scm_kg_list
    res.total_cementitious_kg = total_cementitious

    # ── Step 3: Water content ─────────────────────────────────────────────────
    if inp.water_mode == "auto":
        water_kg = get_aci_water(inp.slump_mm, inp.max_agg_size_mm, inp.air_entrained)
    else:
        water_kg = inp.water_manual_kg
    res.water_kg_m3 = water_kg

    # ── Step 4: W/C and W/CM ratios ──────────────────────────────────────────
    res.wc_ratio_computed = water_kg / effective_cement if effective_cement > 0 else 0.0
    res.wcm_ratio_computed = water_kg / total_cementitious if total_cementitious > 0 else 0.0

    # Validation warnings
    if res.wc_ratio_computed > 0.70:
        warnings.append(f"W/C ratio ({res.wc_ratio_computed:.2f}) is HIGH — durability risk.")
    if res.wc_ratio_computed < 0.30:
        warnings.append(f"W/C ratio ({res.wc_ratio_computed:.2f}) is very LOW — workability concern.")
    if inp.slump_mm > 200:
        warnings.append("Slump > 200 mm is unusually high — consider superplasticizer.")
    if inp.slump_mm < 15:
        warnings.append("Slump < 15 mm is very stiff — verify compaction method.")

    # ── Step 5: Volumes of cementitious + water + air ────────────────────────
    # Cement SG assumed 3.15 (Portland)
    cement_sg = 3.15
    vol_cement = effective_cement / (cement_sg * WATER_DENSITY)

    vol_scm_list = []
    for i, scm in enumerate(inp.scm_list):
        sg = scm.get("sg", 2.20)  # Fly ash default ~2.2
        vol_scm = scm_kg_list[i] / (sg * WATER_DENSITY)
        vol_scm_list.append(vol_scm)

    vol_water = water_kg / WATER_DENSITY
    vol_air = inp.air_content_pct / 100.0

    vol_paste = vol_cement + sum(vol_scm_list) + vol_water + vol_air

    res.vol_cement = vol_cement
    res.vol_scm = vol_scm_list
    res.vol_water = vol_water
    res.vol_air = vol_air

    if vol_paste >= 1.0:
        raise ValueError(
            f"Paste volume ({vol_paste:.4f} m³) ≥ 1.0 m³ — no room for aggregates. "
            "Reduce cement or water content."
        )

    vol_agg_total = 1.0 - vol_paste  # remaining volume for ALL aggregates

    # ── Step 6: Aggregate proportioning ──────────────────────────────────────
    # Validate blend percentages per type
    fine_aggs = [a for a in inp.aggregates if a["type"] == "fine"]
    coarse_aggs = [a for a in inp.aggregates if a["type"] == "coarse"]

    fine_total_pct = sum(a["blend_pct"] for a in fine_aggs)
    coarse_total_pct = sum(a["blend_pct"] for a in coarse_aggs)

    if fine_aggs and abs(fine_total_pct - 100.0) > 0.5:
        warnings.append(f"Fine aggregate blend sums to {fine_total_pct:.1f}% (should be 100%).")
    if coarse_aggs and abs(coarse_total_pct - 100.0) > 0.5:
        warnings.append(f"Coarse aggregate blend sums to {coarse_total_pct:.1f}% (should be 100%).")

    if not inp.aggregates:
        raise ValueError("At least one aggregate must be defined.")

    # Determine split between fine and coarse using ACI bulk volume method
    # ACI Table 6.3.6: Vol of dry-rodded coarse agg per unit vol of concrete
    # Simplified: user defines proportion by blend_pct across all aggregates
    # We use blend_pct as fraction of total aggregate volume
    all_blend_pct_total = sum(a["blend_pct"] for a in inp.aggregates)
    if all_blend_pct_total <= 0:
        raise ValueError("Aggregate blend percentages must sum to > 0.")

    vol_agg_list = []
    kg_agg_list = []
    for agg in inp.aggregates:
        frac = agg["blend_pct"] / all_blend_pct_total
        vol_a = vol_agg_total * frac
        mass_a = vol_a * agg["sg"] * WATER_DENSITY
        vol_agg_list.append(vol_a)
        kg_agg_list.append(mass_a)

    res.vol_agg = vol_agg_list
    res.aggregate_kg_m3 = kg_agg_list

    # ── Step 7: Volume check ─────────────────────────────────────────────────
    vol_total = (vol_cement + sum(vol_scm_list) + vol_water + vol_air + sum(vol_agg_list))
    res.vol_total = vol_total
    if abs(vol_total - 1.0) > 0.005:
        warnings.append(f"Total volume = {vol_total:.4f} m³ (should be 1.000). Check inputs.")

    # ── Step 8: Admixtures ────────────────────────────────────────────────────
    admix_ml_m3 = []
    admix_kg_m3 = []
    for adm in inp.admixtures:
        if adm["dosage_mode"] == "ml/kg":
            ml = adm["dosage"] * total_cementitious
        else:  # % of cement mass
            ml = (adm["dosage"] / 100.0) * total_cementitious * 1000.0
        admix_ml_m3.append(ml)
        admix_kg_m3.append(ml / 1000.0)  # approx density 1.0 kg/L

    res.admixture_ml_m3 = admix_ml_m3
    res.admixture_kg_m3 = admix_kg_m3

    # ── Step 9: Moisture correction for batch ─────────────────────────────────
    batch = inp.batch_volume_m3
    surface_water_sum = 0.0
    batch_agg_ssd = []
    batch_agg_field = []

    for i, agg in enumerate(inp.aggregates):
        ssd_mass = kg_agg_list[i] * batch  # SSD mass for batch
        # Field (wet) mass:  mass_SSD × (1 + MC%) / (1 + Abs%)
        mc = agg["moisture_pct"] / 100.0
        ab = agg["absorption_pct"] / 100.0
        field_mass = ssd_mass * (1.0 + mc) / (1.0 + ab)
        batch_agg_ssd.append(ssd_mass)
        batch_agg_field.append(field_mass)
        # Surface water contribution (positive = excess, negative = absorbs)
        surface_water = ssd_mass * (mc - ab)
        surface_water_sum += surface_water

    # Adjust batch water
    batch_water_adjusted = water_kg * batch - surface_water_sum

    res.batch_cement_kg = effective_cement * batch
    res.batch_scm_kg = [m * batch for m in scm_kg_list]
    res.batch_water_kg = batch_water_adjusted
    res.batch_agg_kg = batch_agg_ssd
    res.batch_agg_adjusted_kg = batch_agg_field
    res.warnings = warnings

    return res


# =============================================================================
# ─── 3. PDF REPORT GENERATOR ─────────────────────────────────────────────────
# =============================================================================

def generate_pdf(inp: MixDesignInput, res: MixDesignResult, filepath: str):
    """Generate a formatted ACI 211.1 mix design PDF report using ReportLab."""

    if not REPORTLAB_OK:
        raise ImportError("reportlab is not installed. Run: pip install reportlab")

    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    styles = getSampleStyleSheet()
    style_title = ParagraphStyle(
        "Title", parent=styles["Title"],
        fontSize=16, spaceAfter=4, textColor=colors.HexColor("#1a3c5e")
    )
    style_h2 = ParagraphStyle(
        "H2", parent=styles["Heading2"],
        fontSize=11, spaceAfter=4, spaceBefore=10,
        textColor=colors.HexColor("#1a3c5e")
    )
    style_body = ParagraphStyle(
        "Body", parent=styles["Normal"],
        fontSize=9, leading=14
    )
    style_footer = ParagraphStyle(
        "Footer", parent=styles["Normal"],
        fontSize=7, textColor=colors.grey, alignment=TA_CENTER
    )

    # Table style helpers
    def header_table_style(col_widths):
        return TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1a3c5e")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ("FONTSIZE", (0, 0), (-1, -1), 8.5),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#eef4fb")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aac4e0")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
        ])

    story = []

    # ── Header ────────────────────────────────────────────────────────────────
    story.append(Paragraph("CONCRETE MIX DESIGN REPORT", style_title))
    story.append(Paragraph("Based on ACI 211.1 — Absolute Volume Method (SI Units)", style_body))
    story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#1a3c5e")))
    story.append(Spacer(1, 4 * mm))

    now = datetime.now().strftime("%B %d, %Y  %H:%M")
    info_data = [
        ["Project Title", inp.project_title, "Date", now],
        ["Target f'c", f"{inp.target_strength_mpa:.1f} MPa",
         "Design Margin", f"{inp.design_margin_mpa:.1f} MPa"],
        ["Required f'cr", f"{inp.target_strength_mpa + inp.design_margin_mpa:.1f} MPa",
         "Batch Volume", f"{inp.batch_volume_m3:.3f} m³"],
    ]
    t = Table(info_data, colWidths=[42 * mm, 48 * mm, 38 * mm, 48 * mm])
    ts = TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),
        ("FONTNAME", (2, 0), (2, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8.5),
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f5f9fd")),
        ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#aac4e0")),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (3, 0), (3, -1), "CENTER"),
    ])
    t.setStyle(ts)
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # ── Section A: Design Parameters ──────────────────────────────────────────
    story.append(Paragraph("A — Design Parameters", style_h2))
    param_data = [
        ["Parameter", "Value", "Parameter", "Value"],
        ["Slump", f"{inp.slump_mm:.0f} mm",
         "Max Agg. Size", f"{inp.max_agg_size_mm:.1f} mm"],
        ["Air Content", f"{inp.air_content_pct:.1f} %",
         "Air Entrained", "Yes" if inp.air_entrained else "No"],
        ["Cement Factor Mode", inp.cement_factor_mode,
         "Cement Factor", f"{inp.cement_factor_value:.1f} {inp.cement_factor_mode}"],
        ["Water Mode", inp.water_mode,
         "W/C (computed)", f"{res.wc_ratio_computed:.3f}"],
        ["W/CM (computed)", f"{res.wcm_ratio_computed:.3f}",
         "Bag Mass", f"{inp.bag_mass_kg:.0f} kg/bag"],
    ]
    t = Table(param_data, colWidths=[48 * mm, 42 * mm, 48 * mm, 42 * mm])
    t.setStyle(header_table_style(None))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # ── Section B: Mix Proportions per m³ ─────────────────────────────────────
    story.append(Paragraph("B — Mix Proportions per 1 m³", style_h2))
    mix_data = [["Material", "Mass (kg)", "Volume (m³)", "% of Total Vol."]]

    def row(label, mass, vol):
        return [label, f"{mass:.2f}", f"{vol:.4f}", f"{vol*100:.2f}%"]

    mix_data.append(row("Portland Cement", res.cement_kg_m3, res.vol_cement))
    for i, scm in enumerate(inp.scm_list):
        mix_data.append(row(
            f"SCM: {scm['name']} ({scm['replacement_pct']:.1f}%)",
            res.scm_kg_m3[i], res.vol_scm[i]
        ))
    mix_data.append(row("Mixing Water", res.water_kg_m3, res.vol_water))
    mix_data.append(["Entrapped Air", "—", f"{res.vol_air:.4f}", f"{res.vol_air*100:.2f}%"])
    for i, agg in enumerate(inp.aggregates):
        mix_data.append(row(
            f"{agg['type'].title()} Agg: {agg['name']}",
            res.aggregate_kg_m3[i], res.vol_agg[i]
        ))

    # Total row
    total_mass = (res.cement_kg_m3 + sum(res.scm_kg_m3) + res.water_kg_m3
                  + sum(res.aggregate_kg_m3))
    mix_data.append(["TOTAL", f"{total_mass:.2f}", f"{res.vol_total:.4f}", f"{res.vol_total*100:.2f}%"])

    cw = [68 * mm, 38 * mm, 38 * mm, 36 * mm]
    t = Table(mix_data, colWidths=cw)
    ts2 = header_table_style(cw)
    ts2.add("FONTNAME", (0, len(mix_data) - 1), (-1, len(mix_data) - 1), "Helvetica-Bold")
    ts2.add("BACKGROUND", (0, len(mix_data) - 1), (-1, len(mix_data) - 1), colors.HexColor("#c8dff5"))
    t.setStyle(ts2)
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # ── Section C: Batch Quantities ───────────────────────────────────────────
    story.append(Paragraph(f"C — Batch Quantities  (Batch = {inp.batch_volume_m3:.3f} m³)", style_h2))
    batch_data = [["Material", "SSD Mass (kg)", "Field Mass (kg)", "Notes"]]
    batch_data.append([
        "Portland Cement",
        f"{res.batch_cement_kg:.2f}",
        f"{res.batch_cement_kg:.2f}",
        f"{res.batch_cement_kg / inp.bag_mass_kg:.2f} bags"
    ])
    for i, scm in enumerate(inp.scm_list):
        batch_data.append([
            f"SCM: {scm['name']}",
            f"{res.batch_scm_kg[i]:.2f}",
            f"{res.batch_scm_kg[i]:.2f}", "—"
        ])
    batch_data.append([
        "Mixing Water",
        f"{res.water_kg_m3 * inp.batch_volume_m3:.2f}",
        f"{res.batch_water_kg:.2f}",
        "Moisture-adjusted"
    ])
    for i, agg in enumerate(inp.aggregates):
        mc = agg["moisture_pct"]
        ab = agg["absorption_pct"]
        batch_data.append([
            f"{agg['type'].title()} Agg: {agg['name']}",
            f"{res.batch_agg_kg[i]:.2f}",
            f"{res.batch_agg_adjusted_kg[i]:.2f}",
            f"MC={mc:.1f}%, Ab={ab:.1f}%"
        ])
    for i, adm in enumerate(inp.admixtures):
        batch_data.append([
            f"Admixture: {adm['name']}",
            f"{res.admixture_ml_m3[i] * inp.batch_volume_m3:.1f} mL",
            f"{res.admixture_ml_m3[i] * inp.batch_volume_m3:.1f} mL",
            adm["type"]
        ])

    cw2 = [58 * mm, 36 * mm, 36 * mm, 50 * mm]
    t = Table(batch_data, colWidths=cw2)
    t.setStyle(header_table_style(cw2))
    story.append(t)
    story.append(Spacer(1, 4 * mm))

    # ── Section D: Aggregate Details ──────────────────────────────────────────
    if inp.aggregates:
        story.append(Paragraph("D — Aggregate Properties", style_h2))
        agg_header = ["Name", "Type", "SG", "Absorption\n(%)", "Moisture\n(%)",
                      "Bulk Density\n(kg/m³)", "Blend\n(%)"]
        agg_data = [agg_header]
        for agg in inp.aggregates:
            agg_data.append([
                agg["name"], agg["type"].title(),
                f"{agg['sg']:.2f}",
                f"{agg['absorption_pct']:.2f}",
                f"{agg['moisture_pct']:.2f}",
                f"{agg.get('bulk_density', 0):.0f}",
                f"{agg['blend_pct']:.1f}%",
            ])
        cw3 = [36 * mm, 22 * mm, 18 * mm, 22 * mm, 22 * mm, 26 * mm, 18 * mm]
        t = Table(agg_data, colWidths=cw3)
        t.setStyle(header_table_style(cw3))
        story.append(t)
        story.append(Spacer(1, 4 * mm))

    # ── Section E: Warnings ───────────────────────────────────────────────────
    if res.warnings:
        story.append(Paragraph("E — Engineering Warnings", style_h2))
        for w in res.warnings:
            story.append(Paragraph(f"⚠ {w}", style_body))
        story.append(Spacer(1, 4 * mm))

    # ── Footer ────────────────────────────────────────────────────────────────
    story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
    story.append(Spacer(1, 2 * mm))
    story.append(Paragraph(
        "Generated by ACI 211.1 Concrete Mix Design Tool (Metric) — For engineering use only. "
        "Verify all results with qualified personnel.",
        style_footer
    ))

    doc.build(story)


# =============================================================================
# ─── 4. GRAPHING MODULE ───────────────────────────────────────────────────────
# =============================================================================

def plot_mix_proportions(inp: MixDesignInput, res: MixDesignResult, parent_frame=None):
    """
    Display a pie chart of mix proportions by volume.
    If parent_frame is provided, embed in Tkinter; otherwise show standalone.
    """
    labels = ["Cement"]
    sizes = [res.vol_cement]

    for i, scm in enumerate(inp.scm_list):
        labels.append(f"SCM: {scm['name']}")
        sizes.append(res.vol_scm[i])

    labels.append("Water")
    sizes.append(res.vol_water)
    labels.append("Air")
    sizes.append(res.vol_air)

    for i, agg in enumerate(inp.aggregates):
        labels.append(f"{agg['name']} ({agg['type']})")
        sizes.append(res.vol_agg[i])

    palette = [
        "#3c78d8", "#6aa84f", "#4fc3f7", "#b0bec5",
        "#e67c73", "#f6b26b", "#76d7c4", "#aed6f1",
        "#f9a825", "#ce93d8"
    ]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(9, 4))
    fig.patch.set_facecolor("#f8fafc")

    # Pie chart — volume proportions
    wedges, texts, autotexts = ax1.pie(
        sizes,
        labels=None,
        autopct=lambda p: f"{p:.1f}%" if p > 2 else "",
        colors=palette[:len(sizes)],
        startangle=90,
        pctdistance=0.75,
        wedgeprops={"linewidth": 0.6, "edgecolor": "white"}
    )
    ax1.set_title("Mix Proportions by Volume", fontsize=10, fontweight="bold", pad=8)
    ax1.legend(wedges, labels, loc="lower center", bbox_to_anchor=(0.5, -0.22),
               ncol=2, fontsize=7.5, framealpha=0.5)

    # Bar chart — mass proportions
    mass_labels = ["Cement"] + [s["name"] for s in inp.scm_list] + ["Water"]
    mass_vals = [res.cement_kg_m3] + list(res.scm_kg_m3) + [res.water_kg_m3]
    for i, agg in enumerate(inp.aggregates):
        mass_labels.append(agg["name"])
        mass_vals.append(res.aggregate_kg_m3[i])

    bars = ax2.bar(range(len(mass_labels)), mass_vals, color=palette[:len(mass_labels)],
                   edgecolor="white", linewidth=0.5)
    ax2.set_xticks(range(len(mass_labels)))
    ax2.set_xticklabels(mass_labels, rotation=30, ha="right", fontsize=7.5)
    ax2.set_ylabel("Mass (kg/m³)", fontsize=8)
    ax2.set_title("Mix Proportions by Mass", fontsize=10, fontweight="bold", pad=8)
    ax2.set_facecolor("#f0f4fa")
    for bar, val in zip(bars, mass_vals):
        ax2.text(bar.get_x() + bar.get_width() / 2,
                 bar.get_height() + 2, f"{val:.0f}",
                 ha="center", va="bottom", fontsize=7)

    plt.tight_layout(pad=1.5)

    if parent_frame is not None and MATPLOTLIB_OK:
        # Embed in Tkinter
        for widget in parent_frame.winfo_children():
            widget.destroy()
        canvas = FigureCanvasTkAgg(fig, master=parent_frame)
        canvas.draw()
        canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)
        plt.close(fig)
    else:
        plt.show()


# =============================================================================
# ─── 5. TKINTER GUI ──────────────────────────────────────────────────────────
# =============================================================================

THEME = {
    "bg": "#f0f4f8",
    "panel": "#ffffff",
    "accent": "#1a3c5e",
    "accent2": "#2e86c1",
    "warn": "#c0392b",
    "ok": "#1e8449",
    "label_fg": "#2c3e50",
    "entry_bg": "#fafcff",
    "header_bg": "#1a3c5e",
    "header_fg": "#ffffff",
    "btn_bg": "#2e86c1",
    "btn_fg": "#ffffff",
    "btn_act": "#1a3c5e",
}


def styled_button(parent, text, command, bg=None, fg=None, **kwargs):
    bg = bg or THEME["btn_bg"]
    fg = fg or THEME["btn_fg"]
    btn = tk.Button(
        parent, text=text, command=command,
        bg=bg, fg=fg, activebackground=THEME["btn_act"], activeforeground="white",
        relief="flat", padx=10, pady=5, cursor="hand2",
        font=("Segoe UI", 9, "bold"), **kwargs
    )
    return btn


def labeled_entry(parent, label, default="", width=16, row=0, col=0, tooltip=None):
    """Compact label + entry pair on a grid parent."""
    tk.Label(parent, text=label, bg=THEME["panel"], fg=THEME["label_fg"],
             font=("Segoe UI", 9), anchor="w").grid(
        row=row, column=col, sticky="w", padx=(4, 2), pady=3)
    var = tk.StringVar(value=str(default))
    entry = tk.Entry(parent, textvariable=var, width=width,
                     bg=THEME["entry_bg"], relief="solid", bd=1,
                     font=("Segoe UI", 9))
    entry.grid(row=row, column=col + 1, sticky="ew", padx=(0, 8), pady=3)
    return var


class AggregateRow:
    """Represents one aggregate's input row in the aggregate manager."""

    def __init__(self, parent, row_idx, remove_callback):
        self.frame = tk.Frame(parent, bg=THEME["panel"], pady=2)
        self.frame.pack(fill=tk.X, pady=1)

        # Fields
        fields = [
            ("Name", "Aggregate", 10),
            ("Type", "fine", 6),
            ("SG", "2.65", 5),
            ("Abs%", "1.0", 4),
            ("MC%", "2.0", 4),
            ("BD kg/m³", "1600", 6),
            ("Blend%", "100", 5),
        ]
        self.vars = {}
        for col, (lbl, default, w) in enumerate(fields):
            tk.Label(self.frame, text=lbl, bg=THEME["panel"],
                     font=("Segoe UI", 8), fg=THEME["label_fg"]).grid(
                row=0, column=col * 2, padx=2, sticky="w")
            var = tk.StringVar(value=default)
            ent = tk.Entry(self.frame, textvariable=var, width=w,
                           bg=THEME["entry_bg"], font=("Segoe UI", 8),
                           relief="solid", bd=1)
            ent.grid(row=0, column=col * 2 + 1, padx=2, pady=1)
            self.vars[lbl] = var

        tk.Button(self.frame, text="✕", command=lambda: remove_callback(self),
                  bg=THEME["warn"], fg="white", font=("Segoe UI", 8, "bold"),
                  relief="flat", padx=4, cursor="hand2").grid(
            row=0, column=len(fields) * 2, padx=4)

    def get_data(self) -> dict:
        agg_type = self.vars["Type"].get().strip().lower()
        if agg_type not in ("fine", "coarse"):
            agg_type = "fine"
        return {
            "name": self.vars["Name"].get().strip() or "Aggregate",
            "type": agg_type,
            "sg": float(self.vars["SG"].get() or 2.65),
            "absorption_pct": float(self.vars["Abs%"].get() or 1.0),
            "moisture_pct": float(self.vars["MC%"].get() or 0.0),
            "bulk_density": float(self.vars["BD kg/m³"].get() or 1600),
            "blend_pct": float(self.vars["Blend%"].get() or 100),
        }


class SCMRow:
    """Represents one SCM entry."""

    def __init__(self, parent, remove_callback):
        self.frame = tk.Frame(parent, bg=THEME["panel"])
        self.frame.pack(fill=tk.X, pady=1)

        fields = [("SCM Name", "Fly Ash", 12), ("Replacement %", "20", 6), ("SG", "2.20", 5)]
        self.vars = {}
        for col, (lbl, default, w) in enumerate(fields):
            tk.Label(self.frame, text=lbl, bg=THEME["panel"],
                     font=("Segoe UI", 8), fg=THEME["label_fg"]).grid(
                row=0, column=col * 2, padx=3, sticky="w")
            var = tk.StringVar(value=default)
            tk.Entry(self.frame, textvariable=var, width=w,
                     bg=THEME["entry_bg"], font=("Segoe UI", 8),
                     relief="solid", bd=1).grid(row=0, column=col * 2 + 1, padx=2)
            self.vars[lbl] = var

        tk.Button(self.frame, text="✕", command=lambda: remove_callback(self),
                  bg=THEME["warn"], fg="white", font=("Segoe UI", 8, "bold"),
                  relief="flat", padx=4, cursor="hand2").grid(
            row=0, column=len(fields) * 2, padx=4)

    def get_data(self) -> dict:
        return {
            "name": self.vars["SCM Name"].get().strip() or "SCM",
            "replacement_pct": float(self.vars["Replacement %"].get() or 0),
            "sg": float(self.vars["SG"].get() or 2.20),
        }


class AdmixtureRow:
    """Represents one admixture entry."""

    def __init__(self, parent, remove_callback):
        self.frame = tk.Frame(parent, bg=THEME["panel"])
        self.frame.pack(fill=tk.X, pady=1)

        fields = [
            ("Name", "HRWR", 10), ("Type", "Plasticizer", 12),
            ("Mode", "ml/kg", 6), ("Dosage", "2.0", 6),
        ]
        self.vars = {}
        for col, (lbl, default, w) in enumerate(fields):
            tk.Label(self.frame, text=lbl, bg=THEME["panel"],
                     font=("Segoe UI", 8), fg=THEME["label_fg"]).grid(
                row=0, column=col * 2, padx=3, sticky="w")
            var = tk.StringVar(value=default)
            tk.Entry(self.frame, textvariable=var, width=w,
                     bg=THEME["entry_bg"], font=("Segoe UI", 8),
                     relief="solid", bd=1).grid(row=0, column=col * 2 + 1, padx=2)
            self.vars[lbl] = var

        tk.Button(self.frame, text="✕", command=lambda: remove_callback(self),
                  bg=THEME["warn"], fg="white", font=("Segoe UI", 8, "bold"),
                  relief="flat", padx=4, cursor="hand2").grid(
            row=0, column=len(fields) * 2, padx=4)

    def get_data(self) -> dict:
        mode = self.vars["Mode"].get().strip()
        if mode not in ("ml/kg", "%"):
            mode = "ml/kg"
        return {
            "name": self.vars["Name"].get().strip() or "Admixture",
            "type": self.vars["Type"].get().strip() or "General",
            "dosage_mode": mode,
            "dosage": float(self.vars["Dosage"].get() or 0),
        }


class MixDesignApp(tk.Tk):
    """Main application window for ACI 211.1 Concrete Mix Design."""

    def __init__(self):
        super().__init__()
        self.title("ACI 211.1 Concrete Mix Design Tool  —  Metric (kg / m³ / mm)")
        self.geometry("1280x820")
        self.minsize(1100, 700)
        self.configure(bg=THEME["bg"])
        self.resizable(True, True)

        self._agg_rows: list = []
        self._scm_rows: list = []
        self._adm_rows: list = []
        self._last_result: MixDesignResult = None
        self._last_input: MixDesignInput = None

        self._build_ui()
        self._add_default_aggregates()

    # ── UI BUILD ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Top toolbar
        toolbar = tk.Frame(self, bg=THEME["header_bg"], height=44)
        toolbar.pack(fill=tk.X)
        tk.Label(toolbar, text="  🏗  ACI 211.1 Concrete Mix Design",
                 bg=THEME["header_bg"], fg=THEME["header_fg"],
                 font=("Segoe UI", 13, "bold")).pack(side=tk.LEFT, padx=8, pady=6)

        for text, cmd, color in [
            ("⟳ Calculate", self._calculate, "#27ae60"),
            ("📄 PDF Report", self._generate_pdf, "#8e44ad"),
            ("📊 Chart", self._show_chart, "#e67e22"),
            ("💾 Save", self._save_design, THEME["btn_bg"]),
            ("📂 Load", self._load_design, THEME["btn_bg"]),
        ]:
            styled_button(toolbar, text, cmd, bg=color).pack(
                side=tk.RIGHT, padx=4, pady=5)

        # Main paned window
        paned = tk.PanedWindow(self, orient=tk.HORIZONTAL, sashwidth=5,
                               bg=THEME["bg"], sashrelief="flat")
        paned.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        # Left: inputs
        left = tk.Frame(paned, bg=THEME["bg"])
        paned.add(left, minsize=530)

        # Right: results + chart
        right = tk.Frame(paned, bg=THEME["bg"])
        paned.add(right, minsize=350)

        self._build_input_panel(left)
        self._build_result_panel(right)

    def _section(self, parent, title):
        """Create a labelled section frame."""
        outer = tk.LabelFrame(parent, text=f"  {title}  ",
                              bg=THEME["panel"], fg=THEME["accent"],
                              font=("Segoe UI", 9, "bold"),
                              relief="groove", bd=1)
        outer.pack(fill=tk.X, padx=4, pady=3)
        return outer

    def _build_input_panel(self, parent):
        # Scrollable canvas for all inputs
        canvas = tk.Canvas(parent, bg=THEME["bg"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        self._input_frame = tk.Frame(canvas, bg=THEME["bg"])

        self._input_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self._input_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        f = self._input_frame

        # ── A. General ────────────────────────────────────────────────────────
        sec = self._section(f, "A — General")
        g = tk.Frame(sec, bg=THEME["panel"])
        g.pack(fill=tk.X, padx=6, pady=4)
        self.v_title       = labeled_entry(g, "Project Title", "Mix Design Project", 22, row=0, col=0)
        self.v_fc          = labeled_entry(g, "Target f'c (MPa)", "28.0", 8, row=1, col=0)
        self.v_margin      = labeled_entry(g, "Design Margin (MPa)", "8.3", 8, row=1, col=2)
        self.v_slump       = labeled_entry(g, "Slump (mm)", "75", 8, row=2, col=0)
        self.v_max_agg     = labeled_entry(g, "Max Agg. Size (mm)", "19", 8, row=2, col=2)
        self.v_air         = labeled_entry(g, "Air Content (%)", "2.0", 8, row=3, col=0)
        self.v_air_ent     = tk.BooleanVar(value=False)
        tk.Checkbutton(g, text="Air-Entrained Concrete", variable=self.v_air_ent,
                       bg=THEME["panel"], font=("Segoe UI", 9)).grid(row=3, column=3, sticky="w")
        self.v_batch       = labeled_entry(g, "Batch Volume (m³)", "1.0", 8, row=4, col=0)
        self.v_bag_mass    = labeled_entry(g, "Bag Mass (kg/bag)", "40", 8, row=4, col=2)
        g.columnconfigure(1, weight=1)
        g.columnconfigure(3, weight=1)

        # ── B. Cementitious ───────────────────────────────────────────────────
        sec2 = self._section(f, "B — Cementitious Materials")
        g2 = tk.Frame(sec2, bg=THEME["panel"])
        g2.pack(fill=tk.X, padx=6, pady=4)
        self.v_cement_mode = tk.StringVar(value="kg/m³")
        tk.Label(g2, text="Cement Factor Mode:", bg=THEME["panel"],
                 font=("Segoe UI", 9)).grid(row=0, column=0, sticky="w", padx=4, pady=3)
        mode_frame = tk.Frame(g2, bg=THEME["panel"])
        mode_frame.grid(row=0, column=1, sticky="w")
        for m in ["kg/m³", "bags"]:
            tk.Radiobutton(mode_frame, text=m, variable=self.v_cement_mode, value=m,
                           bg=THEME["panel"], font=("Segoe UI", 9)).pack(side=tk.LEFT, padx=4)
        self.v_cement_value = labeled_entry(g2, "Cement Factor Value", "350", 8, row=1, col=0)
        self.v_wc_input = labeled_entry(g2, "Target W/C (ref. only)", "0.50", 8, row=1, col=2)
        tk.Label(g2, text="Supplementary Cementitious Materials:", bg=THEME["panel"],
                 font=("Segoe UI", 9, "bold")).grid(row=2, column=0, columnspan=4, sticky="w",
                                                     padx=4, pady=(8, 2))
        self._scm_container = tk.Frame(g2, bg=THEME["panel"])
        self._scm_container.grid(row=3, column=0, columnspan=4, sticky="ew", padx=4)
        styled_button(g2, "+ Add SCM", self._add_scm, bg="#6c8ebf").grid(
            row=4, column=0, sticky="w", padx=4, pady=4)
        g2.columnconfigure(1, weight=1)
        g2.columnconfigure(3, weight=1)

        # ── C. Water ─────────────────────────────────────────────────────────
        sec3 = self._section(f, "C — Mixing Water")
        g3 = tk.Frame(sec3, bg=THEME["panel"])
        g3.pack(fill=tk.X, padx=6, pady=4)
        self.v_water_mode = tk.StringVar(value="auto")
        for m, lbl in [("auto", "Auto (ACI Table)"), ("manual", "Manual")]:
            tk.Radiobutton(g3, text=lbl, variable=self.v_water_mode, value=m,
                           bg=THEME["panel"], font=("Segoe UI", 9)).grid(
                row=0, column={"auto": 0, "manual": 1}[m], sticky="w", padx=6)
        self.v_water_manual = labeled_entry(g3, "Manual Water (kg/m³)", "185", 8, row=1, col=0)

        # ── D. Aggregates ─────────────────────────────────────────────────────
        sec4 = self._section(f, "D — Aggregates")
        g4 = tk.Frame(sec4, bg=THEME["panel"])
        g4.pack(fill=tk.X, padx=6, pady=4)
        tk.Label(g4, text="Name       Type     SG    Abs%  MC%   BD(kg/m³)  Blend%",
                 bg=THEME["panel"], fg=THEME["accent"],
                 font=("Courier", 8, "bold")).pack(anchor="w", padx=4)
        self._agg_container = tk.Frame(g4, bg=THEME["panel"])
        self._agg_container.pack(fill=tk.X)
        styled_button(g4, "+ Add Aggregate", self._add_aggregate, bg="#6c8ebf").pack(
            anchor="w", padx=4, pady=4)

        # ── E. Admixtures ─────────────────────────────────────────────────────
        sec5 = self._section(f, "E — Admixtures (Optional)")
        g5 = tk.Frame(sec5, bg=THEME["panel"])
        g5.pack(fill=tk.X, padx=6, pady=4)
        self._adm_container = tk.Frame(g5, bg=THEME["panel"])
        self._adm_container.pack(fill=tk.X)
        styled_button(g5, "+ Add Admixture", self._add_admixture, bg="#6c8ebf").pack(
            anchor="w", padx=4, pady=4)

    def _build_result_panel(self, parent):
        # Top: results text
        res_outer = tk.LabelFrame(parent, text="  Mix Design Results  ",
                                  bg=THEME["panel"], fg=THEME["accent"],
                                  font=("Segoe UI", 9, "bold"), relief="groove", bd=1)
        res_outer.pack(fill=tk.BOTH, expand=True, padx=4, pady=3)

        # Text area with scrollbar
        txt_frame = tk.Frame(res_outer, bg=THEME["panel"])
        txt_frame.pack(fill=tk.BOTH, expand=True)
        self._result_text = tk.Text(
            txt_frame, font=("Courier New", 9), bg="#f7fbff",
            fg=THEME["label_fg"], relief="flat", wrap=tk.NONE, state=tk.DISABLED
        )
        sb_y = ttk.Scrollbar(txt_frame, orient="vertical", command=self._result_text.yview)
        sb_x = ttk.Scrollbar(txt_frame, orient="horizontal", command=self._result_text.xview)
        self._result_text.configure(yscrollcommand=sb_y.set, xscrollcommand=sb_x.set)
        sb_y.pack(side=tk.RIGHT, fill=tk.Y)
        sb_x.pack(side=tk.BOTTOM, fill=tk.X)
        self._result_text.pack(fill=tk.BOTH, expand=True)

        # Chart frame
        self._chart_frame = tk.LabelFrame(parent, text="  Volume & Mass Chart  ",
                                          bg=THEME["panel"], fg=THEME["accent"],
                                          font=("Segoe UI", 9, "bold"), relief="groove", bd=1,
                                          height=260)
        self._chart_frame.pack(fill=tk.BOTH, expand=False, padx=4, pady=3)
        self._chart_frame.pack_propagate(False)

    # ── AGGREGATE / SCM / ADMIXTURE ADD/REMOVE ────────────────────────────────

    def _add_aggregate(self):
        row = AggregateRow(self._agg_container, len(self._agg_rows), self._remove_agg)
        self._agg_rows.append(row)

    def _remove_agg(self, row):
        row.frame.destroy()
        self._agg_rows.remove(row)

    def _add_scm(self):
        row = SCMRow(self._scm_container, self._remove_scm)
        self._scm_rows.append(row)

    def _remove_scm(self, row):
        row.frame.destroy()
        self._scm_rows.remove(row)

    def _add_admixture(self):
        row = AdmixtureRow(self._adm_container, self._remove_adm)
        self._adm_rows.append(row)

    def _remove_adm(self, row):
        row.frame.destroy()
        self._adm_rows.remove(row)

    def _add_default_aggregates(self):
        """Pre-load with typical fine + coarse aggregates."""
        # Fine
        self._add_aggregate()
        self._agg_rows[-1].vars["Name"].set("River Sand")
        self._agg_rows[-1].vars["Type"].set("fine")
        self._agg_rows[-1].vars["SG"].set("2.65")
        self._agg_rows[-1].vars["Abs%"].set("1.2")
        self._agg_rows[-1].vars["MC%"].set("3.0")
        self._agg_rows[-1].vars["BD kg/m³"].set("1650")
        self._agg_rows[-1].vars["Blend%"].set("40")

        # Coarse
        self._add_aggregate()
        self._agg_rows[-1].vars["Name"].set("Crushed Limestone")
        self._agg_rows[-1].vars["Type"].set("coarse")
        self._agg_rows[-1].vars["SG"].set("2.70")
        self._agg_rows[-1].vars["Abs%"].set("0.8")
        self._agg_rows[-1].vars["MC%"].set("0.5")
        self._agg_rows[-1].vars["BD kg/m³"].set("1580")
        self._agg_rows[-1].vars["Blend%"].set("60")

    # ── COLLECT INPUTS ────────────────────────────────────────────────────────

    def _collect_inputs(self) -> MixDesignInput:
        inp = MixDesignInput()
        inp.project_title = self.v_title.get().strip() or "Mix Design"
        inp.target_strength_mpa = float(self.v_fc.get())
        inp.design_margin_mpa = float(self.v_margin.get())
        inp.slump_mm = float(self.v_slump.get())
        inp.max_agg_size_mm = float(self.v_max_agg.get())
        inp.air_content_pct = float(self.v_air.get())
        inp.air_entrained = self.v_air_ent.get()
        inp.batch_volume_m3 = float(self.v_batch.get())
        inp.bag_mass_kg = float(self.v_bag_mass.get())
        inp.cement_factor_mode = self.v_cement_mode.get()
        inp.cement_factor_value = float(self.v_cement_value.get())
        inp.water_mode = self.v_water_mode.get()
        inp.water_manual_kg = float(self.v_water_manual.get())
        inp.scm_list = [r.get_data() for r in self._scm_rows]
        inp.aggregates = [r.get_data() for r in self._agg_rows]
        inp.admixtures = [r.get_data() for r in self._adm_rows]
        return inp

    # ── CALCULATE ─────────────────────────────────────────────────────────────

    def _calculate(self):
        try:
            inp = self._collect_inputs()
            res = calculate_mix(inp)
            self._last_result = res
            self._last_input = inp
            self._display_results(inp, res)
            if MATPLOTLIB_OK:
                plot_mix_proportions(inp, res, parent_frame=self._chart_frame)
        except Exception as e:
            messagebox.showerror("Calculation Error", str(e))

    def _display_results(self, inp: MixDesignInput, res: MixDesignResult):
        """Format and display results in the text area."""
        lines = []
        SEP = "─" * 60

        lines.append(SEP)
        lines.append(f"  ACI 211.1 MIX DESIGN RESULTS   (1 m³ basis)")
        lines.append(f"  Project: {inp.project_title}")
        lines.append(SEP)
        lines.append("")

        lines.append("  ┌── MIX PROPORTIONS (per 1 m³) ────────────────────┐")
        lines.append(f"  │ {'Material':<30} {'kg/m³':>8}  {'Vol (m³)':>9} │")
        lines.append("  ├────────────────────────────────────────────────────┤")

        def line(mat, kg, vol):
            return f"  │ {mat:<30} {kg:>8.2f}  {vol:>9.4f} │"

        lines.append(line("Portland Cement", res.cement_kg_m3, res.vol_cement))
        for i, scm in enumerate(inp.scm_list):
            lines.append(line(
                f"  SCM: {scm['name']} ({scm['replacement_pct']:.0f}%)",
                res.scm_kg_m3[i], res.vol_scm[i]
            ))
        lines.append(line("Mixing Water", res.water_kg_m3, res.vol_water))
        lines.append(line("Entrapped Air", 0.0, res.vol_air))
        for i, agg in enumerate(inp.aggregates):
            lines.append(line(
                f"  {agg['type'].title()} Agg: {agg['name']}",
                res.aggregate_kg_m3[i], res.vol_agg[i]
            ))
        lines.append("  ├────────────────────────────────────────────────────┤")
        total_kg = (res.cement_kg_m3 + sum(res.scm_kg_m3) + res.water_kg_m3
                    + sum(res.aggregate_kg_m3))
        lines.append(line("TOTAL", total_kg, res.vol_total))
        lines.append("  └────────────────────────────────────────────────────┘")
        lines.append("")

        # Key ratios
        bags = res.cement_kg_m3 / inp.bag_mass_kg
        lines.append("  ── KEY RATIOS ────────────────────────────────────")
        lines.append(f"  W/C  ratio (computed)  : {res.wc_ratio_computed:.4f}")
        lines.append(f"  W/CM ratio (computed)  : {res.wcm_ratio_computed:.4f}")
        lines.append(f"  Target W/C (user ref)  : {float(self.v_wc_input.get()):.4f}")
        lines.append(f"  Total Cementitious     : {res.total_cementitious_kg:.2f} kg/m³")
        lines.append(f"  Cement bags/m³         : {bags:.2f} bags  ({inp.bag_mass_kg:.0f} kg/bag)")
        lines.append(f"  Volume check           : {res.vol_total:.6f} m³  "
                     f"({'✓ OK' if abs(res.vol_total - 1.0) < 0.005 else '✗ CHECK'})")
        lines.append("")

        # Batch quantities
        lines.append(f"  ── BATCH QUANTITIES  ({inp.batch_volume_m3:.3f} m³) ───────────────")
        lines.append(f"  {'Material':<32} {'SSD kg':>9}  {'Field kg':>9}")
        lines.append(f"  {'Cement':<32} {res.batch_cement_kg:>9.2f}  {res.batch_cement_kg:>9.2f}")
        for i, scm in enumerate(inp.scm_list):
            scm_label = f"SCM: {scm['name']}"
            lines.append(f"  {scm_label:<32} {res.batch_scm_kg[i]:>9.2f}  {res.batch_scm_kg[i]:>9.2f}")
        lines.append(f"  {'Water':<32} {res.water_kg_m3 * inp.batch_volume_m3:>9.2f}  {res.batch_water_kg:>9.2f}  ← adjusted")
        for i, agg in enumerate(inp.aggregates):
            lines.append(f"  {agg['name']:<32} {res.batch_agg_kg[i]:>9.2f}  {res.batch_agg_adjusted_kg[i]:>9.2f}")
        for i, adm in enumerate(inp.admixtures):
            ml = res.admixture_ml_m3[i] * inp.batch_volume_m3
            lines.append(f"  Admix: {adm['name']:<25} {ml:>9.1f} mL")
        lines.append("")

        # Admixtures
        if inp.admixtures:
            lines.append("  ── ADMIXTURE DOSAGES (per m³) ──────────────────")
            for i, adm in enumerate(inp.admixtures):
                lines.append(f"  {adm['name']} ({adm['type']}): "
                              f"{res.admixture_ml_m3[i]:.1f} mL/m³  "
                              f"(≈ {res.admixture_kg_m3[i]:.3f} kg/m³)")
            lines.append("")

        # Warnings
        if res.warnings:
            lines.append("  ⚠ ENGINEERING WARNINGS:")
            for w in res.warnings:
                lines.append(f"    → {w}")
        else:
            lines.append("  ✓ No engineering warnings.")

        lines.append("")
        lines.append(SEP)
        lines.append(f"  Calculated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        lines.append(SEP)

        text = "\n".join(lines)
        self._result_text.configure(state=tk.NORMAL)
        self._result_text.delete("1.0", tk.END)
        self._result_text.insert(tk.END, text)
        self._result_text.configure(state=tk.DISABLED)

    # ── PDF ───────────────────────────────────────────────────────────────────

    def _generate_pdf(self):
        if not REPORTLAB_OK:
            messagebox.showerror("Missing Dependency",
                                 "reportlab is not installed.\nRun: pip install reportlab")
            return
        if self._last_result is None:
            messagebox.showwarning("No Results", "Please run Calculate first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Files", "*.pdf")],
            initialfile=f"{self._last_input.project_title.replace(' ', '_')}_MixDesign.pdf"
        )
        if not path:
            return
        try:
            generate_pdf(self._last_input, self._last_result, path)
            messagebox.showinfo("PDF Saved", f"Report saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("PDF Error", str(e))

    # ── CHART ─────────────────────────────────────────────────────────────────

    def _show_chart(self):
        if not MATPLOTLIB_OK:
            messagebox.showerror("Missing Dependency",
                                 "matplotlib is not installed.\nRun: pip install matplotlib")
            return
        if self._last_result is None:
            messagebox.showwarning("No Results", "Please run Calculate first.")
            return
        plot_mix_proportions(self._last_input, self._last_result, parent_frame=self._chart_frame)

    # ── SAVE / LOAD ───────────────────────────────────────────────────────────

    def _to_dict(self) -> dict:
        return {
            "project_title": self.v_title.get(),
            "target_strength_mpa": self.v_fc.get(),
            "design_margin_mpa": self.v_margin.get(),
            "slump_mm": self.v_slump.get(),
            "max_agg_size_mm": self.v_max_agg.get(),
            "air_content_pct": self.v_air.get(),
            "air_entrained": self.v_air_ent.get(),
            "batch_volume_m3": self.v_batch.get(),
            "bag_mass_kg": self.v_bag_mass.get(),
            "cement_factor_mode": self.v_cement_mode.get(),
            "cement_factor_value": self.v_cement_value.get(),
            "wc_input": self.v_wc_input.get(),
            "water_mode": self.v_water_mode.get(),
            "water_manual_kg": self.v_water_manual.get(),
            "scm_list": [r.get_data() for r in self._scm_rows],
            "aggregates": [r.get_data() for r in self._agg_rows],
            "admixtures": [r.get_data() for r in self._adm_rows],
        }

    def _from_dict(self, d: dict):
        self.v_title.set(d.get("project_title", ""))
        self.v_fc.set(d.get("target_strength_mpa", "28"))
        self.v_margin.set(d.get("design_margin_mpa", "8.3"))
        self.v_slump.set(d.get("slump_mm", "75"))
        self.v_max_agg.set(d.get("max_agg_size_mm", "19"))
        self.v_air.set(d.get("air_content_pct", "2.0"))
        self.v_air_ent.set(d.get("air_entrained", False))
        self.v_batch.set(d.get("batch_volume_m3", "1.0"))
        self.v_bag_mass.set(d.get("bag_mass_kg", "40"))
        self.v_cement_mode.set(d.get("cement_factor_mode", "kg/m³"))
        self.v_cement_value.set(d.get("cement_factor_value", "350"))
        self.v_wc_input.set(d.get("wc_input", "0.50"))
        self.v_water_mode.set(d.get("water_mode", "auto"))
        self.v_water_manual.set(d.get("water_manual_kg", "185"))

        # Rebuild SCMs
        for r in self._scm_rows[:]:
            self._remove_scm(r)
        for scm in d.get("scm_list", []):
            self._add_scm()
            self._scm_rows[-1].vars["SCM Name"].set(scm.get("name", ""))
            self._scm_rows[-1].vars["Replacement %"].set(scm.get("replacement_pct", ""))
            self._scm_rows[-1].vars["SG"].set(scm.get("sg", ""))

        # Rebuild aggregates
        for r in self._agg_rows[:]:
            self._remove_agg(r)
        for agg in d.get("aggregates", []):
            self._add_aggregate()
            row = self._agg_rows[-1]
            row.vars["Name"].set(agg.get("name", ""))
            row.vars["Type"].set(agg.get("type", "fine"))
            row.vars["SG"].set(agg.get("sg", "2.65"))
            row.vars["Abs%"].set(agg.get("absorption_pct", "1.0"))
            row.vars["MC%"].set(agg.get("moisture_pct", "0.0"))
            row.vars["BD kg/m³"].set(agg.get("bulk_density", "1600"))
            row.vars["Blend%"].set(agg.get("blend_pct", "100"))

        # Rebuild admixtures
        for r in self._adm_rows[:]:
            self._remove_adm(r)
        for adm in d.get("admixtures", []):
            self._add_admixture()
            row = self._adm_rows[-1]
            row.vars["Name"].set(adm.get("name", ""))
            row.vars["Type"].set(adm.get("type", ""))
            row.vars["Mode"].set(adm.get("dosage_mode", "ml/kg"))
            row.vars["Dosage"].set(adm.get("dosage", ""))

    def _save_design(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("Mix Design JSON", "*.json")],
            initialfile="mix_design.json"
        )
        if not path:
            return
        try:
            with open(path, "w") as f:
                json.dump(self._to_dict(), f, indent=2)
            messagebox.showinfo("Saved", f"Mix design saved to:\n{path}")
        except Exception as e:
            messagebox.showerror("Save Error", str(e))

    def _load_design(self):
        path = filedialog.askopenfilename(
            filetypes=[("Mix Design JSON", "*.json"), ("All Files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "r") as f:
                d = json.load(f)
            self._from_dict(d)
            messagebox.showinfo("Loaded", "Mix design loaded successfully.")
        except Exception as e:
            messagebox.showerror("Load Error", str(e))


# =============================================================================
# ─── 6. ENTRY POINT ──────────────────────────────────────────────────────────
# =============================================================================

if __name__ == "__main__":
    app = MixDesignApp()
    app.mainloop()