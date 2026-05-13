"""
=============================================================================
  Solar Ground Mount – Frame Builder GUI
  Generates a STAAD.Pro .std input file for a Unirac-style 2-post
  ground mount racking system with 2 rows of portrait panels.

  STRUCTURE:
    - 2 rows of portrait panels (4 rails total, 2 per row)
    - Inclined rafter beams extending BEYOND both posts as cantilevers
      Rafter cantilever each side = (rafter_horiz_total - post_spacing_NS) / 2
    - Short south posts + tall north posts
    - Rails run E-W (Z direction) with cantilever overhangs at each end
    - Optional diagonal brace per bay:
        top end   → north post, 6 in above ground
        bottom end → south post, 6 in below its top

  UNITS: KIP FEET  (all inputs in ft, loads in ksf)

  COORDINATE SYSTEM:
    X → South (downslope)   Y → Up   Z → East (along bay)

  RUN:   python solar_gui_builder.py
  NEEDS: Python 3.8+  (tkinter built-in)
=============================================================================
"""

import os, math, tkinter as tk
from tkinter import ttk, filedialog, messagebox

# ── palette ───────────────────────────────────────────────────────────────────
BG      = "#0f1117"
PANEL   = "#1a1d27"
BORDER  = "#2a2d3e"
ACCENT  = "#3d8ef8"
ACCENT2 = "#f8a93d"
TEXT    = "#e8eaf0"
SUBTEXT = "#7c7f99"
OK_GRN  = "#3dffa0"
ERR_RED = "#ff5e5e"
ENTRY_BG= "#12151f"

# ─────────────────────────────────────────────────────────────────────────────
#  GEOMETRY BUILDER
# ─────────────────────────────────────────────────────────────────────────────

def build_std(p):
    """
    All inputs in FEET.  Output is KIP FEET STAAD .std text.

    Key geometry:
      - post_spacing_x  = N-S horizontal distance between south and north post (ft)
      - rafter_horiz    = total horizontal span of rafter (ft)  [user input]
      - rafter cant     = (rafter_horiz - post_spacing_x) / 2  (each side)
      - south post top  = (0, Hf)
      - north post top  = (post_spacing_x, Hr)
        where Hr = Hf + post_spacing_x * tan(tilt)
      - rafter south end = (-rcant, Hf - rcant*(Hr-Hf)/post_spacing_x)
      - rafter north end = ( post_spacing_x+rcant, Hr + rcant*(Hr-Hf)/post_spacing_x)

    Brace (per bay, optional, single diagonal):
      - top    = north post node 6 in (0.5 ft) above ground  = (Xsp, 0.5)
      - bottom = south post node 6 in (0.5 ft) below its top = (0,   Hf-0.5)
    """

    tilt    = math.radians(p["tilt_deg"])
    N       = p["num_bays"] + 1          # portal-frame count
    BL      = p["bay_length"]            # ft, bay spacing along Z
    RCANT   = p["rail_cantilever"]       # ft, rail overhang each side (along Z)
    Xsp     = p["post_spacing_x"]        # ft, N-S post horizontal distance
    Rh      = p["rafter_horiz"]          # ft, total rafter horizontal projection
    Hf      = p["front_post_ht"]         # ft, south post top height
    Hr      = Hf + Xsp * math.tan(tilt) # ft, north post top height (auto)

    # Rafter cantilever (each side, horizontal)
    rcant   = (Rh - Xsp) / 2.0          # ft

    # Slope of rafter in Y per unit X
    rft_slope = (Hr - Hf) / Xsp         # rise/run

    # South rafter end (X < 0 of south post)
    rft_s_x = -rcant
    rft_s_y = Hf - rcant * rft_slope

    # North rafter end (X > north post)
    rft_n_x = Xsp + rcant
    rft_n_y = Hr  + rcant * rft_slope

    # Panel width (for tributary load calculation only)
    PW      = p["panel_width"]           # ft

    # ── Rail positions: 4 rails equally spaced along the FULL rafter length ──
    # Full rafter inclined length (south cant end → north cant end)
    rafter_full_len = math.sqrt(Rh**2 + (rft_n_y - rft_s_y)**2)

    # Spacing = full_len / 5  →  rails at 1/5, 2/5, 3/5, 4/5 of full length
    rail_spacing = rafter_full_len / 5.0

    def pt_on_full_rafter(s):
        """Global (X,Y) at arc-length s from the rafter south-cantilever end."""
        ratio = s / rafter_full_len
        x = rft_s_x + ratio * (rft_n_x - rft_s_x)
        y = rft_s_y + ratio * (rft_n_y - rft_s_y)
        return round(x, 6), round(y, 6)

    # Rail 1 = Row-1 bottom, Rail 2 = Row-1 top
    # Rail 3 = Row-2 bottom, Rail 4 = Row-2 top
    r1_bot_xy = pt_on_full_rafter(1 * rail_spacing)
    r1_top_xy = pt_on_full_rafter(2 * rail_spacing)
    r2_bot_xy = pt_on_full_rafter(3 * rail_spacing)
    r2_top_xy = pt_on_full_rafter(4 * rail_spacing)

    # Post Z coordinates
    Z        = [i * BL for i in range(N)]
    rail_z_s = Z[0]  - RCANT
    rail_z_e = Z[-1] + RCANT

    # Brace node heights (global Y, same X as their respective posts)
    brace_north_y = 0.5          # 6 in above ground on north post
    brace_south_y = Hf - 0.5    # 6 in below top on south post

    # ── Node ID scheme ────────────────────────────────────────────────────────
    # Per frame i (0-based) → 12 nodes:
    #   sb(i)  = 12*i+1   south post base
    #   st(i)  = 12*i+2   south post top
    #   nb(i)  = 12*i+3   north post base
    #   nt(i)  = 12*i+4   north post top
    #   rs(i)  = 12*i+5   rafter south cantilever end
    #   rn(i)  = 12*i+6   rafter north cantilever end
    #   R1B(i) = 12*i+7   row-1 bottom rail on rafter
    #   R1T(i) = 12*i+8   row-1 top    rail on rafter
    #   R2B(i) = 12*i+9   row-2 bottom rail on rafter
    #   R2T(i) = 12*i+10  row-2 top    rail on rafter
    #   BSN(i) = 12*i+11  brace@south post (6in below top)
    #   BNN(i) = 12*i+12  brace@north post (6in above ground)
    # After 12*N: rail cantilever ends (8 nodes)

    def sb(i):  return 12*i+1
    def st(i):  return 12*i+2
    def nb(i):  return 12*i+3
    def nt(i):  return 12*i+4
    def rs(i):  return 12*i+5
    def rn(i):  return 12*i+6
    def R1B(i): return 12*i+7
    def R1T(i): return 12*i+8
    def R2B(i): return 12*i+9
    def R2T(i): return 12*i+10
    def BSN(i): return 12*i+11
    def BNN(i): return 12*i+12

    base_id  = 12*N
    C_R1B_S  = base_id+1; C_R1B_E = base_id+2
    C_R1T_S  = base_id+3; C_R1T_E = base_id+4
    C_R2B_S  = base_id+5; C_R2B_E = base_id+6
    C_R2T_S  = base_id+7; C_R2T_E = base_id+8
    total_nodes = base_id + 8

    F = lambda v: f"{v:.4f}"

    lines = [
        "STAAD SPACE",
        "INPUT WIDTH 79",
        "UNIT FEET KIP",
        "",
        "JOINT COORDINATES",
    ]

    for i, z in enumerate(Z):
        zs = F(z)
        lines += [
            f"  {sb(i)}   0.0      0.0         {zs}",
            f"  {st(i)}   0.0      {F(Hf)}     {zs}",
            f"  {nb(i)}   {F(Xsp)} 0.0         {zs}",
            f"  {nt(i)}   {F(Xsp)} {F(Hr)}     {zs}",
            f"  {rs(i)}   {F(rft_s_x)} {F(rft_s_y)} {zs}",
            f"  {rn(i)}   {F(rft_n_x)} {F(rft_n_y)} {zs}",
            f"  {R1B(i)}  {F(r1_bot_xy[0])} {F(r1_bot_xy[1])} {zs}",
            f"  {R1T(i)}  {F(r1_top_xy[0])} {F(r1_top_xy[1])} {zs}",
            f"  {R2B(i)}  {F(r2_bot_xy[0])} {F(r2_bot_xy[1])} {zs}",
            f"  {R2T(i)}  {F(r2_top_xy[0])} {F(r2_top_xy[1])} {zs}",
            # brace attachment nodes (same X as posts, intermediate Y)
            f"  {BSN(i)}  0.0      {F(brace_south_y)} {zs}",
            f"  {BNN(i)}  {F(Xsp)} {F(brace_north_y)} {zs}",
        ]

    # Rail cantilever end nodes (Z only varies, XY fixed to rail positions)
    for xy, cs, ce in [
        (r1_bot_xy, C_R1B_S, C_R1B_E),
        (r1_top_xy, C_R1T_S, C_R1T_E),
        (r2_bot_xy, C_R2B_S, C_R2B_E),
        (r2_top_xy, C_R2T_S, C_R2T_E),
    ]:
        lines += [
            f"  {cs}  {F(xy[0])} {F(xy[1])} {F(rail_z_s)}",
            f"  {ce}  {F(xy[0])} {F(xy[1])} {F(rail_z_e)}",
        ]
    lines.append("")

    # ── Member incidences ──────────────────────────────────────────────────────
    lines.append("MEMBER INCIDENCES")
    m = 1

    south_post_mems=[]; north_post_mems=[]
    rafter_mems=[]
    brace_mems=[]
    r1b_mems=[]; r1t_mems=[]; r2b_mems=[]; r2t_mems=[]

    # South posts  (base → top)
    for i in range(N):
        lines.append(f"  {m}  {sb(i)}  {st(i)}")
        south_post_mems.append(m); m+=1

    # North posts  (base → top)
    for i in range(N):
        lines.append(f"  {m}  {nb(i)}  {nt(i)}")
        north_post_mems.append(m); m+=1

    # Rafters – split into 7 segments:
    #   rs → st → R1B → R1T → R2B → R2T → nt → rn
    for i in range(N):
        for a, b in [
            (rs(i),  st(i)),
            (st(i),  R1B(i)),
            (R1B(i), R1T(i)),
            (R1T(i), R2B(i)),
            (R2B(i), R2T(i)),
            (R2T(i), nt(i)),
            (nt(i),  rn(i)),
        ]:
            lines.append(f"  {m}  {a}  {b}")
            rafter_mems.append(m); m+=1

    # Diagonal braces: one per frame, within the SAME frame
    # BNN(i) = north post node 6in above ground  (X = Xsp)
    # BSN(i) = south post node 6in below its top (X = 0)
    # Both share the same Z → brace lies entirely in the N-S plane
    if p.get("braces", True):
        for i in range(N):
            lines.append(f"  {m}  {BNN(i)}  {BSN(i)}")
            brace_mems.append(m); m+=1

    # Rails (continuous beams with cantilever ends)
    def add_rail(cant_s, mid_fn, cant_e, store):
        nonlocal m
        lines.append(f"  {m}  {cant_s}  {mid_fn(0)}"); store.append(m); m+=1
        for i in range(N-1):
            lines.append(f"  {m}  {mid_fn(i)}  {mid_fn(i+1)}"); store.append(m); m+=1
        lines.append(f"  {m}  {mid_fn(N-1)}  {cant_e}"); store.append(m); m+=1

    add_rail(C_R1B_S, R1B, C_R1B_E, r1b_mems)
    add_rail(C_R1T_S, R1T, C_R1T_E, r1t_mems)
    add_rail(C_R2B_S, R2B, C_R2B_E, r2b_mems)
    add_rail(C_R2T_S, R2T, C_R2T_E, r2t_mems)

    total_members = m - 1
    all_post = south_post_mems + north_post_mems
    all_rail = r1b_mems + r1t_mems + r2b_mems + r2t_mems
    def ml(lst): return " ".join(str(x) for x in lst)

    lines.append("")

    # ── Member properties ─────────────────────────────────────────────────────
    lines += [
        "MEMBER PROPERTY AMERICAN",
        f"  {ml(all_post)}    TABLE ST {p['sec_post']}",
        f"  {ml(rafter_mems)} TABLE ST {p['sec_rafter']}",
        f"  {ml(all_rail)}    TABLE ST {p['sec_rail']}",
    ]
    if brace_mems:
        lines.append(f"  {ml(brace_mems)} TABLE ST {p['sec_brace']}")
    lines.append("")

    # ── Member releases ───────────────────────────────────────────────────────
    # Braces: pin both ends (axial-only)
    if brace_mems:
        lines.append("MEMBER RELEASE")
        for mb in brace_mems:
            lines.append(f"  {mb} START MX MY MZ")
            lines.append(f"  {mb} END   MX MY MZ")
        lines.append("")

    # ── Supports ──────────────────────────────────────────────────────────────
    base_nodes = []
    for i in range(N):
        base_nodes += [sb(i), nb(i)]
    lines += [
        "SUPPORTS",
        "  " + " ".join(str(n) for n in base_nodes) + " FIXED",
        "",
        "CONSTANTS",
        "  MATERIAL STEEL ALL",
        "",
    ]

    # ── Loads (KIP/FT) ────────────────────────────────────────────────────────
    # Tributary widths on each rail (ft)
    # 4 rails equally spaced → each panel row = PW, 2 rails per row
    # Each rail carries half the panel width as tributary
    trib_per_rail = PW / 2.0

    DL = p["dead_ksf"]   # ksf
    WL = p["wind_ksf"]   # ksf
    SL = p["snow_ksf"]   # ksf

    # UDL on each rail (kip/ft) — all 4 rails carry equal tributary width
    d_rail  = DL * trib_per_rail
    wy_rail = WL * trib_per_rail * math.cos(tilt)
    wx_rail = WL * trib_per_rail * math.sin(tilt)
    s_rail  = SL * trib_per_rail * math.cos(tilt)
    # Aliases so udl_block works unchanged (bot and top carry same load)
    d_bot = d_top = d_rail
    wy_bot = wy_top = wy_rail
    wx_bot = wx_top = wx_rail
    s_bot  = s_top  = s_rail

    def udl_block(lc_num, title, bot_gy, top_gy, bx=0.0, tx=0.0, selfwt=False):
        out = [f"LOAD {lc_num} LOADTYPE {title} TITLE {title}"]
        if selfwt:
            out.append("  SELFWEIGHT Y -1.0")
        out.append("  MEMBER LOAD")
        for grp, gy, gx in [
            (r1b_mems + r2b_mems, bot_gy, bx),
            (r1t_mems + r2t_mems, top_gy, tx),
        ]:
            for mb in grp:
                if gy: out.append(f"  {mb} UNI GY {gy:.6f}")
                if gx: out.append(f"  {mb} UNI GX {gx:.6f}")
        return out

    lines += udl_block(1, "Dead", -d_bot, -d_top, selfwt=True);  lines.append("")
    lines += udl_block(2, "Wind", -wy_bot, -wy_top, -wx_bot, -wx_top); lines.append("")
    lines += udl_block(3, "Wind", +wy_bot, +wy_top, +wx_bot, +wx_top); lines.append("")
    lines += udl_block(4, "Snow", -s_bot, -s_top);                     lines.append("")

    lines += [
        "LOAD COMBINATION 101",
        "  TITLE LRFD 1.4D",          "  1 1.4", "",
        "LOAD COMBINATION 102",
        "  TITLE LRFD 1.2D+1.6S",     "  1 1.2  4 1.6", "",
        "LOAD COMBINATION 103",
        "  TITLE LRFD 1.2D+Wp+0.5S",  "  1 1.2  2 1.0  4 0.5", "",
        "LOAD COMBINATION 104",
        "  TITLE LRFD 0.9D+Wu",        "  1 0.9  3 1.0", "",
        "PERFORM ANALYSIS PRINT ALL", "",
        "PARAMETER 1",
        "  CODE AISC UNIFIED 2016",
        "  TRACK 2 ALL",
        "  FYLD 36 ALL",
        "CHECK CODE ALL", "",
        "FINISH",
    ]

    summary = dict(
        total_nodes=total_nodes, total_members=total_members,
        south_posts=len(south_post_mems), north_posts=len(north_post_mems),
        rafters=len(rafter_mems), braces=len(brace_mems),
        rails=len(all_rail),
        north_post_ht=round(Hr, 4),
        rafter_cant=round(rcant, 4),
        rafter_total_horiz=round(Rh, 4),
    )
    return "\n".join(lines), summary


# ─────────────────────────────────────────────────────────────────────────────
#  GUI
# ─────────────────────────────────────────────────────────────────────────────

class SolarFrameBuilder(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Solar Ground Mount — Frame Builder")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(900, 700)
        self.vars = {}
        self._setup_fonts()
        self._build_ui()
        self.update_idletasks()
        w, h = 980, 820
        x = (self.winfo_screenwidth()  - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

    def _setup_fonts(self):
        self.fH2    = ("Consolas", 11, "bold")
        self.fLbl   = ("Consolas",  9)
        self.fSmall = ("Consolas",  8)
        self.fMono  = ("Consolas",  9)
        self.fBadge = ("Consolas",  8, "bold")

    # ── main layout ───────────────────────────────────────────────────────────
    def _build_ui(self):
        hdr = tk.Frame(self, bg="#080a10", height=52)
        hdr.pack(fill="x"); hdr.pack_propagate(False)
        tk.Label(hdr, text="⬡  SOLAR FRAME BUILDER",
                 bg="#080a10", fg=ACCENT,
                 font=("Consolas",13,"bold")).pack(side="left", padx=18, pady=13)
        tk.Label(hdr,
                 text="STAAD.Pro Generator  ·  Unirac 2-Post Ground Mount  ·  KIP / FT",
                 bg="#080a10", fg=SUBTEXT, font=("Consolas",8)).pack(side="left", pady=16)

        body = tk.Frame(self, bg=BG)
        body.pack(fill="both", expand=True, padx=14, pady=(10,0))

        left  = tk.Frame(body, bg=BG)
        right = tk.Frame(body, bg=BG)
        left.pack(side="left",  fill="both", expand=True, padx=(0,8))
        right.pack(side="left", fill="both", expand=True)

        self._section(left, "GEOMETRY",  self._geom_fields())
        self._section(left, "SECTIONS",  self._sec_fields())
        self._section(left, "LOADS",     self._load_fields())
        self._section(left, "OUTPUT",    self._out_fields())

        self._build_schematic(right)
        self._build_log(right)
        self._build_buttons(right)

    # ── card section ──────────────────────────────────────────────────────────
    def _section(self, parent, title, fields):
        card = tk.Frame(parent, bg=PANEL)
        card.pack(fill="x", pady=(0,6))
        tb = tk.Frame(card, bg=BORDER, height=26); tb.pack(fill="x"); tb.pack_propagate(False)
        tk.Label(tb, text=f"  {title}", bg=BORDER, fg=ACCENT2, font=self.fH2).pack(side="left", pady=4)
        inner = tk.Frame(card, bg=PANEL)
        inner.pack(fill="x", padx=10, pady=6)

        for i, (key, label, default, *rest) in enumerate(fields):
            opts = rest[0] if rest else {}
            r, c = i // 2, (i % 2) * 3
            tk.Label(inner, text=label, bg=PANEL, fg=SUBTEXT,
                     font=self.fLbl, anchor="w").grid(row=r, column=c, sticky="w", padx=(0,4), pady=2)

            if opts.get("type") == "check":
                var = tk.BooleanVar(value=default)
                tk.Checkbutton(inner, variable=var, bg=PANEL, fg=TEXT,
                               selectcolor=ACCENT, activebackground=PANEL,
                               font=self.fLbl).grid(row=r, column=c+1, sticky="w", pady=2)
            elif opts.get("type") == "combo":
                var = tk.StringVar(value=default)
                ttk.Combobox(inner, textvariable=var, values=opts["values"],
                             width=18, font=self.fMono,
                             state="readonly").grid(row=r, column=c+1, sticky="ew", pady=2, padx=(0,12))
            else:
                var = tk.StringVar(value=str(default))
                e = tk.Entry(inner, textvariable=var, width=10, bg=ENTRY_BG, fg=TEXT,
                             insertbackground=TEXT, relief="flat", font=self.fMono,
                             highlightthickness=1, highlightbackground=BORDER,
                             highlightcolor=ACCENT)
                e.grid(row=r, column=c+1, sticky="ew", pady=2)
                u = opts.get("unit","")
                if u:
                    tk.Label(inner, text=u, bg=PANEL, fg=SUBTEXT,
                             font=self.fSmall).grid(row=r, column=c+2, sticky="w", padx=(2,12))
            self.vars[key] = var
        inner.columnconfigure(1, weight=1)
        inner.columnconfigure(4, weight=1)

    # ── field definitions ─────────────────────────────────────────────────────
    def _geom_fields(self):
        return [
            ("num_bays",        "Bays",                5,      {"unit":""}),
            ("bay_length",      "Bay length",           6.0,    {"unit":"ft"}),
            ("rail_cantilever", "Rail cantilever",      1.5,    {"unit":"ft"}),
            ("tilt_deg",        "Tilt angle",           15.0,   {"unit":"°"}),
            ("post_spacing_x",  "Post spacing N-S",     5.0,    {"unit":"ft"}),
            ("rafter_horiz",    "Rafter horiz span",    15.0,   {"unit":"ft"}),
            ("front_post_ht",   "South post ht",        2.5,    {"unit":"ft"}),
            ("panel_width",     "Panel width",          3.72,   {"unit":"ft"}),
            ("braces",          "Include bracing",      True,   {"type":"check"}),
        ]

    def _sec_fields(self):
        return [
            ("sec_post",   "Post section",   "W6X20",    {"unit":""}),
            ("sec_rafter", "Rafter section", "W8X24",    {"unit":""}),
            ("sec_rail",   "Rail section",   "C4X7.25",  {"unit":""}),
            ("sec_brace",  "Brace section",  "L2X2X0.25",{"unit":""}),
        ]

    def _load_fields(self):
        return [
            ("dead_ksf", "Panel DL", 0.0025, {"unit":"ksf"}),
            ("wind_ksf", "Wind",     0.0167, {"unit":"ksf"}),
            ("snow_ksf", "Snow",     0.0104, {"unit":"ksf"}),
        ]

    def _out_fields(self):
        dd = os.path.join(os.path.expanduser("~"), "Documents", "STAAD_Models")
        return [
            ("output_dir",  "Output folder", dd,                  {}),
            ("model_name",  "Model name",    "SolarGroundMount",  {}),
        ]

    # ── schematic canvas ──────────────────────────────────────────────────────
    def _build_schematic(self, parent):
        card = tk.Frame(parent, bg=PANEL)
        card.pack(fill="both", expand=True, pady=(0,6))
        tb = tk.Frame(card, bg=BORDER, height=26); tb.pack(fill="x"); tb.pack_propagate(False)
        tk.Label(tb, text="  SIDE ELEVATION  (N-S plane, 1 frame)",
                 bg=BORDER, fg=ACCENT2, font=self.fH2).pack(side="left", pady=4)
        self.canvas = tk.Canvas(card, bg="#0a0c12", bd=0, highlightthickness=0, height=210)
        self.canvas.pack(fill="both", expand=True, padx=6, pady=6)
        self.canvas.bind("<Configure>", lambda e: self._draw_schematic())
        self._draw_schematic()

    def _draw_schematic(self):
        cv = self.canvas
        cv.delete("all")
        W = cv.winfo_width(); H = cv.winfo_height()
        if W < 20 or H < 20: return

        def v(k, d):
            try: return float(self.vars[k].get())
            except: return d

        tilt    = math.radians(v("tilt_deg", 15))
        Hf      = v("front_post_ht", 2.5)
        Xsp     = v("post_spacing_x", 5.0)
        Rh      = v("rafter_horiz", 15.0)
        PW      = v("panel_width", 3.72)
        do_brace= bool(self.vars.get("braces") and self.vars["braces"].get())

        Hr      = Hf + Xsp * math.tan(tilt)
        slope   = (Hr - Hf) / Xsp
        rcant   = (Rh - Xsp) / 2.0
        rft_sx  = -rcant;        rft_sy = Hf - rcant * slope
        rft_nx  = Xsp + rcant;   rft_ny = Hr + rcant * slope

        # 4 rails equally spaced along full rafter
        full_len = math.sqrt(Rh**2 + (rft_ny - rft_sy)**2)
        sp = full_len / 5.0
        def rpt(i):
            s = i * sp
            ratio = s / full_len
            return rft_sx + ratio*(rft_nx-rft_sx), rft_sy + ratio*(rft_ny-rft_sy)

        r1b = rpt(1); r1t = rpt(2); r2b = rpt(3); r2t = rpt(4)

        # Fit to canvas
        all_x = [rft_sx, 0, Xsp, rft_nx]; all_y = [0, rft_sy, rft_ny, Hr]
        min_x = min(all_x); max_x = max(all_x)
        min_y = 0;          max_y = max(all_y) + 0.3
        mg = 44
        sc = min((W - 2*mg) / (max_x - min_x + 0.01),
                 (H - 2*mg) / (max_y - min_y + 0.01))

        def px(x, y):
            return mg + (x - min_x) * sc, H - mg - (y - min_y) * sc

        # Ground
        cv.create_line(mg - 8, H - mg, W - mg + 8, H - mg,
                       fill="#2a3040", width=1, dash=(4, 4))

        # Posts
        cv.create_line(*px(0, 0), *px(0, Hf), fill="#4a6fa0", width=3)
        cv.create_line(*px(Xsp, 0), *px(Xsp, Hr), fill="#4a6fa0", width=3)

        # Rafter (full, with cantilevers)
        cv.create_line(*px(rft_sx, rft_sy), *px(0, Hf),
                       fill=ACCENT, width=1, dash=(4, 3))           # S cantilever
        cv.create_line(*px(0, Hf), *px(Xsp, Hr),
                       fill=ACCENT, width=2)                         # main span
        cv.create_line(*px(Xsp, Hr), *px(rft_nx, rft_ny),
                       fill=ACCENT, width=1, dash=(4, 3))            # N cantilever

        # Rail dots
        for (rx, ry), clr in [(r1b, OK_GRN),(r1t, OK_GRN),(r2b, ACCENT2),(r2t, ACCENT2)]:
            cx2, cy2 = px(rx, ry)
            cv.create_oval(cx2-5, cy2-5, cx2+5, cy2+5, fill=clr, outline="")

        # Brace
        if do_brace:
            bs_y = Hf - 0.5; bn_y = 0.5
            cv.create_line(*px(Xsp, bn_y), *px(0, bs_y),
                           fill=ACCENT2, width=1, dash=(3, 2))

        # Labels
        mx, my = px(Xsp / 2, (Hf + Hr) / 2)
        cv.create_text(mx, my - 10, text=f"{v('tilt_deg',15):.0f}°",
                       fill=ACCENT, font=self.fBadge)
        cv.create_text(*px(-0.15, Hf / 2),
                       text=f"{Hf:.1f}ft", fill="#4a6fa0", font=self.fBadge)
        cv.create_text(*px(Xsp + 0.3, Hr / 2),
                       text=f"{Hr:.1f}ft", fill="#4a6fa0", font=self.fBadge)
        cv.create_text(*px(rft_sx - 0.1, rft_sy),
                       text=f"←{rcant:.1f}ft", fill=ACCENT, font=self.fSmall, anchor="e")
        cv.create_text(*px(rft_nx + 0.1, rft_ny),
                       text=f"{rcant:.1f}ft→", fill=ACCENT, font=self.fSmall, anchor="w")

        # Compass
        cv.create_text(mg + (0 - min_x) * sc, H - mg + 14,
                       text="S", fill=SUBTEXT, font=self.fBadge)
        cv.create_text(mg + (Xsp - min_x) * sc, H - mg + 14,
                       text="N", fill=SUBTEXT, font=self.fBadge)

        # Legend
        items = [(OK_GRN,"Row-1 rails"),(ACCENT2,"Row-2 rails / brace"),
                 (ACCENT,"Rafter"),("#4a6fa0","Posts")]
        for i, (col, lbl) in enumerate(items):
            cv.create_rectangle(W - 118, 10 + i*16, W - 108, 20 + i*16, fill=col, outline="")
            cv.create_text(W - 104, 15 + i*16, text=lbl, fill=SUBTEXT,
                           font=self.fSmall, anchor="w")

    # ── log ───────────────────────────────────────────────────────────────────
    def _build_log(self, parent):
        card = tk.Frame(parent, bg=PANEL)
        card.pack(fill="x", pady=(0,6))
        tb = tk.Frame(card, bg=BORDER, height=26); tb.pack(fill="x"); tb.pack_propagate(False)
        tk.Label(tb, text="  OUTPUT LOG", bg=BORDER, fg=ACCENT2,
                 font=self.fH2).pack(side="left", pady=4)
        self.log = tk.Text(card, height=8, bg="#080a10", fg=OK_GRN,
                           font=self.fMono, relief="flat", state="disabled",
                           wrap="word", padx=8, pady=6)
        self.log.pack(fill="x", padx=6, pady=6)

    def _log(self, msg, color=None):
        self.log.config(state="normal")
        tag = f"t{id(msg)}"
        self.log.tag_config(tag, foreground=color or OK_GRN)
        self.log.insert("end", msg + "\n", tag)
        self.log.see("end")
        self.log.config(state="disabled")

    def _log_clear(self):
        self.log.config(state="normal"); self.log.delete("1.0", "end")
        self.log.config(state="disabled")

    # ── buttons ───────────────────────────────────────────────────────────────
    def _build_buttons(self, parent):
        bf = tk.Frame(parent, bg=BG)
        bf.pack(fill="x", pady=(0,10))
        st = ttk.Style(self); st.theme_use("clam")
        st.configure("Gen.TButton",  background=ACCENT,  foreground="#fff",
                     font=("Consolas",10,"bold"), relief="flat", padding=10)
        st.map("Gen.TButton", background=[("active","#5aa0ff")])
        st.configure("Aux.TButton",  background=BORDER,  foreground=TEXT,
                     font=("Consolas",9), relief="flat", padding=8)
        st.map("Aux.TButton", background=[("active","#353850")])
        ttk.Button(bf, text="▶  GENERATE .STD", style="Gen.TButton",
                   command=self._generate).pack(side="left", padx=(0,8))
        ttk.Button(bf, text="⟳  Schematic",     style="Aux.TButton",
                   command=self._draw_schematic).pack(side="left", padx=(0,8))
        ttk.Button(bf, text="⊞  Browse…",       style="Aux.TButton",
                   command=self._browse).pack(side="left")

    def _browse(self):
        d = filedialog.askdirectory(title="Select output folder")
        if d: self.vars["output_dir"].set(d)

    # ── param extraction ──────────────────────────────────────────────────────
    def _get_params(self):
        p = {}
        floats = {"bay_length","rail_cantilever","tilt_deg","post_spacing_x",
                  "rafter_horiz","front_post_ht","panel_width",
                  "dead_ksf","wind_ksf","snow_ksf"}
        ints   = {"num_bays"}
        bools  = {"braces"}
        for k, var in self.vars.items():
            raw = var.get()
            if k in bools:   p[k] = bool(raw)
            elif k in ints:  p[k] = int(raw)
            elif k in floats:p[k] = float(raw)
            else:            p[k] = raw
        return p

    # ── generate ─────────────────────────────────────────────────────────────
    def _generate(self):
        self._log_clear()
        try:
            p = self._get_params()
        except ValueError as e:
            self._log(f"✗ Input error: {e}", ERR_RED); return

        errs = []
        if p["num_bays"] < 1:         errs.append("Bays must be ≥ 1")
        if p["bay_length"] <= 0:      errs.append("Bay length must be > 0")
        if not (0 < p["tilt_deg"] < 90): errs.append("Tilt must be 1–89°")
        if p["rafter_horiz"] <= p["post_spacing_x"]:
            errs.append("Rafter horiz span must be > Post spacing N-S")

        if errs:
            for e in errs: self._log(f"✗ {e}", ERR_RED)
            return

        tilt = math.radians(p["tilt_deg"])
        Hr   = p["front_post_ht"] + p["post_spacing_x"] * math.tan(tilt)
        rcant= (p["rafter_horiz"] - p["post_spacing_x"]) / 2.0

        self._log("► Geometry")
        self._log(f"  South post ht      : {p['front_post_ht']:.3f} ft")
        self._log(f"  North post ht      : {Hr:.4f} ft  (auto)")
        self._log(f"  Rafter horiz span  : {p['rafter_horiz']:.3f} ft")
        self._log(f"  Rafter cant (each) : {rcant:.4f} ft  = {rcant*12:.2f} in")
        self._log(f"  Rail Z span        : {p['num_bays']*p['bay_length'] + 2*p['rail_cantilever']:.3f} ft")

        try:
            std_text, info = build_std(p)
        except Exception as e:
            self._log(f"✗ Build error: {e}", ERR_RED); return

        self._log("► Model")
        self._log(f"  Nodes        : {info['total_nodes']}")
        self._log(f"  Members      : {info['total_members']}")
        self._log(f"    S posts    : {info['south_posts']}")
        self._log(f"    N posts    : {info['north_posts']}")
        self._log(f"    Rafters    : {info['rafters']}")
        self._log(f"    Rails (×4) : {info['rails']}")
        self._log(f"    Braces     : {info['braces']}")

        out_dir  = p["output_dir"].strip()
        filename = p["model_name"].strip() + ".std"

        def try_save(d):
            os.makedirs(d, exist_ok=True)
            fp = os.path.join(d, filename)
            with open(fp, "w") as f: f.write(std_text)
            return fp

        filepath = None
        try:
            filepath = try_save(out_dir)
            self._log(f"► Saved: {filepath}", ACCENT)
        except PermissionError:
            fb = os.path.join(os.path.expanduser("~"), "Desktop", "STAAD_Models")
            self._log(f"✗ Permission denied: {out_dir}", ERR_RED)
            self._log(f"  Retrying → {fb}", ACCENT2)
            try:
                filepath = try_save(fb)
                self.vars["output_dir"].set(fb)
                self._log(f"► Saved: {filepath}", ACCENT)
            except Exception as e2:
                self._log(f"✗ Fallback failed: {e2}", ERR_RED)
                self._log("  Use Browse… to pick a writable folder.", SUBTEXT)
                return
        except Exception as e:
            self._log(f"✗ Save error: {e}", ERR_RED)
            self._log("  Use Browse… to pick a writable folder.", SUBTEXT)
            return

        # Try COM
        try:
            import win32com.client
            staad = win32com.client.Dispatch("StaadPro.OpenSTAAD")
            staad.OpenSTAADFile(filepath)
            self._log("► Opened in STAAD.Pro ✓", OK_GRN)
        except ImportError:
            self._log("  (pywin32 not found – open file manually)", SUBTEXT)
        except Exception as e:
            self._log(f"  (COM skipped: {e})", SUBTEXT)

        self._draw_schematic()
        messagebox.showinfo("Done", f"Model written to:\n{filepath}")


# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = SolarFrameBuilder()
    app.mainloop()