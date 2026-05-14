"""
design_engine.py
================
RC Column Design Engine — NSCP 2015 (7th Edition) / ACI 318-based provisions
adopted by the National Structural Code of the Philippines (NSCP).

Key references:
  - NSCP 2015 Section 410 (Members Subject to Flexure and Axial Loads)
  - NSCP 2015 Section 425 (Ties and Spirals)
  - Bresler's Reciprocal Load Method for biaxial bending

Engineering assumptions:
  - Whitney rectangular stress block (β₁ factor per NSCP 410.2.7)
  - Plane sections remain plane (strain compatibility)
  - Concrete tensile strength neglected
  - Units: N and mm throughout (MPa for stresses)
"""

import math
import numpy as np


# ---------------------------------------------------------------------------
# Constants & phi factors (NSCP 2015 Table 421.2.1)
# ---------------------------------------------------------------------------
PHI_TIED    = 0.65   # φ for tied columns (compression-controlled)
PHI_SPIRAL  = 0.75   # φ for spiral columns (compression-controlled)
PHI_TENSION = 0.90   # φ for tension-controlled sections
ES          = 200_000.0  # Modulus of elasticity of steel, MPa
EPSILON_U   = 0.003      # Maximum usable concrete strain (NSCP 410.2.3)

# Standard PNS bar sizes: (bar_designation, diameter_mm, area_mm2)
STANDARD_BARS = [
    ("10mm",  10,   78.54),
    ("12mm",  12,  113.10),
    ("16mm",  16,  201.06),
    ("20mm",  20,  314.16),
    ("25mm",  25,  490.87),
    ("28mm",  28,  615.75),
    ("32mm",  32,  804.25),
    ("36mm",  36, 1017.88),
    ("40mm",  40, 1256.64),
]


# ---------------------------------------------------------------------------
# Helper: Whitney stress-block β₁ factor (NSCP 410.2.7.3)
# ---------------------------------------------------------------------------
def beta1(fc: float) -> float:
    """
    Compute β₁ (Whitney stress-block depth factor).
    NSCP 410.2.7.3:
      β₁ = 0.85 for f'c ≤ 28 MPa
      β₁ decreases by 0.05 per 7 MPa above 28 MPa, min 0.65
    """
    if fc <= 28.0:
        return 0.85
    return max(0.85 - 0.05 * (fc - 28.0) / 7.0, 0.65)


# ---------------------------------------------------------------------------
# Helper: Net tensile strain → phi factor (NSCP Table 421.2.2)
# ---------------------------------------------------------------------------
def phi_factor(epsilon_t: float, column_type: str) -> float:
    """
    Interpolate φ between compression-controlled and tension-controlled limits.
    epsilon_t: net tensile strain at extreme tension reinforcement
    """
    phi_c = PHI_SPIRAL if column_type.lower() == "spiral" else PHI_TIED
    if epsilon_t <= 0.002:          # Compression-controlled
        return phi_c
    elif epsilon_t >= 0.005:        # Tension-controlled
        return PHI_TENSION
    else:                           # Transition region (linear interpolation)
        return phi_c + (PHI_TENSION - phi_c) * (epsilon_t - 0.002) / 0.003


# ---------------------------------------------------------------------------
# Section geometry helpers
# ---------------------------------------------------------------------------
def bar_positions_rectangular(b: float, h: float, cover: float,
                               db: float, n_bars: int):
    """
    Place n_bars uniformly around the perimeter of a rectangular section.
    Returns list of (y_i, A_si) where y_i is measured from the BOTTOM fiber.

    Layout rule: equal bars on each face (4 minimum).
    For n_bars not divisible by 4, extra bars go to the two bending faces.
    """
    dt = cover + db / 2.0   # distance from face to bar centroid (clear cover + half db)

    # Distribute: corners + equal spacing along each side
    positions = []
    bars_per_layer = n_bars // 2  # top + bottom groups (simplified uniform layout)

    # Determine unique y-positions for a symmetric layout
    y_top    = h - dt
    y_bottom = dt

    # Bars along h-face (sides): n_side bars per side
    # We build (y, area) pairs accounting for all bar rows
    # Simplified: equal layers at bottom, intermediate (sides), and top
    n_bottom = math.ceil(n_bars / 4)
    n_top    = math.ceil(n_bars / 4)
    n_side_total = n_bars - n_bottom - n_top  # remaining on two side faces
    n_side_each  = n_side_total // 2

    bar_area = math.pi * db**2 / 4.0

    # Bottom row
    for _ in range(n_bottom):
        positions.append((y_bottom, bar_area))

    # Side rows (linearly spaced between bottom and top)
    if n_side_each > 0:
        side_spacing = (y_top - y_bottom) / (n_side_each + 1)
        for i in range(1, n_side_each + 1):
            y_s = y_bottom + i * side_spacing
            positions.append((y_s, bar_area))  # left side
            positions.append((y_s, bar_area))  # right side (same y, symmetric)

    # Top row
    for _ in range(n_top):
        positions.append((y_top, bar_area))

    return positions


def bar_positions_circular(diameter: float, cover: float,
                            db: float, n_bars: int):
    """
    Place n_bars equally spaced on a circular section.
    Returns list of (y_i, A_si) measured from section centroid.
    """
    R = diameter / 2.0
    r_bar = R - cover - db / 2.0   # radius to bar centroids
    bar_area = math.pi * db**2 / 4.0
    positions = []
    for i in range(n_bars):
        angle = 2 * math.pi * i / n_bars  # starting from top
        y_i = r_bar * math.cos(angle)     # y measured from centroid
        positions.append((y_i, bar_area))
    return positions


# ---------------------------------------------------------------------------
# Core: Single-axis P-M interaction point via strain compatibility
# ---------------------------------------------------------------------------
def pn_mn_point_rectangular(b: float, h: float, cover: float,
                             fc: float, fy: float, db: float, n_bars: int,
                             c: float):
    """
    Compute (Pn, Mn) for a rectangular section at a given neutral-axis depth c.

    Sign convention: Compression positive for Pn.
    Moment is about the centroidal axis (h/2 from bottom).

    Returns (Pn_N, Mn_Nmm, epsilon_t)
    """
    b1   = beta1(fc)
    a    = min(b1 * c, h)   # depth of stress block, capped at h
    bar_pos = bar_positions_rectangular(b, h, cover, db, n_bars)

    # Concrete compression contribution
    Cc = 0.85 * fc * a * b   # N

    # Steel contributions
    Cs_total = 0.0
    Ms_total = 0.0
    epsilon_t = -999.0  # will be updated to most tensile bar strain

    for (y_i, A_si) in bar_pos:
        # Strain at bar (linear strain diagram from top fiber)
        # Top fiber: epsilon_u (compression), bottom fiber depends on c
        d_i = h - y_i  # distance from top (compression) fiber to bar
        eps_i = EPSILON_U * (c - d_i) / c  # positive = compression
        eps_i = max(min(eps_i, fy / ES), -fy / ES)  # cap at yield
        fs_i  = eps_i * ES                           # steel stress, MPa
        # Subtract concrete displaced by steel (only in compression zone)
        fc_conc = 0.85 * fc if d_i <= a else 0.0
        Fsi = A_si * (fs_i - fc_conc)   # N
        Cs_total += Fsi
        Ms_total += Fsi * (y_i - h / 2.0)  # moment about centroid

        # Track most tensile strain
        eps_actual = EPSILON_U * (c - d_i) / c   # no cap for strain check
        if eps_actual < epsilon_t or epsilon_t == -999.0:
            epsilon_t = eps_actual

    epsilon_t = -epsilon_t  # convert to net tensile strain (positive = tension)

    Pn = Cc + Cs_total   # N (positive = compression)
    Mn = Cc * (h / 2.0 - a / 2.0) + Ms_total  # N·mm (positive = sagging)
    return Pn, abs(Mn), max(epsilon_t, 0.0)


# ---------------------------------------------------------------------------
# Interaction diagram generation
# ---------------------------------------------------------------------------
def generate_interaction_diagram(b: float, h: float, cover: float,
                                  fc: float, fy: float, db: float,
                                  n_bars: int, column_type: str,
                                  section_type: str = "rectangular",
                                  n_points: int = 60):
    """
    Generate the nominal (Pn, Mn) and design (φPn, φMn) interaction diagrams.

    Returns dict with:
      'Pn_kN', 'Mn_kNm'     — nominal curve (compression +)
      'phiPn_kN', 'phiMn_kNm' — design curve
      'Pn0_kN'               — pure axial (no eccentricity)
      'phi_Pn0_kN'
      'Mnmax_kNm', 'phi_Mnmax_kNm'  — maximum moment capacity
    """
    Pn_list  = []
    Mn_list  = []
    phi_Pn_list = []
    phi_Mn_list = []

    # Range of neutral axis depths: from very large (pure compression) to
    # pure tension (c → 0)
    # Use c/h parameter from 0.01 to 5.0 (5× section depth covers pure axial)
    c_values = np.linspace(0.01 * h, 5.0 * h, n_points)

    for c in c_values:
        Pn, Mn, eps_t = pn_mn_point_rectangular(b, h, cover, fc, fy, db, n_bars, c)
        phi = phi_factor(eps_t, column_type)
        Pn_list.append(Pn / 1000.0)          # kN
        Mn_list.append(Mn / 1.0e6)           # kN·m
        phi_Pn_list.append(phi * Pn / 1000.0)
        phi_Mn_list.append(phi * Mn / 1.0e6)

    # --- Pure axial capacity (NSCP 410.5.1 / 410.5.2) ---
    bar_area_total = n_bars * math.pi * db**2 / 4.0
    Ag = b * h
    Ast = bar_area_total
    rho = Ast / Ag

    if column_type.lower() == "spiral":
        # NSCP 410.5.2: Pn0 = 0.85[0.85f'c(Ag-Ast) + fy·Ast]
        Pn0 = 0.85 * (0.85 * fc * (Ag - Ast) + fy * Ast)
        phi_Pn0 = PHI_SPIRAL * Pn0
    else:
        # NSCP 410.5.1: Pn0 = 0.80[0.85f'c(Ag-Ast) + fy·Ast]
        Pn0 = 0.80 * (0.85 * fc * (Ag - Ast) + fy * Ast)
        phi_Pn0 = PHI_TIED * Pn0

    # Cap the curve at Pn0 (per NSCP 410.5)
    Pn_list  = [min(p, Pn0 / 1000.0)   for p in Pn_list]
    phi_Pn_list = [min(p, phi_Pn0 / 1000.0) for p in phi_Pn_list]

    return {
        "Pn_kN":        np.array(Pn_list),
        "Mn_kNm":       np.array(Mn_list),
        "phiPn_kN":     np.array(phi_Pn_list),
        "phiMn_kNm":    np.array(phi_Mn_list),
        "Pn0_kN":       Pn0 / 1000.0,
        "phi_Pn0_kN":   phi_Pn0 / 1000.0,
        "Ag_mm2":       Ag,
        "Ast_mm2":      Ast,
        "rho":          rho,
    }


# ---------------------------------------------------------------------------
# Slenderness check & moment magnification (NSCP 410.10 — Nonsway frames)
# ---------------------------------------------------------------------------
def slenderness_check(lu: float, r_gyr: float, k: float = 1.0) -> dict:
    """
    Check column slenderness per NSCP 410.10.1.
    lu  : unsupported length, mm
    r_gyr: radius of gyration (= 0.30h for rectangular, 0.25D for circular), mm
    k   : effective length factor (default 1.0 for conservative pinned ends)

    Short column: klu/r ≤ 34 (for nonsway, M1/M2 conservatively = 1.0)
    Returns dict with slenderness ratio, is_slender flag, and magnified moment.
    """
    klu_r = k * lu / r_gyr
    is_slender = klu_r > 34.0  # Conservative limit per NSCP 410.10.1

    result = {
        "klu_r":      round(klu_r, 2),
        "is_slender": is_slender,
        "limit":      34.0,
        "note":       "Long column — moment magnification required (NSCP 410.10.2)"
                      if is_slender else "Short column — slenderness effects may be neglected",
    }
    return result


def moment_magnifier_nonsway(Pu: float, Cm: float, EI: float,
                              lu: float, k: float = 1.0) -> float:
    """
    Compute moment magnifier δns for nonsway frames (NSCP 410.10.6).
    Pu : factored axial load, N
    Cm : equivalent uniform moment factor (0.6 to 1.0; conservative = 1.0)
    EI : flexural stiffness, N·mm² (use 0.4*Ec*Ig for conservatism)
    lu : unsupported length, mm
    Returns δns ≥ 1.0
    """
    Pc = math.pi**2 * EI / (k * lu)**2   # Euler critical load, N
    delta = Cm / (1.0 - Pu / (0.75 * Pc))
    return max(delta, 1.0)


# ---------------------------------------------------------------------------
# Biaxial bending — Bresler's Reciprocal Load Method (NSCP 410.5.3)
# ---------------------------------------------------------------------------
def bresler_check(Pu: float, phi_Pnx: float, phi_Pny: float,
                  phi_Pn0: float) -> dict:
    """
    Bresler's Reciprocal Load Method for biaxial bending.
    Checks: 1/φPni ≈ 1/φPnx + 1/φPny - 1/φPn0

    Pu      : factored axial load, kN
    phi_Pnx : uniaxial design capacity at Mux eccentricity, kN
    phi_Pny : uniaxial design capacity at Muy eccentricity, kN
    phi_Pn0 : pure axial design capacity, kN

    Returns dict with φPni (approx. biaxial capacity) and DCR.
    """
    if phi_Pnx <= 0 or phi_Pny <= 0 or phi_Pn0 <= 0:
        return {"phi_Pni_kN": 0.0, "DCR": 999.0, "status": "FAIL"}

    inv_Pni = (1.0 / phi_Pnx) + (1.0 / phi_Pny) - (1.0 / phi_Pn0)
    if inv_Pni <= 0:
        return {"phi_Pni_kN": 999.0, "DCR": 0.0, "status": "PASS"}

    phi_Pni = 1.0 / inv_Pni
    DCR     = Pu / phi_Pni

    return {
        "phi_Pni_kN": round(phi_Pni, 2),
        "DCR":        round(DCR, 4),
        "status":     "PASS" if DCR <= 1.0 else "FAIL",
    }


# ---------------------------------------------------------------------------
# Interpolate design capacity at a given eccentricity from the diagram
# ---------------------------------------------------------------------------
def capacity_at_eccentricity(pu_demand: float, mu_demand: float,
                              phi_pn_arr, phi_mn_arr) -> float:
    """
    Find the φPn capacity on the interaction diagram at the eccentricity
    defined by the demand point (Pu, Mu).

    Strategy:
      The interaction curve traces from high Pn (pure compression) down through
      the balanced point to pure tension.  Along this path, eccentricity e = Mn/Pn
      increases monotonically from ~0 (pure axial) through ∞ (pure bending).

      We sort the curve by descending Pn (so eccentricity increases along the
      sorted array), then find the bracketing segment for ecc_demand and
      interpolate.

    Returns φPn at that eccentricity (kN). Returns 0 if outside diagram.
    """
    phi_pn_arr = np.asarray(phi_pn_arr, dtype=float)
    phi_mn_arr = np.asarray(phi_mn_arr, dtype=float)

    if pu_demand == 0 and mu_demand == 0:
        return float(np.max(phi_pn_arr))

    if pu_demand == 0:
        # Pure bending — return max moment capacity
        return float(np.max(phi_mn_arr))

    ecc_demand = mu_demand / pu_demand   # kN·m / kN  → m  (or mm/mm, dimensionless ratio)

    # Keep only compression (Pn > 0) part of the diagram and sort by descending Pn
    mask    = phi_pn_arr > 0
    pn_comp = phi_pn_arr[mask]
    mn_comp = phi_mn_arr[mask]

    if len(pn_comp) == 0:
        return 0.0

    sort_idx = np.argsort(pn_comp)[::-1]   # high Pn → low Pn
    pn_s = pn_comp[sort_idx]
    mn_s = mn_comp[sort_idx]

    # Eccentricities along the sorted curve (monotonically increasing)
    ecc_s = np.where(pn_s > 1e-6, mn_s / pn_s, 1e9)

    # Demand eccentricity above maximum axial: column over-loaded in compression
    if ecc_demand < ecc_s[0]:
        return float(pn_s[0])

    # Demand eccentricity beyond pure-bending limit: demand outside diagram
    if ecc_demand > ecc_s[-1]:
        return 0.0

    # Bracket and linearly interpolate
    idx = np.searchsorted(ecc_s, ecc_demand)
    if idx == 0:
        return float(pn_s[0])
    if idx >= len(ecc_s):
        return float(pn_s[-1])

    e1, e2 = ecc_s[idx - 1], ecc_s[idx]
    p1, p2 = pn_s[idx - 1], pn_s[idx]
    if abs(e2 - e1) < 1e-12:
        return float(p1)
    phi_pn_interp = p1 + (p2 - p1) * (ecc_demand - e1) / (e2 - e1)
    return float(max(phi_pn_interp, 0.0))


# ---------------------------------------------------------------------------
# Reinforcement ratio check (NSCP 410.6.1)
# ---------------------------------------------------------------------------
def check_rho(rho: float) -> dict:
    """
    NSCP 410.6.1.1: 0.01 ≤ ρg ≤ 0.08
    """
    status = "PASS" if 0.01 <= rho <= 0.08 else "FAIL"
    note   = ""
    if rho < 0.01:
        note = "ρ < 1% — increase steel area (NSCP 410.6.1.1)"
    elif rho > 0.08:
        note = "ρ > 8% — reduce steel area or increase section (NSCP 410.6.1.1)"
    return {"rho": round(rho, 4), "rho_pct": round(rho * 100, 2),
            "status": status, "note": note}


# ---------------------------------------------------------------------------
# Tie requirements (NSCP 425.7)
# ---------------------------------------------------------------------------
def tie_requirements(db_main: float, db_tie: float = None) -> dict:
    """
    NSCP 425.7.2 — Lateral tie spacing and size.
    db_main: main bar diameter, mm
    db_tie : tie bar diameter (if None, auto-selected)

    Minimum tie bar:
      - 10mm ties for main bars ≤ 32mm
      - 12mm ties for main bars > 32mm (bundled)

    Maximum tie spacing (smallest of):
      - 16 × db_main
      - 48 × db_tie
      - Least column dimension
    """
    if db_tie is None:
        db_tie = 10.0 if db_main <= 32.0 else 12.0

    s_max_1 = 16.0 * db_main
    s_max_2 = 48.0 * db_tie
    note = (f"Tie spacing ≤ min(16×{db_main:.0f} = {s_max_1:.0f}mm, "
            f"48×{db_tie:.0f} = {s_max_2:.0f}mm, least column dimension)")
    return {
        "db_tie_mm":    db_tie,
        "s_max_16db":   round(s_max_1, 1),
        "s_max_48dt":   round(s_max_2, 1),
        "note":         note,
    }


# ---------------------------------------------------------------------------
# Spiral requirements (NSCP 425.7.3)
# ---------------------------------------------------------------------------
def spiral_requirements(Ag: float, Ach: float, fc: float, fy: float,
                         ds: float) -> dict:
    """
    NSCP 425.7.3 — Minimum spiral reinforcement ratio.
    Ag  : gross section area, mm²
    Ach : core area (to outside of spiral), mm²
    fc  : concrete compressive strength, MPa
    fy  : spiral steel yield strength (≤ 700 MPa per NSCP), MPa
    ds  : spiral bar diameter, mm

    ρs_min = 0.45(Ag/Ach - 1)(f'c/fyh)
    """
    fy_s   = min(fy, 700.0)
    rho_s_min = 0.45 * (Ag / Ach - 1.0) * (fc / fy_s)
    # Spiral pitch: s ≤ 75mm and s ≥ 25mm (NSCP 425.7.3.3)
    As_sp  = math.pi * ds**2 / 4.0
    Dcore  = math.sqrt(4 * Ach / math.pi)  # core diameter
    s_req  = (4 * As_sp) / (rho_s_min * Dcore)
    s_req  = min(s_req, 75.0)
    s_req  = max(s_req, 25.0)
    return {
        "rho_s_min":   round(rho_s_min, 5),
        "s_max_mm":    round(s_req, 1),
        "db_spiral_mm": ds,
        "note":        f"Spiral pitch ≤ {s_req:.1f} mm (25 ≤ s ≤ 75 mm per NSCP 425.7.3.3)",
    }


# ---------------------------------------------------------------------------
# Auto-suggest bar configuration
# ---------------------------------------------------------------------------
def suggest_bar_config(As_required: float, section_perimeter: float,
                        min_bars: int = 4) -> list:
    """
    Suggest viable bar configurations (n_bars, db) whose total area
    meets or exceeds As_required, fitting within section perimeter
    with minimum 40mm clear spacing (NSCP 426.4.2.1).

    Returns list of dicts sorted by area efficiency.
    """
    suggestions = []
    for name, db, ab in STANDARD_BARS:
        n_min_area = math.ceil(As_required / ab)
        n = max(n_min_area, min_bars)
        # Check minimum clear spacing (simplified)
        # Clear spacing ≈ perimeter/n - db ≥ 40mm
        clear_sp = section_perimeter / n - db
        if clear_sp < 40.0:
            n_max = int(section_perimeter / (db + 40.0))
            if n_max < min_bars:
                continue
            n = n_max
        As_provided = n * ab
        if As_provided >= As_required:
            suggestions.append({
                "bar_size":       name,
                "db_mm":          db,
                "n_bars":         n,
                "As_mm2":         round(As_provided, 1),
                "rho_check":      None,  # filled in by caller
                "clear_sp_mm":    round(section_perimeter / n - db, 1),
            })
    return suggestions[:5]  # top 5 options


# ---------------------------------------------------------------------------
# Master design function
# ---------------------------------------------------------------------------
def design_column(params: dict) -> dict:
    """
    Run full RC column design for given parameters.

    params keys:
      b, h           : section dimensions (mm); if circular, b = h = diameter
      fc             : f'c (MPa)
      fy             : fy (MPa)
      Pu             : factored axial load (kN)  ← input in kN
      Mux            : factored moment about x-axis (kN·m)
      Muy            : factored moment about y-axis (kN·m)
      cover          : clear cover (mm)
      db             : main bar diameter (mm)
      n_bars         : number of main bars
      column_type    : 'tied' or 'spiral'
      section_type   : 'rectangular' or 'circular'
      lu             : unsupported length (mm)
      k              : effective length factor

    Returns comprehensive result dict.
    """
    b    = float(params["b"])
    h    = float(params["h"])
    fc   = float(params["fc"])
    fy   = float(params["fy"])
    Pu   = float(params["Pu"]) * 1000.0   # → N
    Mux  = float(params["Mux"]) * 1.0e6   # → N·mm
    Muy  = float(params["Muy"]) * 1.0e6   # → N·mm
    cover = float(params["cover"])
    db   = float(params["db"])
    n    = int(params["n_bars"])
    col_type   = params["column_type"]
    sec_type   = params.get("section_type", "rectangular")
    lu   = float(params.get("lu", 3000.0))
    k    = float(params.get("k", 1.0))

    results = {}

    # ---- Section properties ----
    Ag  = b * h
    Ast = n * math.pi * db**2 / 4.0
    rho = Ast / Ag
    r_gyr = 0.30 * h   # radius of gyration (rectangular: 0.30h)

    results["section"] = {
        "Ag_mm2":  round(Ag, 1),
        "Ast_mm2": round(Ast, 1),
        "rho":     round(rho, 4),
        "rho_pct": round(rho * 100, 2),
    }

    # ---- Reinforcement ratio check ----
    results["rho_check"] = check_rho(rho)

    # ---- Interaction diagram (x-axis bending) ----
    diag = generate_interaction_diagram(b, h, cover, fc, fy, db, n,
                                         col_type, sec_type)
    results["diagram"] = diag

    # ---- Slenderness ----
    results["slenderness"] = slenderness_check(lu, r_gyr, k)

    # ---- Uniaxial checks ----
    # x-axis (bending about x, eccentricity in h-direction)
    ex = Mux / Pu if Pu > 0 else 0.0   # mm
    ey = Muy / Pu if Pu > 0 else 0.0   # mm

    phi_Pnx = capacity_at_eccentricity(Pu / 1000.0,
                                        Mux / 1.0e6,
                                        diag["phiPn_kN"],
                                        diag["phiMn_kNm"])

    # y-axis: use transposed section (swap b and h) for Muy
    diag_y = generate_interaction_diagram(h, b, cover, fc, fy, db, n,
                                           col_type, sec_type)
    phi_Pny = capacity_at_eccentricity(Pu / 1000.0,
                                        Muy / 1.0e6,
                                        diag_y["phiPn_kN"],
                                        diag_y["phiMn_kNm"])

    phi_Pn0 = diag["phi_Pn0_kN"]

    # Demand/Capacity ratios for uniaxial
    DCR_x = (Pu / 1000.0) / phi_Pnx if phi_Pnx > 0 else 999.0
    DCR_y = (Pu / 1000.0) / phi_Pny if phi_Pny > 0 else 999.0

    results["uniaxial_x"] = {
        "phi_Pn_kN": round(phi_Pnx, 2),
        "ex_mm":     round(ex, 1),
        "DCR":       round(DCR_x, 4),
        "status":    "PASS" if DCR_x <= 1.0 else "FAIL",
    }
    results["uniaxial_y"] = {
        "phi_Pn_kN": round(phi_Pny, 2),
        "ey_mm":     round(ey, 1),
        "DCR":       round(DCR_y, 4),
        "status":    "PASS" if DCR_y <= 1.0 else "FAIL",
    }

    # ---- Biaxial check (Bresler) ----
    results["biaxial"] = bresler_check(Pu / 1000.0,
                                        phi_Pnx, phi_Pny, phi_Pn0)

    # ---- Lateral reinforcement ----
    if col_type.lower() == "tied":
        results["lateral"] = tie_requirements(db)
    else:
        Ach = (b - 2 * cover) * (h - 2 * cover)
        results["lateral"] = spiral_requirements(Ag, Ach, fc, fy, 10.0)

    # ---- Bar suggestions ----
    As_min = 0.01 * Ag
    perim  = 2 * (b + h)
    results["bar_suggestions"] = suggest_bar_config(max(Ast, As_min), perim)

    # ---- Overall status ----
    all_checks = [
        results["rho_check"]["status"],
        results["uniaxial_x"]["status"],
        results["uniaxial_y"]["status"],
        results["biaxial"]["status"],
    ]
    results["overall_status"] = "PASS" if all(s == "PASS" for s in all_checks) else "FAIL"

    # ---- Summary values (convenience) ----
    results["summary"] = {
        "Pu_kN":        round(Pu / 1000.0, 2),
        "Mux_kNm":      round(Mux / 1.0e6, 2),
        "Muy_kNm":      round(Muy / 1.0e6, 2),
        "phi_Pn0_kN":   round(phi_Pn0, 2),
        "phi_Pnx_kN":   round(phi_Pnx, 2),
        "phi_Pny_kN":   round(phi_Pny, 2),
        "phi_Pni_kN":   results["biaxial"]["phi_Pni_kN"],
        "rho_pct":      round(rho * 100, 2),
        "Ast_mm2":      round(Ast, 1),
        "DCR_biaxial":  results["biaxial"]["DCR"],
        "overall":      results["overall_status"],
    }

    return results