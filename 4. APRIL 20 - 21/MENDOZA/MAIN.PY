"""
=============================================================================
  CANTILEVER CONCRETE RETAINING WALL — ANALYSIS & DESIGN
  NSCP 2015 (National Structural Code of the Philippines)
  Ultimate Strength Design (USD) | 1-Metre Unit Strip Method
=============================================================================
  Units  : Forces → kN, kN/m, kN/m²
            Lengths → m  (geometry inputs)
            Reinforcement checks → mm, mm², MPa
  Strip  : All forces and moments are per 1-metre length of wall (b = 1 m).
=============================================================================
"""

import math


# ─────────────────────────────────────────────────────────────────────────────
# HELPER UTILITIES
# ─────────────────────────────────────────────────────────────────────────────

def bar_area_mm2(dia_mm: float) -> float:
    """Cross-sectional area of a single reinforcing bar (mm²)."""
    return math.pi / 4.0 * dia_mm ** 2


def spacing_mm(As_req_per_m: float, dia_mm: float) -> float:
    """
    Centre-to-centre bar spacing (mm) for a 1-m wide strip.

    Parameters
    ----------
    As_req_per_m : float  – required steel area in mm²/m
    dia_mm       : float  – chosen bar diameter in mm

    Returns
    -------
    spacing in mm (rounded DOWN to nearest 5 mm for conservatism)
    """
    if As_req_per_m <= 0:
        return 999.0  # no steel needed — return a large sentinel
    Ab = bar_area_mm2(dia_mm)
    s = (Ab / As_req_per_m) * 1000.0   # 1 m = 1000 mm
    # round DOWN to nearest 5 mm so we never under-provide steel
    s = math.floor(s / 5.0) * 5.0
    return max(s, 50.0)                 # practical minimum 50 mm


def section_divider(title: str = "", width: int = 72) -> str:
    """Pretty console divider."""
    if title:
        side = (width - len(title) - 2) // 2
        return f"\n{'─' * side} {title} {'─' * side}"
    return "─" * width


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 1 — WALL DEFINITION (Inputs & Material Properties)
# ─────────────────────────────────────────────────────────────────────────────

class RetainingWallInputs:
    """
    All geometry, soil, and material parameters for a cantilever retaining
    wall, per the 1-metre unit strip convention.

    Geometry Reference
    ------------------
    ::

        ←── B_base ───────────────────────────────────→
        ←B_toe→ ←──── t_stem_bot ────→ ←── B_heel ───→
                  t_stem_top (at top)
                 ┌──┐
                 │  │                        ← H_stem (above base top)
                 │  │  (stem tapers or
                 │  │   uniform)
                 │  │
                ─┘  └──────────────────────────────────
                │  ←t_stem_bot→                        │ t_base
                └──────────────────────────────────────┘
        ← D_toe cover soil →

    Sign / axis convention
    ----------------------
    Overturning moments are taken about the TOE of the base slab.
    """

    def __init__(
        self,
        # ── Geometry (metres) ──────────────────────────────────────────────
        H_stem: float,          # clear height of stem above top of base slab
        t_stem_top: float,      # stem thickness at top (m)
        t_stem_bot: float,      # stem thickness at bottom / base interface (m)
        B_toe: float,           # toe projection beyond front face of stem (m)
        B_heel: float,          # heel projection beyond back face of stem (m)
        t_base: float,          # base slab thickness (m)
        D_cover_toe: float,     # depth of soil cover at toe (m)
        # ── Soil Mechanics ─────────────────────────────────────────────────
        gamma_s: float,         # backfill unit weight (kN/m³)
        phi_deg: float,         # angle of internal friction (degrees)
        cohesion: float,        # cohesion c (kN/m²); 0 for granular backfill
        q_allow: float,         # allowable bearing capacity (kN/m²)
        surcharge: float = 0.0, # uniform surcharge on backfill (kN/m²)
        # ── Material Properties ────────────────────────────────────────────
        fc_MPa: float = 28.0,   # f'c — concrete compressive strength (MPa)
        fy_MPa: float = 415.0,  # fy  — steel yield strength (MPa)
        gamma_c: float = 23.54, # concrete unit weight (kN/m³) ≈ 2400 kg/m³
        # ── Detailing Preferences ──────────────────────────────────────────
        cover_mm: float = 75.0,          # clear cover to main steel (mm)
        main_bar_dia_mm: float = 16.0,   # preferred main bar diameter (mm)
        temp_bar_dia_mm: float = 12.0,   # preferred shrinkage/temp bar (mm)
        mu_base: float = None,  # base friction; if None → tan(2φ/3)
    ):
        # ── Store geometry ─────────────────────────────────────────────────
        self.H_stem       = H_stem
        self.t_stem_top   = t_stem_top
        self.t_stem_bot   = t_stem_bot
        self.B_toe        = B_toe
        self.B_heel       = B_heel
        self.t_base       = t_base
        self.D_cover_toe  = D_cover_toe

        # ── Derived geometry ───────────────────────────────────────────────
        self.H_total = H_stem + t_base               # total wall height (m)
        self.B_base  = B_toe + t_stem_bot + B_heel   # total base width (m)

        # ── Soil ───────────────────────────────────────────────────────────
        self.gamma_s   = gamma_s
        self.phi_rad   = math.radians(phi_deg)
        self.phi_deg   = phi_deg
        self.cohesion  = cohesion
        self.q_allow   = q_allow
        self.surcharge = surcharge

        # Rankine active & passive pressure coefficients
        self.Ka = math.tan(math.radians(45.0 - phi_deg / 2.0)) ** 2
        self.Kp = math.tan(math.radians(45.0 + phi_deg / 2.0)) ** 2

        # Base friction coefficient: typically tan(2φ/3) for concrete-on-soil
        if mu_base is None:
            self.mu = math.tan(2.0 * self.phi_rad / 3.0)
        else:
            self.mu = mu_base

        # ── Materials ──────────────────────────────────────────────────────
        self.fc      = fc_MPa
        self.fy      = fy_MPa
        self.gamma_c = gamma_c

        # ── Detailing ──────────────────────────────────────────────────────
        self.cover_mm     = cover_mm
        self.main_bar_dia = main_bar_dia_mm
        self.temp_bar_dia = temp_bar_dia_mm

        # Effective depths (mm) — main steel effective depth for each section
        # d = section thickness − clear cover − ½ bar diameter
        self.d_stem_mm = (t_stem_bot * 1000.0
                          - cover_mm - main_bar_dia_mm / 2.0)
        self.d_heel_mm = (t_base * 1000.0
                          - cover_mm - main_bar_dia_mm / 2.0)
        self.d_toe_mm  = self.d_heel_mm   # same slab thickness

    def echo(self):
        """Print a formatted summary of all input parameters."""
        print(section_divider("MODULE 1 — INPUTS"))
        print(f"  Stem Height (H_stem)          : {self.H_stem:.3f} m")
        print(f"  Total Wall Height (H_total)   : {self.H_total:.3f} m")
        print(f"  Stem Thickness (top / bot)    : {self.t_stem_top:.3f} / "
              f"{self.t_stem_bot:.3f} m")
        print(f"  Base: Toe / Heel / Thickness  : {self.B_toe:.3f} / "
              f"{self.B_heel:.3f} / {self.t_base:.3f} m")
        print(f"  Total Base Width (B_base)     : {self.B_base:.3f} m")
        print(f"  Soil Cover at Toe             : {self.D_cover_toe:.3f} m")
        print(f"  Backfill Unit Weight          : {self.gamma_s:.2f} kN/m³")
        print(f"  Friction Angle φ              : {self.phi_deg:.1f}°")
        print(f"  Cohesion c                    : {self.cohesion:.2f} kN/m²")
        print(f"  Surcharge q                   : {self.surcharge:.2f} kN/m²")
        print(f"  Allowable Bearing qₐ          : {self.q_allow:.2f} kN/m²")
        print(f"  Ka / Kp (Rankine)             : {self.Ka:.4f} / {self.Kp:.4f}")
        print(f"  Base Friction μ               : {self.mu:.4f}")
        print(f"  f'c                           : {self.fc:.1f} MPa")
        print(f"  fy                            : {self.fy:.1f} MPa")
        print(f"  Concrete Unit Weight γc       : {self.gamma_c:.2f} kN/m³")
        print(f"  Clear Cover                   : {self.cover_mm:.0f} mm")
        print(f"  Main Bar / Temp Bar Diameter  : {self.main_bar_dia:.0f} mm / "
              f"{self.temp_bar_dia:.0f} mm")
        print(f"  Effective Depth — Stem        : {self.d_stem_mm:.1f} mm")
        print(f"  Effective Depth — Base Slab   : {self.d_heel_mm:.1f} mm")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 2 — EXTERNAL STABILITY (Service Loads)
# ─────────────────────────────────────────────────────────────────────────────

class StabilityAnalysis:
    """
    Computes overturning, sliding, and bearing pressure checks under
    UNFACTORED (service) loads.  All forces are per 1-m strip.

    Moment convention
    -----------------
    Moments are taken about the TOE of the base slab.
    Resisting moments are positive; overturning moments are positive magnitudes
    compared separately.
    """

    def __init__(self, w: RetainingWallInputs):
        self.w = w
        self._compute()

    def _compute(self):
        w = self.w

        # ── 1. Active Earth Pressure (Rankine) ────────────────────────────
        H  = w.H_total   # total height over which pressure acts
        Ka = w.Ka
        gs = w.gamma_s
        q  = w.surcharge

        # Triangular pressure (soil weight): pa = ½ Ka γs H²  at H/3 from base
        self.Pa_tri      = 0.5 * Ka * gs * H ** 2
        self.y_Pa_tri    = H / 3.0

        # Rectangular surcharge pressure: pa_rect = Ka q H  at H/2 from base
        self.Pa_surcharge     = Ka * q * H
        self.y_Pa_surcharge   = H / 2.0

        # Total horizontal driving force (kN/m)
        self.Pa_total = self.Pa_tri + self.Pa_surcharge

        # ── 2. Passive Resistance at Toe ──────────────────────────────────
        # Depth of passive soil = toe cover + base thickness
        Dp = w.D_cover_toe + w.t_base
        self.Pp = 0.5 * w.Kp * gs * Dp ** 2

        # ── 3. Weight Components & Moment Arms from Toe ───────────────────
        B  = w.B_base
        bt = w.B_toe
        ts = w.t_stem_bot
        th = w.t_base
        Hs = w.H_stem
        gc = w.gamma_c

        # W1 — base slab self-weight (full base width × thickness × 1 m)
        self.W1 = gc * B * th * 1.0
        self.x1 = B / 2.0                        # centroid from toe

        # W2 — stem self-weight (trapezoidal; simplified to average thickness)
        t_avg_stem = (w.t_stem_top + w.t_stem_bot) / 2.0
        self.W2 = gc * t_avg_stem * Hs * 1.0
        # Centroid of stem from toe = B_toe + half stem width (simplified rect.)
        self.x2 = bt + ts / 2.0

        # W3 — soil on heel (from back face of stem to end of heel)
        # Height of soil column over heel = H_stem + t_base (full depth)
        self.W3 = gs * w.B_heel * (Hs + th) * 1.0
        self.x3 = B - w.B_heel / 2.0             # centroid from toe

        # W4 — soil on toe (small passive cover wedge, resisting)
        self.W4 = gs * bt * w.D_cover_toe * 1.0
        self.x4 = bt / 2.0

        # W5 — surcharge load on heel surface (live)
        self.W5 = q * w.B_heel * 1.0
        self.x5 = self.x3

        # Total vertical load (kN/m)
        self.N_total = self.W1 + self.W2 + self.W3 + self.W4 + self.W5

        # ── 4. Overturning Moment (about toe) ─────────────────────────────
        self.M_OT = (self.Pa_tri * self.y_Pa_tri
                     + self.Pa_surcharge * self.y_Pa_surcharge)

        # ── 5. Resisting Moment (about toe) ───────────────────────────────
        self.M_R = (self.W1 * self.x1
                    + self.W2 * self.x2
                    + self.W3 * self.x3
                    + self.W4 * self.x4
                    + self.W5 * self.x5)

        # ── 6. FS — Overturning ───────────────────────────────────────────
        self.FS_OT = self.M_R / self.M_OT

        # ── 7. FS — Sliding ───────────────────────────────────────────────
        self.F_friction     = w.mu * self.N_total
        self.F_passive      = self.Pp
        self.F_resist_slide = self.F_friction + self.F_passive
        self.F_drive_slide  = self.Pa_total
        self.FS_slide       = self.F_resist_slide / self.F_drive_slide

        # ── 8. Bearing Pressure (eccentricity method) ─────────────────────
        # Resultant x from toe: x_R = (M_R − M_OT) / N_total
        self.x_R    = (self.M_R - self.M_OT) / self.N_total
        # Eccentricity about base centroid
        self.e      = B / 2.0 - self.x_R
        self.e_allow = B / 6.0   # middle-third rule

        # Trapezoidal distribution: q = N/B ± 6Ne/B²
        self.q_max = (self.N_total / B) * (1.0 + 6.0 * self.e / B)
        self.q_min = (self.N_total / B) * (1.0 - 6.0 * self.e / B)

        # Status flags
        self.ok_OT    = self.FS_OT   >= 2.0
        self.ok_slide = self.FS_slide >= 1.5
        self.ok_e     = abs(self.e)  <= self.e_allow
        self.ok_qmax  = self.q_max   <= w.q_allow

    def report(self):
        w = self.w
        print(section_divider("MODULE 2 — EXTERNAL STABILITY (Service Loads)"))

        print("\n  ── Weight Components ──────────────────────────────────────")
        print(f"  W1 (Base Slab)         : {self.W1:>8.3f} kN/m  arm = {self.x1:.3f} m")
        print(f"  W2 (Stem)              : {self.W2:>8.3f} kN/m  arm = {self.x2:.3f} m")
        print(f"  W3 (Soil on Heel)      : {self.W3:>8.3f} kN/m  arm = {self.x3:.3f} m")
        print(f"  W4 (Soil on Toe)       : {self.W4:>8.3f} kN/m  arm = {self.x4:.3f} m")
        print(f"  W5 (Surcharge on Heel) : {self.W5:>8.3f} kN/m  arm = {self.x5:.3f} m")
        print(f"  ΣV (N_total)           : {self.N_total:>8.3f} kN/m")

        print("\n  ── Lateral Forces ─────────────────────────────────────────")
        print(f"  Pa (triangular)        : {self.Pa_tri:>8.3f} kN/m  "
              f"arm = {self.y_Pa_tri:.3f} m")
        print(f"  Pa (surcharge rect.)   : {self.Pa_surcharge:>8.3f} kN/m  "
              f"arm = {self.y_Pa_surcharge:.3f} m")
        print(f"  Pa TOTAL               : {self.Pa_total:>8.3f} kN/m")
        print(f"  Pp (passive at toe)    : {self.Pp:>8.3f} kN/m")

        print("\n  ── Overturning ────────────────────────────────────────────")
        print(f"  Overturning Moment MOT : {self.M_OT:>8.3f} kN·m/m")
        print(f"  Resisting Moment MR    : {self.M_R:>8.3f} kN·m/m")
        flag = "✓  PASS" if self.ok_OT else "✗  FAIL"
        print(f"  FS_overturning         : {self.FS_OT:>8.3f}  (req ≥ 2.0)  [{flag}]")

        print("\n  ── Sliding ────────────────────────────────────────────────")
        print(f"  Base Friction (μN)     : {self.F_friction:>8.3f} kN/m  (μ = {w.mu:.4f})")
        print(f"  Passive Resistance     : {self.F_passive:>8.3f} kN/m")
        print(f"  Total Resistance       : {self.F_resist_slide:>8.3f} kN/m")
        print(f"  Driving Force          : {self.F_drive_slide:>8.3f} kN/m")
        flag = "✓  PASS" if self.ok_slide else "✗  FAIL"
        print(f"  FS_sliding             : {self.FS_slide:>8.3f}  (req ≥ 1.5)  [{flag}]")

        print("\n  ── Bearing Pressure ───────────────────────────────────────")
        print(f"  Resultant x from Toe   : {self.x_R:>8.3f} m")
        print(f"  Eccentricity e         : {self.e:>8.3f} m")
        print(f"  Middle-third limit B/6 : {self.e_allow:>8.3f} m")
        flag_e = "✓  PASS" if self.ok_e else "✗  FAIL — Tension under footing!"
        print(f"  |e| ≤ B/6              :          [{flag_e}]")
        print(f"  q_max                  : {self.q_max:>8.3f} kN/m²")
        print(f"  q_min                  : {self.q_min:>8.3f} kN/m²")
        flag_q = "✓  PASS" if self.ok_qmax else "✗  FAIL — Exceeds q_allow!"
        print(f"  q_allow                : {w.q_allow:>8.3f} kN/m²  [{flag_q}]")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 3 — INTERNAL FORCES (Factored Loads, NSCP 2015)
# ─────────────────────────────────────────────────────────────────────────────

class InternalForces:
    """
    Factored Mu and Vu at the three critical sections using NSCP 2015
    load combinations.

    ┌──────────┬──────────────────────────────────────────────────────────┐
    │ Section  │ Description                                              │
    ├──────────┼──────────────────────────────────────────────────────────┤
    │ STEM     │ Vertical cantilever fixed at footing top.                │
    │          │ Load: active earth pressure + surcharge.                 │
    │          │ U = 1.6H + 1.6L (no gravity dead load in horizontal dir) │
    ├──────────┼──────────────────────────────────────────────────────────┤
    │ HEEL     │ Horizontal cantilever from back of stem.                 │
    │          │ Upward: bearing pressure; Downward: soil + slab weight.  │
    │          │ U = 1.2D + 1.6L (net upward/downward governs)           │
    ├──────────┼──────────────────────────────────────────────────────────┤
    │ TOE      │ Horizontal cantilever from front of stem.                │
    │          │ Upward: bearing pressure; Downward: slab + cover weight. │
    │          │ U = 1.2D (net upward governs)                            │
    └──────────┴──────────────────────────────────────────────────────────┘
    """

    def __init__(self, w: RetainingWallInputs, stab: StabilityAnalysis):
        self.w    = w
        self.stab = stab
        self._compute_stem()
        self._compute_heel()
        self._compute_toe()

    # ── STEM (vertical cantilever) ─────────────────────────────────────────
    def _compute_stem(self):
        w = self.w
        H = w.H_stem   # height of cantilever

        # Active pressure at base of stem (kN/m²)
        pa_base = w.Ka * w.gamma_s * H

        # Triangular load resultant (soil only)
        Pa_tri   = 0.5 * pa_base * H           # kN/m  (unfactored)
        M_tri    = Pa_tri * (H / 3.0)           # kN·m/m at base
        V_tri    = Pa_tri

        # Rectangular surcharge load
        Pa_rect  = w.Ka * w.surcharge * H       # kN/m  (unfactored)
        M_rect   = Pa_rect * (H / 2.0)          # kN·m/m at base
        V_rect   = Pa_rect

        # NSCP 2015: U = 1.6H (earth pressure is H-type load)
        #            surcharge treated as L: 1.6L
        self.Mu_stem = 1.6 * M_tri + 1.6 * M_rect   # kN·m/m
        self.Vu_stem = 1.6 * V_tri + 1.6 * V_rect   # kN/m

    # ── HEEL SLAB (horizontal cantilever — length = B_heel) ────────────────
    def _compute_heel(self):
        w    = self.w
        stab = self.stab
        L    = w.B_heel   # cantilever length

        # Dead downward loads (kN/m²)
        w_soil_D = w.gamma_s * w.H_stem   # weight of backfill on heel
        w_slab_D = w.gamma_c * w.t_base   # slab self-weight
        w_D      = w_soil_D + w_slab_D

        # Live downward load (kN/m²)
        w_L = w.surcharge

        # Average upward bearing pressure under heel strip
        # (Linear interpolation: q at heel end = q_min; at stem face = interpolated)
        B = w.B_base
        q_at_heel = stab.q_min
        # Distance from toe to heel strip centroid = B − B_heel/2
        x_heel_centroid = B - w.B_heel / 2.0
        q_at_stem_face_heel = (stab.q_max
                               - (stab.q_max - stab.q_min) * (B - w.B_heel) / B)
        q_up = (q_at_heel + q_at_stem_face_heel) / 2.0   # average (kN/m²)

        # Factored net load (positive = net upward)
        w_up_f   = 1.2 * q_up
        w_down_f = 1.2 * w_D + 1.6 * w_L
        w_net_f  = w_up_f - w_down_f     # kN/m² (may be + or −)

        # Cantilever moment and shear at face of stem (fixed end)
        self.Mu_heel          = abs(w_net_f) * L ** 2 / 2.0   # kN·m/m
        self.Vu_heel          = abs(w_net_f) * L               # kN/m
        self._heel_net_upward = (w_net_f >= 0)  # True → tension on TOP face

    # ── TOE SLAB (horizontal cantilever — length = B_toe) ─────────────────
    def _compute_toe(self):
        w    = self.w
        stab = self.stab
        L    = w.B_toe   # cantilever length

        # Dead downward loads (kN/m²)
        w_slab_D    = w.gamma_c * w.t_base
        w_soil_toe  = w.gamma_s * w.D_cover_toe
        w_D         = w_slab_D + w_soil_toe

        # Average upward bearing pressure under toe strip
        B = w.B_base
        q_at_toe_tip = stab.q_max
        q_at_stem_face_toe = (stab.q_max
                              - (stab.q_max - stab.q_min) * (w.B_toe / B))
        q_up = (q_at_toe_tip + q_at_stem_face_toe) / 2.0   # average (kN/m²)

        # Factored net load
        w_up_f   = 1.2 * q_up
        w_down_f = 1.2 * w_D
        w_net_f  = w_up_f - w_down_f   # typically positive (upward) for toe

        self.Mu_toe          = abs(w_net_f) * L ** 2 / 2.0   # kN·m/m
        self.Vu_toe          = abs(w_net_f) * L               # kN/m
        self._toe_net_upward = (w_net_f >= 0)

    def report(self):
        print(section_divider("MODULE 3 — FACTORED INTERNAL FORCES (NSCP 2015)"))

        print("\n  ── Stem (base — vertical cantilever) ──────────────────────")
        print(f"  Mu_stem              : {self.Mu_stem:>8.3f} kN·m/m  [U = 1.6H + 1.6L]")
        print(f"  Vu_stem              : {self.Vu_stem:>8.3f} kN/m")

        print("\n  ── Heel Slab (back face of stem) ──────────────────────────")
        print(f"  Mu_heel              : {self.Mu_heel:>8.3f} kN·m/m  [U = 1.2D + 1.6L]")
        print(f"  Vu_heel              : {self.Vu_heel:>8.3f} kN/m")
        face = "TOP (net uplift)" if self._heel_net_upward else "BOTTOM (soil wt. governs)"
        print(f"  Critical tension face: {face}")

        print("\n  ── Toe Slab (front face of stem) ──────────────────────────")
        print(f"  Mu_toe               : {self.Mu_toe:>8.3f} kN·m/m  [U = 1.2D]")
        print(f"  Vu_toe               : {self.Vu_toe:>8.3f} kN/m")
        face = "BOTTOM (bearing pressure governs)" if self._toe_net_upward else "TOP"
        print(f"  Critical tension face: {face}")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 4 — NSCP 2015 REINFORCEMENT DESIGN
# ─────────────────────────────────────────────────────────────────────────────

class ReinforcementDesign:
    """
    USD reinforcement design for the three critical sections per NSCP 2015.

    ┌─────────────────────────────────────────────────────────────────────┐
    │  FLEXURAL DESIGN                                                    │
    │    Rn  = Mu / (φ · b · d²)             φ_flex = 0.90              │
    │    ρ   = (0.85f'c/fy)[1 − √(1 − 2Rn/(0.85f'c))]                  │
    │    As  = max(ρ_req, ρ_min) · b · d                                 │
    │                                                                     │
    │  ρ_min (NSCP 2015 Sec. 406.6.1):                                   │
    │    ρ_min = max(0.25√f'c / fy,  1.4 / fy)                          │
    │                                                                     │
    │  ρ_max (tension-controlled, εt ≥ 0.004):                           │
    │    ρ_max = 0.85·β₁·(f'c/fy)·[0.003/(0.003+0.004)]                │
    │                                                                     │
    │  SHEAR DESIGN (NSCP 2015 Sec. 422.5):                              │
    │    φVc = 0.75 × 0.17 × λ × √f'c × b × d                          │
    │          φ = 0.75,  λ = 1.0 (normal weight),  b = 1000 mm         │
    │                                                                     │
    │  SHRINKAGE & TEMPERATURE (NSCP 2015 Sec. 407.7.1):                 │
    │    ρ_st = 0.0020  for  fy ≤ 275 MPa                               │
    │    ρ_st = 0.0018  for  fy = 415 MPa                               │
    │    ρ_st = 0.0018 × 420/fy  for  fy > 420 MPa  (min 0.0014)       │
    └─────────────────────────────────────────────────────────────────────┘
    """

    def __init__(self, w: RetainingWallInputs, forces: InternalForces):
        self.w      = w
        self.forces = forces
        self.results = {}

        # ── Shared design constants ────────────────────────────────────────
        self._phi_flex  = 0.90
        self._phi_shear = 0.75
        self._lam       = 1.0       # normal-weight concrete
        self._b_mm      = 1000.0    # 1-m strip width in mm

        self._beta1   = self._get_beta1()
        self._rho_min = max(0.25 * math.sqrt(w.fc) / w.fy, 1.4 / w.fy)
        # ρ_max at εt = 0.004 (minimum ductility)
        self._rho_max = (0.85 * self._beta1 * w.fc / w.fy
                         * 0.003 / (0.003 + 0.004))
        self._rho_st  = self._shrinkage_ratio()

        # ── Design each section ───────────────────────────────────────────
        self.results["stem"] = self._design_section(
            label       = "Stem",
            Mu_kNm      = forces.Mu_stem,
            Vu_kN       = forces.Vu_stem,
            d_mm        = w.d_stem_mm,
            section_h_mm= w.t_stem_bot * 1000.0,
        )
        self.results["heel"] = self._design_section(
            label       = "Heel",
            Mu_kNm      = forces.Mu_heel,
            Vu_kN       = forces.Vu_heel,
            d_mm        = w.d_heel_mm,
            section_h_mm= w.t_base * 1000.0,
        )
        self.results["toe"]  = self._design_section(
            label       = "Toe",
            Mu_kNm      = forces.Mu_toe,
            Vu_kN       = forces.Vu_toe,
            d_mm        = w.d_toe_mm,
            section_h_mm= w.t_base * 1000.0,
        )

    # ── β₁ per NSCP 2015 Sec. 422.2.2.4.3 ───────────────────────────────
    def _get_beta1(self) -> float:
        fc = self.w.fc
        if fc <= 28.0:
            return 0.85
        beta1 = 0.85 - 0.05 * (fc - 28.0) / 7.0
        return max(beta1, 0.65)

    # ── Shrinkage/temperature ratio ───────────────────────────────────────
    def _shrinkage_ratio(self) -> float:
        fy = self.w.fy
        if fy <= 275.0:
            return 0.0020
        elif fy <= 420.0:
            return 0.0018
        else:
            return max(0.0018 * 420.0 / fy, 0.0014)

    # ── Core design function ──────────────────────────────────────────────
    def _design_section(self, label: str, Mu_kNm: float, Vu_kN: float,
                         d_mm: float, section_h_mm: float) -> dict:
        """Flexural + shear + shrinkage design for a single rectangular section."""
        w  = self.w
        b  = self._b_mm
        d  = d_mm

        # Convert moment to N·mm
        Mu_Nmm = Mu_kNm * 1.0e6

        # ── Flexure ───────────────────────────────────────────────────────
        Rn = Mu_Nmm / (self._phi_flex * b * d ** 2)

        discriminant = 1.0 - (2.0 * Rn) / (0.85 * w.fc)
        over_stressed = False
        if discriminant < 0:
            # Section is over-stressed — use ρ_max as placeholder and flag
            rho_req    = self._rho_max
            over_stressed = True
        else:
            rho_req = (0.85 * w.fc / w.fy) * (1.0 - math.sqrt(discriminant))

        # Governing design reinforcement ratio
        rho_design = max(rho_req, self._rho_min)

        # Flag if ρ exceeds ρ_max (section not tension-controlled)
        over_rho = rho_design > self._rho_max
        rho_design = min(rho_design, self._rho_max)   # cap — designer must resize

        As_req_mm2 = rho_design * b * d   # mm²/m

        # Bar spacing (c/c) for selected main bar diameter
        s_main   = spacing_mm(As_req_mm2, w.main_bar_dia)
        # Actual As provided based on chosen spacing
        As_prov  = bar_area_mm2(w.main_bar_dia) / s_main * 1000.0   # mm²/m

        # ── Shear ─────────────────────────────────────────────────────────
        # φVc [N] = 0.75 × 0.17 × 1.0 × √f'c × b × d
        phi_Vc_N = self._phi_shear * 0.17 * self._lam * math.sqrt(w.fc) * b * d
        Vu_N     = Vu_kN * 1000.0
        shear_ok = phi_Vc_N >= Vu_N

        # ── Shrinkage & Temperature ───────────────────────────────────────
        # Applied to the GROSS section (full thickness) per NSCP 2015
        As_temp  = self._rho_st * b * section_h_mm   # mm²/m
        s_temp   = spacing_mm(As_temp, w.temp_bar_dia)

        return {
            "label"         : label,
            "Mu_kNm"        : Mu_kNm,
            "Vu_kN"         : Vu_kN,
            "d_mm"          : d_mm,
            "Rn_MPa"        : Rn,
            "rho_req"       : rho_req,
            "rho_min"       : self._rho_min,
            "rho_max"       : self._rho_max,
            "rho_design"    : rho_design,
            "As_req_mm2"    : As_req_mm2,
            "As_prov_mm2"   : As_prov,
            "s_main_mm"     : s_main,
            "phi_Vc_kN"     : phi_Vc_N / 1000.0,
            "shear_ok"      : shear_ok,
            "As_temp_mm2"   : As_temp,
            "s_temp_mm"     : s_temp,
            "over_rho"      : over_rho,
            "over_stressed" : over_stressed,
        }

    def report(self):
        w = self.w
        print(section_divider("MODULE 4 — NSCP 2015 REINFORCEMENT DESIGN"))
        print(f"\n  β₁ = {self._beta1:.3f}   "
              f"ρ_min = {self._rho_min:.5f}   "
              f"ρ_max (εt≥0.004) = {self._rho_max:.5f}   "
              f"ρ_st = {self._rho_st:.4f}")

        for key in ("stem", "heel", "toe"):
            r = self.results[key]
            print(f"\n  {'─'*60}")
            print(f"  SECTION : {r['label'].upper()}")
            print(f"  {'─'*60}")
            print(f"  Mu                   : {r['Mu_kNm']:>8.3f} kN·m/m")
            print(f"  Vu                   : {r['Vu_kN']:>8.3f} kN/m")
            print(f"  Effective depth d    : {r['d_mm']:>8.1f} mm")

            print(f"\n  [Flexural Design — φ = {self._phi_flex}]")
            print(f"  Rn                   : {r['Rn_MPa']:>8.4f} MPa")
            print(f"  ρ_required           : {r['rho_req']:>8.5f}")
            print(f"  ρ_min                : {r['rho_min']:>8.5f}")
            print(f"  ρ_max                : {r['rho_max']:>8.5f}")
            print(f"  ρ_design (governing) : {r['rho_design']:>8.5f}")
            print(f"  As required          : {r['As_req_mm2']:>8.1f} mm²/m")
            print(f"  As provided          : {r['As_prov_mm2']:>8.1f} mm²/m")
            print(f"  Main bar spacing     : Ø{w.main_bar_dia:.0f}mm @ "
                  f"{r['s_main_mm']:.0f}mm c/c")

            if r["over_stressed"]:
                print(f"  *** CRITICAL: Section over-stressed (Rn > 0.85f'c/2) "
                      "— Increase depth! ***")
            if r["over_rho"]:
                print(f"  *** WARNING : ρ_req > ρ_max — Section not tension-controlled. "
                      "Increase depth! ***")

            print(f"\n  [Shear Design — φVc = 0.75×0.17×λ×√f'c×b×d]")
            flag_v = "✓  PASS" if r["shear_ok"] else "✗  FAIL — INCREASE THICKNESS"
            print(f"  φVc                  : {r['phi_Vc_kN']:>8.3f} kN/m")
            print(f"  Vu                   : {r['Vu_kN']:>8.3f} kN/m")
            print(f"  φVc ≥ Vu ?           :          [{flag_v}]")

            print(f"\n  [Shrinkage & Temperature — ρ_st = {self._rho_st:.4f}]")
            print(f"  As_temp required     : {r['As_temp_mm2']:>8.1f} mm²/m")
            print(f"  Temp bar spacing     : Ø{w.temp_bar_dia:.0f}mm @ "
                  f"{r['s_temp_mm']:.0f}mm c/c")


# ─────────────────────────────────────────────────────────────────────────────
# MODULE 5 — DETAILING SUMMARY
# ─────────────────────────────────────────────────────────────────────────────

class DetailingSummary:
    """
    Prints a single consolidated design report — the engineer's takeaway sheet.
    """

    def __init__(self, w: RetainingWallInputs,
                 stab: StabilityAnalysis,
                 forces: InternalForces,
                 design: ReinforcementDesign):
        self.w      = w
        self.stab   = stab
        self.forces = forces
        self.design = design

    def report(self):
        w  = self.w
        st = self.stab
        d  = self.design
        hr = "═" * 72

        print(f"\n{hr}")
        print(f"{'CANTILEVER RETAINING WALL — NSCP 2015 DESIGN SUMMARY':^72}")
        print(f"{hr}")

        # ── Stability ────────────────────────────────────────────────────
        ok = lambda flag: "PASS ✓" if flag else "FAIL ✗"
        print("\n  ┌─ STABILITY CHECKS ─────────────────────────────────────────┐")
        print(f"  │  FS Overturning : {st.FS_OT:>7.3f}   (req ≥ 2.0)   {ok(st.ok_OT):<13} │")
        print(f"  │  FS Sliding     : {st.FS_slide:>7.3f}   (req ≥ 1.5)   {ok(st.ok_slide):<13} │")
        print(f"  │  Eccentricity e : {st.e:>7.3f} m  (allow ±{st.e_allow:.3f} m) {ok(st.ok_e):<13} │")
        print(f"  └────────────────────────────────────────────────────────────┘")

        # ── Bearing ──────────────────────────────────────────────────────
        print("\n  ┌─ BEARING PRESSURES ─────────────────────────────────────────┐")
        print(f"  │  q_max          : {st.q_max:>8.2f} kN/m²                        │")
        print(f"  │  q_min          : {st.q_min:>8.2f} kN/m²                        │")
        print(f"  │  q_allow        : {w.q_allow:>8.2f} kN/m²   {ok(st.ok_qmax):<26} │")
        print(f"  └────────────────────────────────────────────────────────────┘")

        # ── Internal Forces ──────────────────────────────────────────────
        f = self.forces
        print("\n  ┌─ FACTORED DESIGN FORCES ────────────────────────────────────┐")
        print(f"  │  {'Section':<8}  {'Mu (kN·m/m)':>14}  {'Vu (kN/m)':>12}              │")
        print(f"  │  {'─'*60} │")
        for lbl, Mu, Vu in (("Stem",  f.Mu_stem, f.Vu_stem),
                             ("Heel",  f.Mu_heel, f.Vu_heel),
                             ("Toe",   f.Mu_toe,  f.Vu_toe)):
            print(f"  │  {lbl:<8}  {Mu:>14.3f}  {Vu:>12.3f}              │")
        print(f"  └────────────────────────────────────────────────────────────┘")

        # ── Reinforcement Schedule ────────────────────────────────────────
        print("\n  ┌─ REINFORCEMENT DETAILING SCHEDULE ──────────────────────────┐")
        print(f"  │  {'Section':<10} {'As_req':>9} {'As_prov':>9} "
              f"{'Main Bars':>15} {'Temp Bars':>14}  │")
        print(f"  │  {'':─<62} │")

        for key, lbl in (("stem","Stem (V)"), ("heel","Heel (H)"), ("toe","Toe  (H)")):
            r = d.results[key]
            sflag = "" if r["shear_ok"] else " ← !"
            print(f"  │  {lbl:<10} "
                  f"{r['As_req_mm2']:>9.1f} "
                  f"{r['As_prov_mm2']:>9.1f} "
                  f"  Ø{w.main_bar_dia:.0f}@{r['s_main_mm']:>4.0f}mm c/c"
                  f"  Ø{w.temp_bar_dia:.0f}@{r['s_temp_mm']:>4.0f}mm c/c"
                  f"{sflag:<4}  │")

        print(f"  │  As in mm²/m  |  V = vertical, H = horizontal bars     │")
        print(f"  │  Clear cover to main steel: {w.cover_mm:.0f} mm                    │")
        print(f"  └────────────────────────────────────────────────────────────┘")

        # ── Global Warnings ───────────────────────────────────────────────
        warnings = []
        if not st.ok_OT:
            warnings.append("FS_OT < 2.0 — increase B_heel or add a shear key.")
        if not st.ok_slide:
            warnings.append("FS_slide < 1.5 — add a shear key or widen base.")
        if not st.ok_e:
            warnings.append("Eccentricity > B/6 — tension under footing; "
                            "widen heel or increase B_base.")
        if not st.ok_qmax:
            warnings.append(f"q_max ({st.q_max:.1f} kN/m²) > q_allow "
                            f"({w.q_allow:.1f} kN/m²) — widen base.")
        for key in ("stem", "heel", "toe"):
            r = d.results[key]
            if not r["shear_ok"]:
                warnings.append(
                    f"{r['label']}: φVc ({r['phi_Vc_kN']:.1f} kN) < "
                    f"Vu ({r['Vu_kN']:.1f} kN) — increase section thickness.")
            if r["over_rho"] or r["over_stressed"]:
                warnings.append(
                    f"{r['label']}: ρ > ρ_max or section over-stressed — "
                    "increase effective depth.")

        print()
        if warnings:
            print("  ⚠️  DESIGN WARNINGS — ACTION REQUIRED:")
            for i, msg in enumerate(warnings, 1):
                print(f"     {i:>2}. {msg}")
        else:
            print("  ✅  All stability, bearing, shear, and flexure checks PASS.")
            print("      Wall is adequate per NSCP 2015 USD provisions.")

        print(f"\n{hr}\n")


# ─────────────────────────────────────────────────────────────────────────────
# MAIN — EXAMPLE PROBLEM
# ─────────────────────────────────────────────────────────────────────────────
#
#  Worked example — 3.5 m retained height, granular backfill, φ=30°
#
#  Wall geometry (m):
#    H_stem=3.50  |  t_top=0.25, t_bot=0.40  |  B_toe=0.90, B_heel=2.10
#    t_base=0.50  |  D_cover_toe=0.30
#
#  Soil: γs=17 kN/m³, φ=30°, c=0, qa=150 kN/m², surcharge=10 kN/m²
#  Materials: f'c=28 MPa, fy=415 MPa, γc=23.54 kN/m³
#  Bars: Ø16 main, Ø12 temp/shrinkage, cover=75 mm

if __name__ == "__main__":

    # ── 1. Define wall ────────────────────────────────────────────────────
    wall = RetainingWallInputs(
        H_stem          = 3.50,
        t_stem_top      = 0.25,
        t_stem_bot      = 0.40,
        B_toe           = 0.90,
        B_heel          = 2.10,
        t_base          = 0.50,
        D_cover_toe     = 0.30,
        gamma_s         = 17.0,
        phi_deg         = 30.0,
        cohesion        = 0.0,
        q_allow         = 150.0,
        surcharge       = 10.0,
        fc_MPa          = 28.0,
        fy_MPa          = 415.0,
        gamma_c         = 23.54,
        cover_mm        = 75.0,
        main_bar_dia_mm = 16.0,
        temp_bar_dia_mm = 12.0,
    )

    # ── 2. Run all five modules ───────────────────────────────────────────
    wall.echo()

    stability = StabilityAnalysis(wall)
    stability.report()

    int_forces = InternalForces(wall, stability)
    int_forces.report()

    rebar = ReinforcementDesign(wall, int_forces)
    rebar.report()

    summary = DetailingSummary(wall, stability, int_forces, rebar)
    summary.report()