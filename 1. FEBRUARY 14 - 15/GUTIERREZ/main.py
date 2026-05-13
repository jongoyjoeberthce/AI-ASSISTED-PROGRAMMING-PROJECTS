"""
==============================================================================
  STAAD.Pro Two-Storey House Builder — NSCP 2015
  Uses openstaadpy (same as WarehouseFrameBuilder reference code)

  Install:  pip install openstaadpy
  Run:      python staad_two_storey_final.py
  Requires: STAAD.Pro open with an EMPTY .std model
==============================================================================
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, filedialog
import threading
import traceback
import math
import json
import os
from datetime import datetime
from array import array as pyarray

# ── openstaadpy import (same pattern as reference WarehouseFrameBuilder) ─────
try:
    from openstaadpy import os_analytical
    STAAD_AVAILABLE = True
except ImportError:
    STAAD_AVAILABLE = False


# ══════════════════════════════════════════════════════════════════════════════
#  NSCP 2015 §208 SEISMIC CALCULATOR
# ══════════════════════════════════════════════════════════════════════════════
class NSCPSeismic:
    ZONE_Z = {"Zone 2": 0.20, "Zone 4": 0.40}
    SOIL   = ["SA", "SB", "SC", "SD", "SE"]
    CA = {
        "Zone 2": {"SA":0.16,"SB":0.20,"SC":0.24,"SD":0.28,"SE":0.34},
        "Zone 4": {"SA":0.32,"SB":0.40,"SC":0.40,"SD":0.44,"SE":0.36},
    }
    CV = {
        "Zone 2": {"SA":0.16,"SB":0.20,"SC":0.32,"SD":0.40,"SE":0.64},
        "Zone 4": {"SA":0.32,"SB":0.40,"SC":0.56,"SD":0.64,"SE":0.96},
    }
    IMP = {
        "I — Standard (I=1.0)":    1.0,
        "II — Essential (I=1.25)": 1.25,
        "III — Hazardous (I=1.50)":1.50,
    }
    R = {
        "SMRF Concrete (R=8.5)":   8.5,
        "SMRF Steel (R=8.5)":      8.5,
        "IMF Concrete (R=5.5)":    5.5,
        "OMF Concrete (R=3.5)":    3.5,
        "IMF Steel (R=6.0)":       6.0,
        "OMF Steel (R=4.5)":       4.5,
        "Shear Wall (R=4.5)":      4.5,
        "Braced Frame (R=5.6)":    5.6,
    }
    CT = {
        "Steel MRF":    0.0853,
        "Concrete MRF": 0.0731,
        "Other":        0.0488,
    }

    @classmethod
    def compute(cls, zone, soil, imp_k, R_k, Ct_k, hn, W):
        Ca = cls.CA[zone][soil];  Cv = cls.CV[zone][soil]
        I  = cls.IMP[imp_k];      R  = cls.R[R_k];   Ct = cls.CT[Ct_k]
        T  = Ct * (hn ** 0.75)
        Vd = (Cv * I) / (R * T) * W
        Vn = 0.11 * Ca * I * W
        Vx = 2.5 * Ca * I / R * W
        V  = max(Vn, min(Vd, Vx))
        Ft = 0.07 * T * V if T > 0.7 else 0.0
        return dict(Ca=Ca, Cv=Cv, I=I, R=R, Ct=Ct,
                    T=T, V=V, Vd=Vd, Vn=Vn, Vx=Vx, Ft=Ft)


# ══════════════════════════════════════════════════════════════════════════════
#  HELPER
# ══════════════════════════════════════════════════════════════════════════════
def to_int_array(lst):
    """Convert list/int to COM-compatible integer array (same as reference code)."""
    # Accept single int, list, or already an array
    if isinstance(lst, int):
        lst = [lst]
    if isinstance(lst, (list, tuple)):
        return pyarray('l', [int(x) for x in lst])
    return lst


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN APPLICATION
# ══════════════════════════════════════════════════════════════════════════════
class TwoStoreyHouseBuilder:

    def __init__(self, root):
        self.root = root
        self.root.title("STAAD.Pro Two-Storey House Builder — NSCP 2015")
        self.root.geometry("1060x860")
        self.root.resizable(True, True)

        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.staad      = None
        self.is_running = False

        self._build_ui()

        if not STAAD_AVAILABLE:
            self.log("WARNING: openstaadpy not found!", "warning")
            self.log("Install it:  pip install openstaadpy", "warning")
        else:
            self.log("openstaadpy found ✓  — open STAAD.Pro with an empty model, then click Build.", "success")

    # ──────────────────────────────────────────────────────────────────────────
    #  UI CONSTRUCTION
    # ──────────────────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Menu
        mb = tk.Menu(self.root)
        self.root.config(menu=mb)
        fm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="File", menu=fm)
        fm.add_command(label="Save Configuration", command=self.save_config)
        fm.add_command(label="Load Configuration", command=self.load_config)
        fm.add_separator()
        fm.add_command(label="Export Log",          command=self.export_log)
        fm.add_separator()
        fm.add_command(label="Exit",                command=self.root.quit)
        hm = tk.Menu(mb, tearoff=0)
        mb.add_cascade(label="Help", menu=hm)
        hm.add_command(label="About",           command=self.show_about)
        hm.add_command(label="Parameter Guide", command=self.show_guide)

        # Root grid
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        mf = ttk.Frame(self.root, padding="10")
        mf.grid(row=0, column=0, sticky="nsew")
        mf.columnconfigure(0, weight=1)
        mf.columnconfigure(1, weight=1)
        mf.rowconfigure(5, weight=1)

        # Title
        ttk.Label(mf, text="Two-Storey House Builder — NSCP 2015",
                  font=('Arial', 15, 'bold')).grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 8))

        # ── Notebook for parameter tabs ────────────────────────────────────
        nb = ttk.Notebook(mf)
        nb.grid(row=1, column=0, columnspan=2, sticky="nsew", pady=(0, 8))
        mf.rowconfigure(1, weight=0)

        tab_geo  = ttk.Frame(nb, padding=8)
        tab_mat  = ttk.Frame(nb, padding=8)
        tab_ld   = ttk.Frame(nb, padding=8)
        tab_eq   = ttk.Frame(nb, padding=8)
        nb.add(tab_geo,  text="  🏗  Geometry  ")
        nb.add(tab_mat,  text="  🧱  Material & Sections  ")
        nb.add(tab_ld,   text="  ⬇  Gravity Loads  ")
        nb.add(tab_eq,   text="  🌏  Seismic §208  ")

        self._tab_geometry(tab_geo)
        self._tab_material(tab_mat)
        self._tab_loads(tab_ld)
        self._tab_seismic(tab_eq)

        # ── Buttons ────────────────────────────────────────────────────────
        bf = ttk.Frame(mf)
        bf.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        self.btn_preview = ttk.Button(bf, text="Preview Model Info",
                                      command=self.preview_model, width=20)
        self.btn_preview.grid(row=0, column=0, padx=4)

        self.btn_seismic = ttk.Button(bf, text="Compute Seismic",
                                      command=self.seismic_preview, width=18)
        self.btn_seismic.grid(row=0, column=1, padx=4)

        self.btn_build = ttk.Button(bf, text="▶  Build Model",
                                    command=self.build_model, width=18)
        self.btn_build.grid(row=0, column=2, padx=4)

        self.btn_analyze = ttk.Button(bf, text="Build & Analyze",
                                      command=self.build_and_analyze, width=18)
        self.btn_analyze.grid(row=0, column=3, padx=4)

        self.btn_clear = ttk.Button(bf, text="Clear Log",
                                    command=self.clear_log, width=12)
        self.btn_clear.grid(row=0, column=4, padx=4)

        # ── Progress bar ───────────────────────────────────────────────────
        self.progress = ttk.Progressbar(mf, mode='indeterminate')
        self.progress.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(0, 6))

        # ── Log ────────────────────────────────────────────────────────────
        lf = ttk.LabelFrame(mf, text="Build Log", padding=8)
        lf.grid(row=4, column=0, columnspan=2, sticky="nsew")
        lf.columnconfigure(0, weight=1); lf.rowconfigure(0, weight=1)
        mf.rowconfigure(4, weight=1)

        self.log_text = scrolledtext.ScrolledText(lf, wrap=tk.WORD,
                                                  height=14, width=100)
        self.log_text.grid(row=0, column=0, sticky="nsew")
        self.log_text.tag_config('info',    foreground='black')
        self.log_text.tag_config('success', foreground='green')
        self.log_text.tag_config('warning', foreground='darkorange')
        self.log_text.tag_config('error',   foreground='red')
        self.log_text.tag_config('eq',      foreground='blue')

        # ── Status bar ─────────────────────────────────────────────────────
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(mf, textvariable=self.status_var,
                  relief=tk.SUNKEN, anchor=tk.W).grid(
            row=5, column=0, columnspan=2, sticky="ew", pady=(6, 0))

    # ──────────────────────────────────────────────────────────────────────────
    #  TAB: GEOMETRY
    # ──────────────────────────────────────────────────────────────────────────
    def _tab_geometry(self, p):
        p.columnconfigure(1, weight=1); p.columnconfigure(3, weight=1)

        # Left column
        lf = ttk.LabelFrame(p, text=" House Geometry ", padding=10)
        lf.grid(row=0, column=0, sticky="nsew", padx=(0, 6))

        geo_fields = [
            ("Bays in X direction:",  "bays_x",    "3",   "Column lines along length"),
            ("Bays in Z direction:",  "bays_z",    "2",   "Column lines along width"),
            ("Bay Width X (m):",      "bay_w",     "5.0", "Span in X direction"),
            ("Bay Depth Z (m):",      "bay_d",     "5.0", "Span in Z direction"),
            ("Storey 1 Height (m):",  "h1",        "3.0", "Ground floor height"),
            ("Storey 2 Height (m):",  "h2",        "3.0", "Upper floor height"),
        ]
        self.vars = {}
        for r, (lbl, key, val, tip) in enumerate(geo_fields):
            ttk.Label(lf, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            v = tk.StringVar(value=val); self.vars[key] = v
            ttk.Entry(lf, textvariable=v, width=12).grid(row=r, column=1, sticky="w", padx=(8,0), pady=4)
            ttk.Label(lf, text=tip, foreground="gray").grid(row=r, column=2, sticky="w", padx=(6,0), pady=4)

        # Right column — options
        rf = ttk.LabelFrame(p, text=" Options ", padding=10)
        rf.grid(row=0, column=1, sticky="nsew", padx=(6, 0))

        ttk.Label(rf, text="Unit System:").grid(row=0, column=0, sticky="w", pady=4)
        self.vars["unit"] = tk.StringVar(value="METER-KN")
        ttk.Combobox(rf, textvariable=self.vars["unit"],
                     values=["METER-KN", "FEET-KIP", "INCHES-KIP"],
                     state="readonly", width=14).grid(row=0, column=1, sticky="w", padx=(8,0), pady=4)

        ttk.Label(rf, text="Output File (.std):").grid(row=1, column=0, sticky="w", pady=4)
        self.vars["file"] = tk.StringVar(
            value=os.path.join(os.path.expanduser("~"), "Desktop", "TwoStoreyHouse.std"))
        ttk.Entry(rf, textvariable=self.vars["file"], width=28).grid(
            row=1, column=1, sticky="ew", padx=(8,0), pady=4)
        ttk.Button(rf, text="…", width=3,
                   command=self._browse_file).grid(row=1, column=2, padx=(4,0), pady=4)

        self.sw_var = tk.BooleanVar(value=True)
        self.combo_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(rf, text="Include Self-Weight",
                        variable=self.sw_var).grid(row=2, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Checkbutton(rf, text="Include NSCP 2015 Load Combinations",
                        variable=self.combo_var).grid(row=3, column=0, columnspan=3, sticky="w", pady=4)

        # Unit system
        ttk.Label(rf, text="Unit System:").grid(row=4, column=0, sticky="w", pady=(10,2))
        self.vars["unit"] = tk.StringVar(value="METER-KN")
        ttk.Combobox(rf, textvariable=self.vars["unit"],
                     values=["METER-KN", "FEET-KIP", "INCHES-KIP"],
                     state="readonly", width=18).grid(row=4, column=1, columnspan=2, sticky="w", padx=(8,0), pady=(10,2))

        # Support type at Y=0 base nodes
        ttk.Label(rf, text="Base Support Type (Y=0):").grid(row=5, column=0, sticky="w", pady=(6,2))
        self.vars["support_type"] = tk.StringVar(value="FIXED")
        ttk.Combobox(rf, textvariable=self.vars["support_type"],
                     values=[
                         "FIXED",
                         "PINNED",
                         "FIXED BUT FX FZ MX MY MZ",
                         "FIXED BUT MX MY MZ",
                         "FIXED BUT FX FZ MY",
                     ],
                     state="readonly", width=28).grid(row=5, column=1, columnspan=2, sticky="w", padx=(8,0), pady=(6,2))
        ttk.Label(rf, text="FIXED=all DOF | PINNED=no moment | FIXED BUT=partial",
                  foreground="gray").grid(row=6, column=0, columnspan=3, sticky="w", padx=(0,0), pady=(0,4))

    # ──────────────────────────────────────────────────────────────────────────
    #  TAB: MATERIAL & SECTIONS
    # ──────────────────────────────────────────────────────────────────────────
    def _tab_material(self, p):
        # Material type toggle
        mf = ttk.LabelFrame(p, text=" Material Type ", padding=10)
        mf.pack(fill="x", pady=(0, 6))
        self.mat_var = tk.StringVar(value="Concrete (RC)")
        for t in ["Concrete (RC)", "Structural Steel"]:
            ttk.Radiobutton(mf, text=t, variable=self.mat_var,
                            value=t, command=self._on_mat_change).pack(side="left", padx=16, pady=4)

        # ── Concrete panel ─────────────────────────────────────────────────
        self.rc_frame = ttk.LabelFrame(p, text=" RC Concrete Parameters ", padding=10)
        self.rc_frame.pack(fill="x", pady=(0, 6))

        # Two sub-columns
        sf = ttk.LabelFrame(self.rc_frame, text=" Material Strengths ", padding=8)
        sf.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=4)
        self.rc_frame.columnconfigure(0, weight=1); self.rc_frame.columnconfigure(1, weight=1)

        fc_opts = ["21", "24", "28", "32", "35", "42", "Custom"]
        ttk.Label(sf, text="f'c (MPa):").grid(row=0, column=0, sticky="w", pady=4)
        self.vars["fc_sel"] = tk.StringVar(value="28")
        fc_cb = ttk.Combobox(sf, textvariable=self.vars["fc_sel"],
                              values=fc_opts, state="readonly", width=14)
        fc_cb.grid(row=0, column=1, sticky="w", padx=(8,0), pady=4)
        fc_cb.bind("<<ComboboxSelected>>", lambda e: self._on_fc_change())

        self.fc_custom_frame = ttk.Frame(sf)
        self.fc_custom_frame.grid(row=1, column=0, columnspan=3, sticky="w")
        ttk.Label(self.fc_custom_frame, text="Custom f'c:").pack(side="left")
        self.fc_custom_var = tk.StringVar(value="28")
        ttk.Entry(self.fc_custom_frame, textvariable=self.fc_custom_var, width=8).pack(side="left", padx=(6,0))
        self.fc_custom_frame.grid_remove()

        ttk.Label(sf, text="fy main bars (MPa):").grid(row=2, column=0, sticky="w", pady=4)
        self.vars["fy_sel"] = tk.StringVar(value="415 — Grade 60")
        ttk.Combobox(sf, textvariable=self.vars["fy_sel"],
                     values=["275 — Grade 40", "415 — Grade 60", "500 — Grade 72"],
                     state="readonly", width=16).grid(row=2, column=1, sticky="w", padx=(8,0), pady=4)

        ttk.Label(sf, text="fyt stirrups (MPa):").grid(row=3, column=0, sticky="w", pady=4)
        self.vars["fyt_sel"] = tk.StringVar(value="275 — Grade 40")
        ttk.Combobox(sf, textvariable=self.vars["fyt_sel"],
                     values=["275 — Grade 40", "415 — Grade 60"],
                     state="readonly", width=16).grid(row=3, column=1, sticky="w", padx=(8,0), pady=4)

        df = ttk.LabelFrame(self.rc_frame, text=" Member Dimensions (mm) ", padding=8)
        df.grid(row=0, column=1, sticky="nsew", pady=4)

        dim_fields = [
            ("Column Width b:",   "col_b",  "400"),
            ("Column Depth h:",   "col_h",  "400"),
            ("Beam Width b:",     "beam_b", "300"),
            ("Beam Depth h:",     "beam_h", "600"),
            ("Sec Beam Width:",   "sb_b",   "250"),
            ("Sec Beam Depth:",   "sb_h",   "500"),
        ]
        for r, (lbl, key, val) in enumerate(dim_fields):
            ttk.Label(df, text=lbl).grid(row=r, column=0, sticky="w", pady=3)
            self.vars[key] = tk.StringVar(value=val)
            ttk.Entry(df, textvariable=self.vars[key], width=10).grid(
                row=r, column=1, sticky="w", padx=(8,0), pady=3)

        # ── Steel panel ────────────────────────────────────────────────────
        self.steel_frame = ttk.LabelFrame(p, text=" Steel Section Parameters ", padding=10)
        self.steel_frame.pack(fill="x", pady=(0, 6))

        ttk.Label(self.steel_frame, text="Steel Fy (MPa):").grid(row=0, column=0, sticky="w", pady=4)
        self.vars["steel_fy"] = tk.StringVar(value="345 — A572 Gr50")
        ttk.Combobox(self.steel_frame, textvariable=self.vars["steel_fy"],
                     values=["250 — A36", "345 — A572 Gr50", "415 — Gr60"],
                     state="readonly", width=18).grid(row=0, column=1, sticky="w", padx=(8,0), pady=4)

        steel_sec = [
            ("Column Section:",       "col_sec",  ["W12X72","W14X82","W14X109","W14X132","W14X176",
                                                    "UC203X203X60","UC254X254X89","HW250X250","HW300X300"], "W14X82"),
            ("Primary Beam:",         "beam_sec", ["W18X35","W21X44","W21X62","W24X55","W24X76",
                                                    "UB305X165X40","UB406X178X60","HN400X200"], "W21X44"),
            ("Secondary Beam:",       "sb_sec",   ["W12X26","W14X30","W16X31","W18X35",
                                                    "UB203X133X25","UB254X146X31","HN300X150"], "W16X31"),
        ]
        for r, (lbl, key, vals, dflt) in enumerate(steel_sec, start=1):
            ttk.Label(self.steel_frame, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            self.vars[key] = tk.StringVar(value=dflt)
            ttk.Combobox(self.steel_frame, textvariable=self.vars[key],
                         values=vals, width=20).grid(
                row=r, column=1, sticky="w", padx=(8,0), pady=4)

        self._on_mat_change()

    # ──────────────────────────────────────────────────────────────────────────
    #  TAB: GRAVITY LOADS
    # ──────────────────────────────────────────────────────────────────────────
    def _tab_loads(self, p):
        lf = ttk.LabelFrame(p, text=" Gravity Loads (kN/m²) ", padding=12)
        lf.pack(fill="x", pady=(0, 6))

        load_fields = [
            ("Dead Load (kN/m²):", "dl", "4.0", "Superimposed — tiles, ceiling, partitions"),
            ("Live Load (kN/m²):", "ll", "2.4", "NSCP Table 205 — residential = 2.4"),
            ("Wind Load (kN/m²):", "wl", "1.2", "Design wind pressure on facade"),
        ]
        for r, (lbl, key, val, tip) in enumerate(load_fields):
            ttk.Label(lf, text=lbl).grid(row=r, column=0, sticky="w", pady=5)
            self.vars[key] = tk.StringVar(value=val)
            ttk.Entry(lf, textvariable=self.vars[key], width=12).grid(
                row=r, column=1, sticky="w", padx=(8,0), pady=5)
            ttk.Label(lf, text=tip, foreground="gray").grid(
                row=r, column=2, sticky="w", padx=(8,0), pady=5)

        # Combo reference display
        cf = ttk.LabelFrame(p, text=" NSCP 2015 §203 Load Combinations (auto-generated) ", padding=8)
        cf.pack(fill="x")
        combos = [
            "1.4D",               "1.2D + 1.6L",
            "1.2D + 1.0L + 1.6Wx","1.2D + 1.0L + 1.6Wz",
            "0.9D + 1.0Wx",       "0.9D + 1.0Wz",
            "1.2D + 1.0L + 1.0Ex (if seismic)", "1.2D + 1.0L + 1.0Ez (if seismic)",
            "0.9D + 1.0Ex (if seismic)",         "0.9D + 1.0Ez (if seismic)",
        ]
        for i, c in enumerate(combos):
            clr = "blue" if "seismic" in c else "gray"
            ttk.Label(cf, text=f"  ⬡  {c}", foreground=clr).grid(
                row=i//2, column=i%2, sticky="w", padx=8, pady=2)

    # ──────────────────────────────────────────────────────────────────────────
    #  TAB: SEISMIC
    # ──────────────────────────────────────────────────────────────────────────
    def _tab_seismic(self, p):
        top = ttk.Frame(p); top.pack(fill="x", pady=(0, 6))
        self.eq_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="Enable Seismic Design  (NSCP 2015 §208)",
                        variable=self.eq_var,
                        command=self._on_eq_toggle).pack(side="left", pady=4)

        self.eq_body = ttk.Frame(p)
        self.eq_body.pack(fill="x")

        lc = ttk.Frame(self.eq_body); rc = ttk.Frame(self.eq_body)
        lc.pack(side="left", fill="both", expand=True, padx=(0, 8))
        rc.pack(side="right", fill="both", expand=True, padx=(8, 0))

        # Site
        sf = ttk.LabelFrame(lc, text=" Site Parameters ", padding=10)
        sf.pack(fill="x", pady=(0, 6))

        site_fields = [
            ("Seismic Zone:",    "eq_zone", list(NSCPSeismic.ZONE_Z.keys()), "Zone 4"),
            ("Soil Profile:",    "eq_soil", NSCPSeismic.SOIL,                 "SD"),
            ("Importance I:",    "eq_imp",  list(NSCPSeismic.IMP.keys()),      "I — Standard (I=1.0)"),
        ]
        for r, (lbl, key, vals, dflt) in enumerate(site_fields):
            ttk.Label(sf, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            self.vars[key] = tk.StringVar(value=dflt)
            ttk.Combobox(sf, textvariable=self.vars[key],
                         values=vals, width=26).grid(
                row=r, column=1, sticky="w", padx=(8,0), pady=4)

        # System
        rf = ttk.LabelFrame(lc, text=" Structural System ", padding=10)
        rf.pack(fill="x")
        sys_fields = [
            ("R factor:", "eq_R",  list(NSCPSeismic.R.keys()),  "IMF Concrete (R=5.5)"),
            ("Period Ct:","eq_Ct", list(NSCPSeismic.CT.keys()), "Concrete MRF"),
        ]
        for r, (lbl, key, vals, dflt) in enumerate(sys_fields):
            ttk.Label(rf, text=lbl).grid(row=r, column=0, sticky="w", pady=4)
            self.vars[key] = tk.StringVar(value=dflt)
            ttk.Combobox(rf, textvariable=self.vars[key],
                         values=vals, width=26).grid(
                row=r, column=1, sticky="w", padx=(8,0), pady=4)

        # Results
        rp = ttk.LabelFrame(rc, text=" Seismic Results (click Compute Seismic) ", padding=8)
        rp.pack(fill="both", expand=True)
        self.eq_res = scrolledtext.ScrolledText(rp, height=14, width=38,
                                                 wrap=tk.WORD, font=("Consolas", 8))
        self.eq_res.pack(fill="both", expand=True)
        self.eq_res.config(state=tk.DISABLED)

        # Equations reference
        ref = ttk.LabelFrame(p, text=" NSCP 2015 §208 Key Equations ", padding=8)
        ref.pack(fill="x", pady=(6, 0))
        eqs = [
            "T = Ct × hn^0.75  (§208.5.2.2)",
            "V = Cv·I·W / (R·T)  (§208.5.3.1)",
            "Vmin = 0.11·Ca·I·W",
            "Vmax = 2.5·Ca·I·W / R",
            "Fx = (V−Ft)·wx·hx / Σwi·hi  (§208.5.6)",
            "Ft = 0.07·T·V  if T > 0.7 s",
        ]
        for i, e in enumerate(eqs):
            ttk.Label(ref, text=f"  ⬡  {e}", foreground="gray").grid(
                row=i//2, column=i%2, sticky="w", padx=8, pady=2)

    # ──────────────────────────────────────────────────────────────────────────
    #  EVENT HANDLERS
    # ──────────────────────────────────────────────────────────────────────────
    def _on_mat_change(self):
        mat = self.mat_var.get()
        if mat == "Concrete (RC)":
            self.rc_frame.pack(fill="x", pady=(0,6))
            self.steel_frame.pack_forget()
        else:
            self.rc_frame.pack_forget()
            self.steel_frame.pack(fill="x", pady=(0,6))

    def _on_fc_change(self):
        if self.vars["fc_sel"].get() == "Custom":
            self.fc_custom_frame.grid()
        else:
            self.fc_custom_frame.grid_remove()

    def _on_eq_toggle(self):
        if self.eq_var.get():
            self.eq_body.pack(fill="x")
        else:
            self.eq_body.pack_forget()

    def _browse_file(self):
        fp = filedialog.asksaveasfilename(
            defaultextension=".std",
            filetypes=[("STAAD Files", "*.std"), ("All files", "*.*")],
            initialfile="TwoStoreyHouse.std")
        if fp:
            self.vars["file"].set(fp)

    # ──────────────────────────────────────────────────────────────────────────
    #  PARAMETER COLLECTION & VALIDATION
    # ──────────────────────────────────────────────────────────────────────────
    def _collect_params(self):
        v = self.vars
        fv = lambda k: float(v[k].get())
        iv = lambda k: int(v[k].get())
        sv = lambda k: v[k].get()

        # fc
        fc_s = sv("fc_sel")
        fc   = float(self.fc_custom_var.get()) if fc_s == "Custom" else float(fc_s)
        fy   = float(sv("fy_sel").split()[0])
        fyt  = float(sv("fyt_sel").split()[0])

        return dict(
            bays_x   = iv("bays_x"),  bays_z  = iv("bays_z"),
            bay_w    = fv("bay_w"),   bay_d   = fv("bay_d"),
            h1       = fv("h1"),      h2      = fv("h2"),
            mat      = self.mat_var.get(),
            fc=fc, fy=fy, fyt=fyt,
            col_b    = fv("col_b"),   col_h   = fv("col_h"),
            beam_b   = fv("beam_b"),  beam_h  = fv("beam_h"),
            sb_b     = fv("sb_b"),    sb_h    = fv("sb_h"),
            col_sec  = sv("col_sec"),
            beam_sec = sv("beam_sec"),
            sb_sec   = sv("sb_sec"),
            dl=fv("dl"), ll=fv("ll"), wl=fv("wl"),
            eq       = self.eq_var.get(),
            eq_zone  = sv("eq_zone"), eq_soil = sv("eq_soil"),
            eq_imp   = sv("eq_imp"),  eq_R    = sv("eq_R"),
            eq_Ct    = sv("eq_Ct"),
            unit         = sv("unit"),
            support_type = sv("support_type"),
            sw       = self.sw_var.get(),
            combo    = self.combo_var.get(),
            file     = sv("file"),
        )

    def _validate(self):
        errors = []; warnings = []
        try:
            p = self._collect_params()
            if p['bays_x'] < 1 or p['bays_z'] < 1:
                errors.append("Bays must be ≥ 1")
            if p['bay_w'] <= 0 or p['bay_d'] <= 0:
                errors.append("Bay dimensions must be > 0")
            if p['h1'] <= 0 or p['h2'] <= 0:
                errors.append("Storey heights must be > 0")
            if p['mat'] == "Concrete (RC)":
                if p['col_b'] < 200 or p['col_h'] < 200:
                    warnings.append("Column dimensions seem small (< 200 mm)")
                if p['beam_h'] < p['beam_b']:
                    warnings.append("Beam depth < width — check dimensions")
        except ValueError as e:
            errors.append(f"Invalid input: {e}")
        return errors, warnings

    # ──────────────────────────────────────────────────────────────────────────
    #  PREVIEW
    # ──────────────────────────────────────────────────────────────────────────
    def preview_model(self):
        errs, warns = self._validate()
        if errs:
            messagebox.showerror("Errors", "\n".join(f"• {e}" for e in errs))
            return
        p = self._collect_params()
        nx = p['bays_x']+1; nz = p['bays_z']+1; lvs = 3
        n_nodes   = nx * nz * lvs
        n_cols    = nx * nz * 2
        n_beams   = (p['bays_x']*nz + p['bays_z']*nx) * 2
        n_members = n_cols + n_beams
        hn        = p['h1'] + p['h2']

        txt = f"""Two-Storey House Model — Preview
{'='*52}

GEOMETRY
  Footprint   : {p['bays_x']*p['bay_w']:.1f} m × {p['bays_z']*p['bay_d']:.1f} m
  Total Height: {hn:.1f} m  ({p['h1']} + {p['h2']} m)
  Bays X × Z  : {p['bays_x']} × {p['bays_z']}
  Bay Size    : {p['bay_w']} m × {p['bay_d']} m
  Floor Levels: 2 (+ base)

MODEL SIZE
  Nodes       : {n_nodes}
  Members     : ~{n_members}
    Columns   : {n_cols}
    Beams     : {n_beams}

MATERIAL: {p['mat']}"""
        if p['mat'] == "Concrete (RC)":
            txt += f"""
  f'c = {p['fc']} MPa  |  fy = {p['fy']} MPa  |  fyt = {p['fyt']} MPa
  Ec  = {4700*math.sqrt(p['fc']):.0f} MPa
  Column   : {p['col_b']} × {p['col_h']} mm
  Beam     : {p['beam_b']} × {p['beam_h']} mm
  Sec Beam : {p['sb_b']} × {p['sb_h']} mm"""
        else:
            txt += f"""
  Column   : {p['col_sec']}
  Beam     : {p['beam_sec']}
  Sec Beam : {p['sb_sec']}"""

        txt += f"""

LOADS (kN/m²)
  Dead      : {p['dl']}
  Live      : {p['ll']}
  Wind      : {p['wl']}

SEISMIC    : {'Zone '+p['eq_zone'] if p['eq'] else 'Disabled'}"""
        if p['eq']:
            area = p['bays_x']*p['bay_w']*p['bays_z']*p['bay_d']
            W    = (p['dl']+0.25*p['ll'])*area*2
            sr   = NSCPSeismic.compute(p['eq_zone'],p['eq_soil'],
                                       p['eq_imp'],p['eq_R'],p['eq_Ct'],hn,W)
            txt += f"""
  T = {sr['T']:.3f} s  |  V = {sr['V']:.2f} kN

NOTES:
  Supports NOT assigned — configure in STAAD.Pro
  Column base nodes: every ({p['bays_z']+1}) nodes per level
"""
        if warns:
            txt += "\nWARNINGS:\n" + "\n".join(f"• {w}" for w in warns)

        win = tk.Toplevel(self.root)
        win.title("Model Preview"); win.geometry("580x640")
        t = scrolledtext.ScrolledText(win, wrap=tk.WORD, width=68, height=40)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        t.insert(1.0, txt); t.config(state=tk.DISABLED)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=8)

    # ──────────────────────────────────────────────────────────────────────────
    #  SEISMIC PREVIEW
    # ──────────────────────────────────────────────────────────────────────────
    def seismic_preview(self):
        try: p = self._collect_params()
        except Exception as e:
            messagebox.showerror("Input Error", str(e)); return
        if not p['eq']:
            messagebox.showinfo("Seismic", "Seismic is disabled."); return

        area = p['bays_x']*p['bay_w'] * p['bays_z']*p['bay_d']
        W1   = (p['dl']+0.25*p['ll'])*area
        W    = W1 * 2
        hn   = p['h1']+p['h2']
        sr   = NSCPSeismic.compute(p['eq_zone'],p['eq_soil'],
                                   p['eq_imp'],p['eq_R'],p['eq_Ct'],hn,W)
        swh  = W1*p['h1'] + W1*(p['h1']+p['h2'])
        F1   = (sr['V']-sr['Ft'])*W1*p['h1']/swh
        F2   = (sr['V']-sr['Ft'])*W1*(p['h1']+p['h2'])/swh + sr['Ft']

        lines = [
            "╔══════════════════════════════════════",
            "║  NSCP 2015 §208 — SEISMIC RESULTS",
            "╠══════════════════════════════════════",
            f"║  Zone       : {p['eq_zone']}",
            f"║  Soil       : {p['eq_soil']}",
            f"║  Ca         : {sr['Ca']:.4f}",
            f"║  Cv         : {sr['Cv']:.4f}",
            f"║  I          : {sr['I']}",
            f"║  R          : {sr['R']}",
            f"║  Ct         : {sr['Ct']}",
            "╠══════════════════════════════════════",
            f"║  hn         : {hn:.2f} m",
            f"║  T (Meth.A) : {sr['T']:.4f} s",
            f"║  W (seismic): {W:.2f} kN",
            "╠══════════════════════════════════════",
            f"║  V_design   : {sr['Vd']:.2f} kN",
            f"║  V_min      : {sr['Vn']:.2f} kN",
            f"║  V_max      : {sr['Vx']:.2f} kN",
            f"║  V (govern) : {sr['V']:.2f} kN  ◄",
            f"║  Ft (top)   : {sr['Ft']:.2f} kN",
            "╠══════════════════════════════════════",
            f"║  F1 (Floor2): {F1:.2f} kN",
            f"║  F2 (Roof)  : {F2:.2f} kN",
            "╚══════════════════════════════════════",
        ]
        self.eq_res.config(state=tk.NORMAL)
        self.eq_res.delete(1.0, tk.END)
        self.eq_res.insert(1.0, "\n".join(lines))
        self.eq_res.config(state=tk.DISABLED)
        self.log("── SEISMIC RESULTS ──────────────────────", "eq")
        for l in lines: self.log(l, "eq")

    # ──────────────────────────────────────────────────────────────────────────
    #  BUILD
    # ──────────────────────────────────────────────────────────────────────────
    def build_model(self):
        self._start_build(run_analysis=False)

    def build_and_analyze(self):
        self._start_build(run_analysis=True)

    def _start_build(self, run_analysis):
        if not STAAD_AVAILABLE:
            messagebox.showerror("Error",
                "openstaadpy not found!\n\nInstall:  pip install openstaadpy\n"
                "Then open STAAD.Pro with an empty .std model.")
            return
        if self.is_running:
            messagebox.showwarning("Busy", "Build already running!"); return

        errs, warns = self._validate()
        if errs:
            messagebox.showerror("Errors", "\n".join(f"• {e}" for e in errs)); return
        if warns:
            if not messagebox.askyesno("Warnings",
                "\n".join(f"• {w}" for w in warns) + "\n\nContinue?"): return

        try: p = self._collect_params()
        except Exception as e: messagebox.showerror("Input", str(e)); return

        t = threading.Thread(target=self._build_thread,
                             args=(p, run_analysis), daemon=True)
        t.start()

    def _build_thread(self, p, run_analysis):
        self.is_running = True
        self._set_btns("disabled")
        self.progress.start(10)
        try:
            self._execute_build(p, run_analysis)
        except Exception as e:
            self.log(f"ERROR: {e}", "error")
            self.log(traceback.format_exc(), "error")
            self.root.after(0, lambda: messagebox.showerror("Build Failed", str(e)))
        finally:
            self.progress.stop()
            self._set_btns("normal")
            self.is_running = False
            self.status_var.set("Ready")

    # ──────────────────────────────────────────────────────────────────────────
    #  CORE BUILD — writes the .std file directly, then opens in STAAD.Pro
    #  This is the ONLY reliable way to guarantee correct units + properties.
    # ──────────────────────────────────────────────────────────────────────────
    def _execute_build(self, p, run_analysis):
        self.log("="*60)
        self.log("Starting Two-Storey House Build …")

        unit     = p['unit']
        mat      = p['mat']
        fp       = p['file']
        sup_type = p.get('support_type', 'FIXED')

        # ── Grid dimensions ───────────────────────────────────────────────────
        nx = p['bays_x']+1;  nz = p['bays_z']+1
        bw = p['bay_w'];     bd = p['bay_d']
        h1 = p['h1'];        h2 = p['h2']
        DL = p['dl'];  LL = p['ll'];  WL = p['wl']

        # ── Unit-aware dimension conversion ───────────────────────────────────
        # All input is in metres (bays) and mm (sections); convert for chosen unit
        if unit == "METER-KN":
            L_div  = 1.0       # coords already in metres
            S_div  = 1000.0    # mm → m  for section dims
            u_str  = "METER KN"
            # Material properties for METER-KN
            E_conc = 4700*math.sqrt(p['fc'])*1000   # kN/m²
            E_steel= 200000000                       # kN/m²
            dens_c = 24.0                            # kN/m³
            dens_s = 76.82                           # kN/m³
        elif unit == "FEET-KIP":
            L_div  = 0.3048    # m → ft
            S_div  = 304.8     # mm → ft
            u_str  = "FEET KIP"
            E_conc = 4700*math.sqrt(p['fc'])*20.885 # kip/ft²
            E_steel= 4176000                         # kip/ft²  (29000 ksi → kip/ft²)
            dens_c = 0.1502                          # kip/ft³
            dens_s = 0.4900                          # kip/ft³
        else:  # INCHES-KIP
            L_div  = 0.0254    # m → inches
            S_div  = 25.4      # mm → inches
            u_str  = "INCH KIP"
            E_conc = 4700*math.sqrt(p['fc'])*0.14504 # ksi
            E_steel= 29000                            # ksi
            dens_c = 8.68e-5                          # kip/in³
            dens_s = 2.836e-4                         # kip/in³

        # ── Build node table ──────────────────────────────────────────────────
        self.status_var.set("Building node table …")
        nid = 1
        node_map = {}
        nodes = []   # list of (id, x, y, z)  in model units
        for lv, yy in enumerate([0.0, h1, h1+h2]):
            for ix in range(nx):
                for iz in range(nz):
                    x = (ix*bw) / L_div
                    y = yy      / L_div
                    z = (iz*bd) / L_div
                    node_map[(lv,ix,iz)] = nid
                    nodes.append((nid, x, y, z))
                    nid += 1
        total_nodes = nid-1

        # ── Build member table ────────────────────────────────────────────────
        mid=1; col_mems=[]; beam_mems=[]; sbm_mems=[]; members=[]
        for ix in range(nx):
            for iz in range(nz):
                for lv in range(2):
                    members.append((mid, node_map[(lv,ix,iz)], node_map[(lv+1,ix,iz)]))
                    col_mems.append(mid); mid+=1
        for lv in [1,2]:
            for iz in range(nz):
                for ix in range(nx-1):
                    members.append((mid, node_map[(lv,ix,iz)], node_map[(lv,ix+1,iz)]))
                    beam_mems.append(mid); mid+=1
        for lv in [1,2]:
            for ix in range(nx):
                for iz in range(nz-1):
                    members.append((mid, node_map[(lv,ix,iz)], node_map[(lv,ix,iz+1)]))
                    sbm_mems.append(mid); mid+=1
        total_members = mid-1

        def ml(ids): return " ".join(str(i) for i in ids)

        # ── Seismic calculation ───────────────────────────────────────────────
        has_eq = p['eq']
        if has_eq:
            area = p['bays_x']*bw * p['bays_z']*bd   # m²
            W1 = (DL+0.25*LL)*area     # kN (DL/LL in kN/m², area in m²)
            W  = W1*2; hn = h1+h2
            sr = NSCPSeismic.compute(p['eq_zone'],p['eq_soil'],
                                     p['eq_imp'],p['eq_R'],p['eq_Ct'],hn,W)
            V=sr['V']; Ft=sr['Ft']
            swh = W1*h1 + W1*(h1+h2)
            F1 = (V-Ft)*W1*h1/swh
            F2 = (V-Ft)*W1*(h1+h2)/swh + Ft
            n_fl = nx*nz
            f1n_kN=F1/n_fl; f2n_kN=F2/n_fl

            # Convert seismic nodal forces to model units
            eq_conv = {"METER-KN":1.0, "FEET-KIP":0.22481, "INCHES-KIP":0.22481}
            ec = eq_conv.get(unit, 1.0)
            f1n = f1n_kN * ec
            f2n = f2n_kN * ec

            self.log(f"  Seismic: T={sr['T']:.3f}s W={W:.1f}kN V={V:.2f}kN", "eq")
            self.log(f"  F1={F1:.2f}kN F2={F2:.2f}kN per-node:{f1n_kN:.3f}/{f2n_kN:.3f}kN", "eq")

        # ── Tributary load per metre — in MODEL units ─────────────────────────
        # DL/LL/WL inputs are in kN/m².  Convert to model force/length units.
        # For METER-KN: kN/m² × m = kN/m  (no conversion needed)
        # For FEET-KIP: kN/m² × 0.02089 = kip/ft²; × ft trib = kip/ft
        # For INCH-KIP: kN/m² × 0.001450 = ksi; × in trib = kip/in
        if unit == "METER-KN":
            f_conv = 1.0           # kN/m stays kN/m
            tx = bd/2; tz = bw/2   # tributary widths already in metres
        elif unit == "FEET-KIP":
            f_conv = 0.020885      # kN/m → kip/ft  per unit width
            tx = (bd/2) / 0.3048   # tributary width in feet
            tz = (bw/2) / 0.3048
        else:  # INCHES-KIP
            f_conv = 0.001749      # kN/m → kip/in  per unit width
            tx = (bd/2) / 0.0254
            tz = (bw/2) / 0.0254

        dl_b = DL * f_conv * tx
        dl_s = DL * f_conv * tz
        ll_b = LL * f_conv * tx
        ll_s = LL * f_conv * tz
        wl_x = WL * f_conv * (bd / L_div)   # wind on column face
        wl_z = WL * f_conv * (bw / L_div)

        self.log(f"  Loads in {unit}: DL beam={dl_b:.4f}  LL beam={ll_b:.4f}  "
                 f"WL x={wl_x:.4f}", "success")

        # ── Section dimensions in model units ─────────────────────────────────
        if mat == "Concrete (RC)":
            col_yd = p['col_h']/S_div;  col_zd = p['col_b']/S_div
            bm_yd  = p['beam_h']/S_div; bm_zd  = p['beam_b']/S_div
            sb_yd  = p['sb_h']/S_div;   sb_zd  = p['sb_b']/S_div

        # ── Write the .std file ───────────────────────────────────────────────
        self.status_var.set("Writing .std file …")
        self.log(f"Writing: {fp}")
        lines = []
        W = lines.append   # shorthand

        W(f"STAAD SPACE TWO-STOREY HOUSE NSCP 2015")
        W(f"START JOB INFORMATION")
        W(f"ENGINEER DATE {datetime.now().strftime('%d-%b-%Y')}")
        W(f"END JOB INFORMATION")
        W(f"INPUT WIDTH 79")
        W(f"UNIT {u_str}")
        W(f"JOINT COORDINATES")
        for nid_i, x, y, z in nodes:
            W(f"{nid_i} {x:.6f} {y:.6f} {z:.6f}")
        W(f"MEMBER INCIDENCES")
        for mid_i, n1, n2 in members:
            W(f"{mid_i} {n1} {n2}")

        # Member properties
        if mat == "Concrete (RC)":
            W(f"MEMBER PROPERTY")
            W(f"{ml(col_mems)} PRIS YD {col_yd:.6f} ZD {col_zd:.6f}")
            W(f"{ml(beam_mems)} PRIS YD {bm_yd:.6f} ZD {bm_zd:.6f}")
            W(f"{ml(sbm_mems)} PRIS YD {sb_yd:.6f} ZD {sb_zd:.6f}")
        else:
            cs=p['col_sec']; bs=p['beam_sec']; ss=p['sb_sec']
            # AMERICAN keyword must be on SAME line as MEMBER PROPERTY
            W(f"MEMBER PROPERTY AMERICAN")
            W(f"{ml(col_mems)} TABLE ST {cs}")
            W(f"{ml(beam_mems)} TABLE ST {bs}")
            W(f"{ml(sbm_mems)} TABLE ST {ss}")

        # Material definition
        W(f"DEFINE MATERIAL START")
        if mat == "Concrete (RC)":
            W(f"ISOTROPIC CONCRETE")
            W(f"E {E_conc:.2f}")
            W(f"POISSON 0.17")
            W(f"DENSITY {dens_c:.4f}")
            W(f"ALPHA 1E-05")
            W(f"DAMP 0.05")
        else:
            W(f"ISOTROPIC STEEL")
            W(f"E {E_steel:.2f}")
            W(f"POISSON 0.3")
            W(f"DENSITY {dens_s:.6f}")
            W(f"ALPHA 1.2E-05")
            W(f"DAMP 0.03")
        W(f"END DEFINE MATERIAL")

        # Constants (material assignment)
        W(f"CONSTANTS")
        mat_name = "CONCRETE" if mat == "Concrete (RC)" else "STEEL"
        W(f"MATERIAL {mat_name} MEMB {ml(col_mems+beam_mems+sbm_mems)}")

        # Supports
        base_nodes = [node_map[(0,ix,iz)] for ix in range(nx) for iz in range(nz)]
        W(f"SUPPORTS")
        W(f"{ml(base_nodes)} {sup_type}")

        # Loads
        W(f"LOAD 1 LOADTYPE Dead TITLE DEAD LOAD")
        if p['sw']:
            W(f"SELFWEIGHT Y -1.0")
        W(f"MEMBER LOAD")
        for m in beam_mems:
            W(f"{m} UNI GY -{dl_b:.6f}")
        for m in sbm_mems:
            W(f"{m} UNI GY -{dl_s:.6f}")

        W(f"LOAD 2 LOADTYPE Live TITLE LIVE LOAD")
        W(f"MEMBER LOAD")
        for m in beam_mems:
            W(f"{m} UNI GY -{ll_b:.6f}")
        for m in sbm_mems:
            W(f"{m} UNI GY -{ll_s:.6f}")

        W(f"LOAD 3 LOADTYPE Wind TITLE WIND +X")
        W(f"MEMBER LOAD")
        for m in col_mems:
            W(f"{m} UNI GX {wl_x:.6f}")

        W(f"LOAD 4 LOADTYPE Wind TITLE WIND +Z")
        W(f"MEMBER LOAD")
        for m in col_mems:
            W(f"{m} UNI GZ {wl_z:.6f}")

        if has_eq:
            W(f"LOAD 5 LOADTYPE Seismic TITLE EQ +X V={V:.2f}kN")
            W(f"JOINT LOAD")
            for ix in range(nx):
                for iz in range(nz):
                    W(f"{node_map[(1,ix,iz)]} FX {f1n:.6f}")
                    W(f"{node_map[(2,ix,iz)]} FX {f2n:.6f}")
            W(f"LOAD 6 LOADTYPE Seismic TITLE EQ +Z V={V:.2f}kN")
            W(f"JOINT LOAD")
            for ix in range(nx):
                for iz in range(nz):
                    W(f"{node_map[(1,ix,iz)]} FZ {f1n:.6f}")
                    W(f"{node_map[(2,ix,iz)]} FZ {f2n:.6f}")

        # Load combinations
        if p['combo']:
            combos = [
                (7,  "1.4D",            [(1,1.4)]),
                (8,  "1.2D+1.6L",       [(1,1.2),(2,1.6)]),
                (9,  "1.2D+1.0L+1.6Wx", [(1,1.2),(2,1.0),(3,1.6)]),
                (10, "1.2D+1.0L+1.6Wz", [(1,1.2),(2,1.0),(4,1.6)]),
                (11, "0.9D+1.0Wx",      [(1,0.9),(3,1.0)]),
                (12, "0.9D+1.0Wz",      [(1,0.9),(4,1.0)]),
            ]
            if has_eq:
                combos += [
                    (13,"1.2D+1.0L+1.0Ex",[(1,1.2),(2,1.0),(5,1.0)]),
                    (14,"1.2D+1.0L+1.0Ez",[(1,1.2),(2,1.0),(6,1.0)]),
                    (15,"0.9D+1.0Ex",      [(1,0.9),(5,1.0)]),
                    (16,"0.9D+1.0Ez",      [(1,0.9),(6,1.0)]),
                ]
            for cid, ctitle, factors in combos:
                fstr = " ".join(f"{lc} {f}" for lc,f in factors)
                W(f"LOAD COMBINATION {cid} {ctitle}")
                W(fstr)

        W(f"PERFORM ANALYSIS PRINT STATICS CHECK")
        W(f"FINISH")

        # Write file
        std_content = "\n".join(lines) + "\n"
        with open(fp, "w") as f:
            f.write(std_content)
        self.log(f"  .std file written ({len(lines)} lines)", "success")

        # ── Open in STAAD.Pro via openstaadpy ─────────────────────────────────
        self.status_var.set("Opening in STAAD.Pro …")
        self.log("Opening model in STAAD.Pro …")
        try:
            self.staad = os_analytical.connect()
            # Open the .std file we just wrote
            try:
                self.staad.OpenSTAADFile(fp)
            except Exception:
                try:
                    self.staad.NewSTAADFile(fp, "Two-Storey House NSCP2015")
                except Exception:
                    pass
            self.staad.SaveModel(True)
            self.log("Opened in STAAD.Pro ✓", "success")
        except Exception as e:
            self.log(f"  STAAD open note: {e}", "warning")
            self.log(f"  File written at: {fp}", "warning")
            self.log("  Open it manually: File → Open in STAAD.Pro", "warning")

        # Run analysis
        if run_analysis:
            self.status_var.set("Running analysis …")
            self.log("Running analysis …")
            try:
                self.staad.Command.PerformAnalysis(0)
                self.log("Analysis complete ✓", "success")
            except Exception as e:
                self.log(f"  Analysis: {e}", "warning")

        # Summary
        self.log("="*60, "success")
        self.log("BUILD COMPLETE", "success")
        self.log(f"  Nodes    : {total_nodes}", "success")
        self.log(f"  Members  : {total_members}  ({len(col_mems)} col / "
                 f"{len(beam_mems)} beam / {len(sbm_mems)} sb)", "success")
        self.log(f"  Material : {mat_name}", "success")
        self.log(f"  Support  : {sup_type} at {len(base_nodes)} base nodes", "success")
        self.log(f"  Units    : {u_str}", "success")
        self.log(f"  File     : {fp}", "success")
        self.log("="*60, "success")
        self.log("TIP: View → Structure Diagrams → Rendering → Beam for 3D view","warning")
        self.status_var.set("Done!")
        self.root.after(0, lambda: messagebox.showinfo(
            "Build Complete ✓",
            f"Model written and opened!\n\n"
            f"  Nodes    : {total_nodes}\n"
            f"  Members  : {total_members}\n"
            f"  Material : {mat_name}\n"
            f"  Support  : {sup_type}\n"
            f"  Units    : {u_str}\n"
            f"  File     : {fp}\n\n"
            "3D view: View → Structure Diagrams\n"
            "  → Rendering tab → check 'Beam'"))

    # ──────────────────────────────────────────────────────────────────────────
    #  UTILITIES
    # ──────────────────────────────────────────────────────────────────────────
    def log(self, msg, tag="info"):
        ts = datetime.now().strftime("%H:%M:%S")
        def _a():
            self.log_text.insert(tk.END, f"[{ts}] {msg}\n", tag)
            self.log_text.see(tk.END)
            self.root.update_idletasks()
        self.root.after(0, _a)

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)
        self.log("Log cleared.")

    def _set_btns(self, state):
        for b in [self.btn_preview, self.btn_seismic,
                  self.btn_build, self.btn_analyze]:
            b['state'] = state

    def save_config(self):
        try:
            p = self._collect_params()
            p["mat"]    = self.mat_var.get()
            p["sw"]     = self.sw_var.get()
            p["combo"]  = self.combo_var.get()
            p["eq_on"]  = self.eq_var.get()
            fn = filedialog.asksaveasfilename(
                defaultextension=".json",
                filetypes=[("JSON","*.json")],
                title="Save Configuration")
            if fn:
                with open(fn, "w") as f: json.dump(p, f, indent=2)
                messagebox.showinfo("Saved", "Configuration saved!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def load_config(self):
        try:
            fn = filedialog.askopenfilename(
                filetypes=[("JSON","*.json")], title="Load Configuration")
            if fn:
                with open(fn) as f: p = json.load(f)
                for k, v_obj in self.vars.items():
                    if k in p: v_obj.set(str(p[k]))
                if "mat" in p:  self.mat_var.set(p["mat"]);  self._on_mat_change()
                if "sw" in p:   self.sw_var.set(p["sw"])
                if "combo" in p:self.combo_var.set(p["combo"])
                if "eq_on" in p:self.eq_var.set(p["eq_on"]); self._on_eq_toggle()
                messagebox.showinfo("Loaded", "Configuration loaded!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def export_log(self):
        try:
            fn = filedialog.asksaveasfilename(
                defaultextension=".txt", filetypes=[("Text","*.txt")])
            if fn:
                with open(fn,"w") as f: f.write(self.log_text.get(1.0, tk.END))
                messagebox.showinfo("Exported", "Log exported!")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def show_about(self):
        messagebox.showinfo("About",
            "STAAD.Pro Two-Storey House Builder\n"
            "NSCP 2015 | §208 Seismic | Concrete & Steel\n\n"
            "Uses openstaadpy (same as WarehouseFrameBuilder)\n\n"
            "NOTE: Supports NOT assigned — configure\n"
            "manually in STAAD.Pro after build.")

    def show_guide(self):
        messagebox.showinfo("Guide",
            "PARAMETER GUIDE\n\n"
            "GEOMETRY:\n"
            "  Bays X/Z: column grid count\n"
            "  Bay Width/Depth: span in metres\n"
            "  Storey Heights: floor-to-floor (m)\n\n"
            "MATERIAL:\n"
            "  Concrete: enter fc, fy, fyt and b×h dims\n"
            "  Steel: pick section from AISC table\n\n"
            "LOADS:\n"
            "  All in kN/m² (superimposed)\n\n"
            "SEISMIC (NSCP 2015 §208):\n"
            "  Zone 2 or 4 | Soil SA–SE\n"
            "  R factor per structural system\n\n"
            "SUPPORTS:\n"
            "  NOT assigned — set in STAAD.Pro\n"
            "  Base nodes listed in log after build.")


# ══════════════════════════════════════════════════════════════════════════════
def main():
    root = tk.Tk()
    TwoStoreyHouseBuilder(root)
    root.mainloop()

if __name__ == "__main__":
    main()