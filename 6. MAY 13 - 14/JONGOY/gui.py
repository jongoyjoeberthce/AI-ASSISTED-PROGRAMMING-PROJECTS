"""
gui.py
======
NSCP RC Column Designer — Graphical User Interface
Built with Tkinter + Matplotlib (embedded plot).

Layout:
  ┌─────────────────────────────────────────────────────────┐
  │  Header bar (title + logo area)                         │
  ├──────────────────┬──────────────────────────────────────┤
  │  LEFT PANEL      │  RIGHT PANEL                         │
  │  Inputs          │  Results + Interaction Diagram        │
  └──────────────────┴──────────────────────────────────────┘
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, font as tkfont
import math
import numpy as np

# Matplotlib embedded in Tkinter
import matplotlib
matplotlib.use("TkAgg")
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
import matplotlib.patches as mpatches

from design_engine import design_column, STANDARD_BARS


# ---------------------------------------------------------------------------
# Color palette (engineering-professional dark-accent theme)
# ---------------------------------------------------------------------------
CLR_BG       = "#F4F6F8"      # Main background
CLR_PANEL    = "#FFFFFF"      # Panel background
CLR_HEADER   = "#1A3C5E"      # Deep navy header
CLR_ACCENT   = "#2471A3"      # Primary accent blue
CLR_ACCENT2  = "#1ABC9C"      # Teal for PASS
CLR_DANGER   = "#E74C3C"      # Red for FAIL
CLR_WARN     = "#F39C12"      # Amber for warnings
CLR_TEXT     = "#2C3E50"      # Main text
CLR_MUTED    = "#7F8C8D"      # Secondary text
CLR_BORDER   = "#D5D8DC"      # Subtle borders
CLR_INPUT_BG = "#FDFEFE"      # Input field background


class RCColumnDesignerApp(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("NSCP RC Column Designer — KIRAS Engineering")
        self.geometry("1400x900")
        self.minsize(1100, 700)
        self.configure(bg=CLR_BG)

        # Store last results for export
        self._last_results = None
        self._last_params  = None

        self._build_fonts()
        self._build_layout()
        self._populate_defaults()

    # ------------------------------------------------------------------
    # Font setup
    # ------------------------------------------------------------------
    def _build_fonts(self):
        self.f_title  = tkfont.Font(family="Helvetica", size=16, weight="bold")
        self.f_head   = tkfont.Font(family="Helvetica", size=11, weight="bold")
        self.f_label  = tkfont.Font(family="Helvetica", size=9)
        self.f_entry  = tkfont.Font(family="Courier",   size=9)
        self.f_result = tkfont.Font(family="Courier",   size=9)
        self.f_status = tkfont.Font(family="Helvetica", size=12, weight="bold")

    # ------------------------------------------------------------------
    # Top-level layout
    # ------------------------------------------------------------------
    def _build_layout(self):
        # --- Header ---
        header = tk.Frame(self, bg=CLR_HEADER, height=60)
        header.pack(side=tk.TOP, fill=tk.X)
        header.pack_propagate(False)

        tk.Label(header, text="⚙  NSCP RC Column Designer",
                 font=self.f_title, bg=CLR_HEADER, fg="white",
                 padx=20).pack(side=tk.LEFT, pady=12)

        tk.Label(header,
                 text="NSCP 2015  |  Strength Design  |  Biaxial Bending",
                 font=self.f_label, bg=CLR_HEADER, fg="#AED6F1").pack(
                     side=tk.RIGHT, padx=20)

        # --- Main area ---
        main = tk.PanedWindow(self, orient=tk.HORIZONTAL,
                              bg=CLR_BG, sashwidth=6, sashrelief=tk.FLAT)
        main.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        # Left panel — inputs
        left_outer = tk.Frame(main, bg=CLR_BG)
        main.add(left_outer, minsize=340, width=400)
        self._build_input_panel(left_outer)

        # Right panel — results
        right_outer = tk.Frame(main, bg=CLR_BG)
        main.add(right_outer, minsize=600)
        self._build_results_panel(right_outer)

    # ------------------------------------------------------------------
    # Input panel
    # ------------------------------------------------------------------
    def _build_input_panel(self, parent):
        canvas = tk.Canvas(parent, bg=CLR_BG, highlightthickness=0)
        scroll = ttk.Scrollbar(parent, orient=tk.VERTICAL, command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        frame = tk.Frame(canvas, bg=CLR_BG)
        canvas.create_window((0, 0), window=frame, anchor="nw")
        frame.bind("<Configure>",
                   lambda e: canvas.configure(
                       scrollregion=canvas.bbox("all")))
        # Mouse-wheel scroll
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        self.inputs = {}   # dict of all input StringVars

        def section(title, parent_frame):
            f = tk.LabelFrame(parent_frame, text=f"  {title}  ",
                              font=self.f_head, bg=CLR_PANEL,
                              fg=CLR_ACCENT, relief=tk.FLAT,
                              bd=1, highlightthickness=1,
                              highlightbackground=CLR_BORDER)
            f.pack(fill=tk.X, padx=6, pady=(6, 0))
            return f

        def row(parent_frame, label, key, default, unit="", width=12, choices=None):
            r = tk.Frame(parent_frame, bg=CLR_PANEL)
            r.pack(fill=tk.X, padx=10, pady=3)
            tk.Label(r, text=label, font=self.f_label, bg=CLR_PANEL,
                     fg=CLR_TEXT, width=22, anchor="w").pack(side=tk.LEFT)
            var = tk.StringVar(value=default)
            self.inputs[key] = var
            if choices:
                w = ttk.Combobox(r, textvariable=var, values=choices,
                                  font=self.f_entry, width=width, state="readonly")
            else:
                w = tk.Entry(r, textvariable=var, font=self.f_entry,
                              width=width, bg=CLR_INPUT_BG, relief=tk.FLAT,
                              bd=1, highlightthickness=1,
                              highlightcolor=CLR_ACCENT,
                              highlightbackground=CLR_BORDER)
            w.pack(side=tk.LEFT, padx=(4, 0))
            if unit:
                tk.Label(r, text=unit, font=self.f_label,
                          bg=CLR_PANEL, fg=CLR_MUTED, width=6).pack(side=tk.LEFT)

        # --- Section geometry ---
        s1 = section("Section Geometry", frame)
        row(s1, "Section Type",       "section_type",  "Rectangular",
            choices=["Rectangular", "Circular"])
        row(s1, "Width  b",            "b",    "400",  "mm")
        row(s1, "Depth  h",            "h",    "500",  "mm")
        row(s1, "Clear Cover",         "cover","40",   "mm")
        row(s1, "Column Type",         "column_type","Tied",
            choices=["Tied", "Spiral"])

        # --- Materials ---
        s2 = section("Material Properties", frame)
        row(s2, "f'c (concrete)",      "fc",   "28",   "MPa")
        row(s2, "fy (steel)",          "fy",   "420",  "MPa")

        # --- Loads ---
        s3 = section("Factored Loads", frame)
        row(s3, "Pu  (axial)",         "Pu",   "1500", "kN")
        row(s3, "Mux (about x-axis)",  "Mux",  "120",  "kN·m")
        row(s3, "Muy (about y-axis)",  "Muy",  "80",   "kN·m")

        # --- Reinforcement ---
        s4 = section("Reinforcement", frame)
        bar_choices = [b[0] for b in STANDARD_BARS]
        row(s4, "Main Bar Size",       "db_name","25mm",
            choices=bar_choices)
        row(s4, "Number of Bars",      "n_bars", "8",    "")

        # --- Slenderness ---
        s5 = section("Slenderness", frame)
        row(s5, "Unsupported Length lu", "lu", "3600", "mm")
        row(s5, "Eff. Length Factor k",  "k",  "1.0",  "")

        # --- Buttons ---
        btn_frame = tk.Frame(frame, bg=CLR_BG)
        btn_frame.pack(fill=tk.X, padx=6, pady=12)

        run_btn = tk.Button(btn_frame, text="▶  Run Design",
                            font=self.f_head, bg=CLR_ACCENT, fg="white",
                            activebackground="#1A5276", activeforeground="white",
                            relief=tk.FLAT, cursor="hand2", padx=16, pady=8,
                            command=self._run_design)
        run_btn.pack(fill=tk.X, pady=(0, 6))

        export_btn = tk.Button(btn_frame, text="⬇  Export Report (TXT)",
                               font=self.f_label, bg=CLR_MUTED, fg="white",
                               activebackground="#566573",
                               relief=tk.FLAT, cursor="hand2", padx=10, pady=6,
                               command=self._export_txt)
        export_btn.pack(fill=tk.X)

    # ------------------------------------------------------------------
    # Results panel
    # ------------------------------------------------------------------
    def _build_results_panel(self, parent):
        notebook = ttk.Notebook(parent)
        notebook.pack(fill=tk.BOTH, expand=True)

        # Tab 1: Interaction diagram + status
        tab_diagram = tk.Frame(notebook, bg=CLR_BG)
        notebook.add(tab_diagram, text="  Interaction Diagram  ")

        # Tab 2: Detailed results text
        tab_detail = tk.Frame(notebook, bg=CLR_BG)
        notebook.add(tab_detail, text="  Design Summary  ")

        # --- Diagram tab ---
        # Status strip
        self.status_frame = tk.Frame(tab_diagram, bg=CLR_PANEL, height=48)
        self.status_frame.pack(fill=tk.X, padx=6, pady=(6, 0))
        self.status_frame.pack_propagate(False)
        self.status_lbl = tk.Label(self.status_frame,
                                    text="Run design to see results",
                                    font=self.f_status, bg=CLR_PANEL, fg=CLR_MUTED)
        self.status_lbl.pack(expand=True)

        # KPI strip
        self.kpi_frame = tk.Frame(tab_diagram, bg=CLR_BG)
        self.kpi_frame.pack(fill=tk.X, padx=6, pady=(4, 0))
        self._build_kpi_strip()

        # Matplotlib figure
        plot_frame = tk.Frame(tab_diagram, bg=CLR_BG)
        plot_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

        self.fig = Figure(figsize=(8, 5.5), dpi=100, facecolor=CLR_PANEL)
        self.ax  = self.fig.add_subplot(111)
        self._style_axes()

        self.canvas = FigureCanvasTkAgg(self.fig, master=plot_frame)
        self.canvas.draw()
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        toolbar_frame = tk.Frame(plot_frame, bg=CLR_BG)
        toolbar_frame.pack(fill=tk.X)
        NavigationToolbar2Tk(self.canvas, toolbar_frame)

        # --- Detail tab ---
        detail_frame = tk.Frame(tab_detail, bg=CLR_PANEL)
        detail_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)

        detail_scroll = ttk.Scrollbar(detail_frame)
        detail_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.detail_text = tk.Text(detail_frame, font=self.f_result,
                                    bg=CLR_PANEL, fg=CLR_TEXT,
                                    relief=tk.FLAT, bd=0,
                                    wrap=tk.NONE,
                                    yscrollcommand=detail_scroll.set,
                                    state=tk.DISABLED)
        self.detail_text.pack(fill=tk.BOTH, expand=True)
        detail_scroll.config(command=self.detail_text.yview)

        # Tags for colored text
        self.detail_text.tag_config("pass",    foreground=CLR_ACCENT2, font=self.f_head)
        self.detail_text.tag_config("fail",    foreground=CLR_DANGER,  font=self.f_head)
        self.detail_text.tag_config("heading", foreground=CLR_ACCENT,  font=self.f_head)
        self.detail_text.tag_config("warn",    foreground=CLR_WARN)
        self.detail_text.tag_config("mono",    font=self.f_result)

    # ------------------------------------------------------------------
    # KPI cards strip
    # ------------------------------------------------------------------
    def _build_kpi_strip(self):
        self.kpi_widgets = {}
        kpis = [
            ("φPn0", "Pure Axial (kN)"),
            ("DCR",  "Biaxial DCR"),
            ("ρ%",   "Steel Ratio (%)"),
            ("φPni", "Biaxial Cap. (kN)"),
        ]
        for key, label in kpis:
            card = tk.Frame(self.kpi_frame, bg=CLR_PANEL,
                            relief=tk.FLAT, bd=0,
                            highlightthickness=1,
                            highlightbackground=CLR_BORDER)
            card.pack(side=tk.LEFT, padx=4, pady=2, fill=tk.Y, expand=True)
            tk.Label(card, text=label, font=self.f_label,
                      bg=CLR_PANEL, fg=CLR_MUTED).pack(pady=(6, 0))
            val_lbl = tk.Label(card, text="—", font=self.f_status,
                                bg=CLR_PANEL, fg=CLR_TEXT, padx=14)
            val_lbl.pack(pady=(0, 6))
            self.kpi_widgets[key] = val_lbl

    def _update_kpis(self, r: dict):
        s = r["summary"]
        dcr = s["DCR_biaxial"]
        dcr_clr = CLR_ACCENT2 if dcr <= 1.0 else CLR_DANGER
        self.kpi_widgets["φPn0"].config(text=f"{s['phi_Pn0_kN']:.1f}", fg=CLR_ACCENT)
        self.kpi_widgets["DCR"].config(text=f"{dcr:.3f}", fg=dcr_clr)
        self.kpi_widgets["ρ%"].config(text=f"{s['rho_pct']:.2f}%",
                                       fg=CLR_ACCENT2 if 1 <= s['rho_pct'] <= 8 else CLR_DANGER)
        self.kpi_widgets["φPni"].config(text=f"{s['phi_Pni_kN']:.1f}", fg=CLR_ACCENT)

    # ------------------------------------------------------------------
    # Axes styling
    # ------------------------------------------------------------------
    def _style_axes(self):
        ax = self.ax
        ax.set_facecolor(CLR_PANEL)
        self.fig.patch.set_facecolor(CLR_PANEL)
        for spine in ax.spines.values():
            spine.set_edgecolor(CLR_BORDER)
        ax.tick_params(colors=CLR_MUTED, labelsize=8)
        ax.set_xlabel("φMn  (kN·m)", color=CLR_TEXT, fontsize=9)
        ax.set_ylabel("φPn  (kN)",   color=CLR_TEXT, fontsize=9)
        ax.set_title("P–M Interaction Diagram", color=CLR_ACCENT, fontsize=10, pad=8)
        ax.grid(True, linestyle="--", linewidth=0.4, color=CLR_BORDER)

    # ------------------------------------------------------------------
    # Run design
    # ------------------------------------------------------------------
    def _run_design(self):
        try:
            params = self._collect_params()
        except ValueError as e:
            messagebox.showerror("Input Error", str(e))
            return

        try:
            results = design_column(params)
        except Exception as e:
            messagebox.showerror("Design Error", f"Calculation error:\n{e}")
            return

        self._last_results = results
        self._last_params  = params

        self._update_status(results)
        self._update_kpis(results)
        self._draw_diagram(results, params)
        self._update_detail_text(results, params)

    # ------------------------------------------------------------------
    # Collect and validate inputs
    # ------------------------------------------------------------------
    def _collect_params(self) -> dict:
        def fval(key, label, lo=None, hi=None):
            try:
                v = float(self.inputs[key].get())
            except ValueError:
                raise ValueError(f"'{label}' must be a number.")
            if lo is not None and v < lo:
                raise ValueError(f"'{label}' must be ≥ {lo}.")
            if hi is not None and v > hi:
                raise ValueError(f"'{label}' must be ≤ {hi}.")
            return v

        def ival(key, label, lo=None, hi=None):
            try:
                v = int(float(self.inputs[key].get()))
            except ValueError:
                raise ValueError(f"'{label}' must be an integer.")
            if lo is not None and v < lo:
                raise ValueError(f"'{label}' must be ≥ {lo}.")
            if hi is not None and v > hi:
                raise ValueError(f"'{label}' must be ≤ {hi}.")
            return v

        # Look up bar diameter from name
        db_name = self.inputs["db_name"].get()
        db_map  = {b[0]: b[1] for b in STANDARD_BARS}
        if db_name not in db_map:
            raise ValueError(f"Unknown bar size: {db_name}")
        db = db_map[db_name]

        return {
            "b":           fval("b",     "Width b",         100, 2000),
            "h":           fval("h",     "Depth h",         100, 2000),
            "cover":       fval("cover", "Clear cover",     20,  100),
            "fc":          fval("fc",    "f'c",             17,  100),
            "fy":          fval("fy",    "fy",              275, 700),
            "Pu":          fval("Pu",    "Pu",              0),
            "Mux":         fval("Mux",   "Mux",             0),
            "Muy":         fval("Muy",   "Muy",             0),
            "db":          db,
            "n_bars":      ival("n_bars","Number of bars",  4,   80),
            "column_type": self.inputs["column_type"].get().lower(),
            "section_type":self.inputs["section_type"].get().lower(),
            "lu":          fval("lu",    "Unsupported length lu", 100),
            "k":           fval("k",     "k factor",        0.5, 2.5),
        }

    # ------------------------------------------------------------------
    # Update status banner
    # ------------------------------------------------------------------
    def _update_status(self, r: dict):
        status = r["overall_status"]
        if status == "PASS":
            self.status_frame.config(bg=CLR_ACCENT2)
            self.status_lbl.config(text="✔  DESIGN PASSES — All NSCP checks satisfied",
                                   bg=CLR_ACCENT2, fg="white")
        else:
            self.status_frame.config(bg=CLR_DANGER)
            self.status_lbl.config(text="✘  DESIGN FAILS — Review flagged checks below",
                                   bg=CLR_DANGER, fg="white")

    # ------------------------------------------------------------------
    # Draw interaction diagram
    # ------------------------------------------------------------------
    def _draw_diagram(self, r: dict, params: dict):
        ax = self.ax
        ax.cla()
        self._style_axes()

        diag = r["diagram"]
        # Filter to positive moment range and sort by Mn
        phi_pn = np.array(diag["phiPn_kN"])
        phi_mn = np.array(diag["phiMn_kNm"])
        pn     = np.array(diag["Pn_kN"])
        mn     = np.array(diag["Mn_kNm"])

        # Sort by Mn for a clean curve
        idx_s  = np.argsort(phi_mn)
        phi_mn = phi_mn[idx_s]
        phi_pn = phi_pn[idx_s]
        idx_n  = np.argsort(mn)
        mn     = mn[idx_n]
        pn     = pn[idx_n]

        # Design curve (φ·Pn, φ·Mn)
        ax.plot(phi_mn, phi_pn, color=CLR_ACCENT, linewidth=2.0,
                label="Design envelope (φPn-φMn)", zorder=3)

        # Nominal curve (lighter, dashed)
        ax.plot(mn, pn, color=CLR_ACCENT, linewidth=1.0, linestyle="--",
                alpha=0.45, label="Nominal (Pn-Mn)", zorder=2)

        # Demand point
        Pu_kN  = r["summary"]["Pu_kN"]
        Mux_km = r["summary"]["Mux_kNm"]
        Muy_km = r["summary"]["Muy_kNm"]
        Mu_total = math.sqrt(Mux_km**2 + Muy_km**2)

        ax.scatter([Mux_km], [Pu_kN], color=CLR_DANGER,
                    s=80, zorder=5, label=f"Demand (Mux): Pu={Pu_kN:.0f}kN, Mux={Mux_km:.0f}kN·m")
        ax.scatter([Muy_km], [Pu_kN], color=CLR_WARN,
                    s=80, zorder=5, marker="s",
                    label=f"Demand (Muy): Pu={Pu_kN:.0f}kN, Muy={Muy_km:.0f}kN·m")

        # Eccentricity line
        if Pu_kN > 0:
            e_x = Mux_km / Pu_kN
            m_line = np.linspace(0, max(phi_mn) * 1.1, 100)
            p_line = m_line / e_x if e_x > 0 else np.zeros(100) + max(phi_pn)
            ax.plot(m_line, p_line, color=CLR_DANGER, linewidth=0.8,
                    linestyle=":", alpha=0.5, label="Eccentricity ray")

        # φPn0 horizontal line
        phi_pn0 = diag["phi_Pn0_kN"]
        ax.axhline(phi_pn0, color=CLR_MUTED, linewidth=0.8, linestyle="-.",
                    label=f"φPn0 = {phi_pn0:.0f} kN")

        # Pure tension (Pn = As·fy)
        As = r["section"]["Ast_mm2"]
        phi_Pt = -0.9 * As * float(params["fy"]) / 1000.0
        ax.axhline(phi_Pt, color="#A569BD", linewidth=0.8, linestyle="-.",
                    label=f"φPt = {phi_Pt:.0f} kN (tension)")

        ax.legend(fontsize=7, loc="upper right", framealpha=0.9)
        ax.set_title(
            f"P–M Interaction Diagram  |  {int(params['b'])}×{int(params['h'])} mm  "
            f"|  f'c={params['fc']}MPa  fy={params['fy']}MPa  "
            f"  {int(params['n_bars'])}–{self.inputs['db_name'].get()}",
            color=CLR_ACCENT, fontsize=9, pad=8)

        self.canvas.draw()

    # ------------------------------------------------------------------
    # Detail text
    # ------------------------------------------------------------------
    def _update_detail_text(self, r: dict, params: dict):
        txt = self.detail_text
        txt.config(state=tk.NORMAL)
        txt.delete("1.0", tk.END)

        def h(text):
            txt.insert(tk.END, f"\n{'═'*65}\n  {text}\n{'═'*65}\n", "heading")

        def line(label, value, tag="mono"):
            txt.insert(tk.END, f"  {label:<38} {value}\n", tag)

        def status_line(label, status, note=""):
            tag = "pass" if status == "PASS" else "fail"
            txt.insert(tk.END, f"  {label:<38} [{status}]  {note}\n", tag)

        # --- Header ---
        txt.insert(tk.END, "\n  NSCP 2015 RC COLUMN DESIGN REPORT\n", "heading")
        txt.insert(tk.END, f"  KIRAS Engineering Ltd.\n", "mono")
        txt.insert(tk.END, f"  {'─'*63}\n", "mono")

        # --- Section ---
        h("1. COLUMN SECTION & MATERIAL PROPERTIES")
        line("Section (b × h):", f"{params['b']} × {params['h']} mm")
        line("Column type:",     params['column_type'].capitalize())
        line("f'c:",             f"{params['fc']} MPa")
        line("fy:",              f"{params['fy']} MPa")
        line("Clear cover:",     f"{params['cover']} mm")
        line("Bar size / count:",f"{self.inputs['db_name'].get()} / {params['n_bars']} bars")
        line("Gross area Ag:",   f"{r['section']['Ag_mm2']:.0f} mm²")
        line("Steel area Ast:",  f"{r['section']['Ast_mm2']:.1f} mm²")

        # --- Rho check ---
        h("2. REINFORCEMENT RATIO  (NSCP 410.6.1.1)")
        rc = r["rho_check"]
        line("ρg provided:",     f"{rc['rho_pct']:.2f}%")
        line("Allowable range:", "1.00% – 8.00%")
        status_line("ρg check:", rc["status"], rc.get("note", ""))

        # --- Slenderness ---
        h("3. SLENDERNESS  (NSCP 410.10)")
        sl = r["slenderness"]
        line("klu / r:",         f"{sl['klu_r']:.2f}")
        line("Limit:",           f"{sl['limit']:.1f}")
        status_line("Slenderness:", "PASS" if not sl["is_slender"] else "WARN",
                    sl["note"])

        # --- Axial capacity ---
        h("4. PURE AXIAL CAPACITY  (NSCP 410.5)")
        line("φPn0:",           f"{r['summary']['phi_Pn0_kN']:.2f} kN")
        line("Pu:",             f"{r['summary']['Pu_kN']:.2f} kN")
        status_line("Axial check:",
                    "PASS" if r['summary']['Pu_kN'] <= r['summary']['phi_Pn0_kN'] else "FAIL")

        # --- Uniaxial checks ---
        h("5. UNIAXIAL BENDING CHECKS")
        ux = r["uniaxial_x"]
        line("φPnx (x-axis capacity):", f"{ux['phi_Pn_kN']:.2f} kN")
        line("ex:",                     f"{ux['ex_mm']:.1f} mm")
        line("DCR (x):",                f"{ux['DCR']:.4f}")
        status_line("Uniaxial x check:",ux["status"])

        uy = r["uniaxial_y"]
        line("φPny (y-axis capacity):", f"{uy['phi_Pn_kN']:.2f} kN")
        line("ey:",                     f"{uy['ey_mm']:.1f} mm")
        line("DCR (y):",                f"{uy['DCR']:.4f}")
        status_line("Uniaxial y check:",uy["status"])

        # --- Biaxial ---
        h("6. BIAXIAL BENDING  — Bresler Reciprocal Load Method")
        bx = r["biaxial"]
        line("φPnx:",           f"{r['summary']['phi_Pnx_kN']:.2f} kN")
        line("φPny:",           f"{r['summary']['phi_Pny_kN']:.2f} kN")
        line("φPn0:",           f"{r['summary']['phi_Pn0_kN']:.2f} kN")
        line("φPni (biaxial):", f"{bx['phi_Pni_kN']:.2f} kN")
        line("Pu:",             f"{r['summary']['Pu_kN']:.2f} kN")
        line("DCR = Pu/φPni:", f"{bx['DCR']:.4f}")
        status_line("Biaxial check:", bx["status"])

        # --- Lateral reinforcement ---
        h("7. LATERAL REINFORCEMENT  (NSCP 425.7)")
        lat = r["lateral"]
        if "db_tie_mm" in lat:
            line("Tie bar size:", f"{lat['db_tie_mm']:.0f} mm")
            line("s ≤ 16db:",    f"{lat['s_max_16db']:.0f} mm")
            line("s ≤ 48dt:",    f"{lat['s_max_48dt']:.0f} mm")
        else:
            line("Spiral bar:",     f"{lat['db_spiral_mm']:.0f} mm")
            line("ρs_min:",         f"{lat['rho_s_min']:.5f}")
            line("s_max:",          f"{lat['s_max_mm']:.1f} mm")
        txt.insert(tk.END, f"  {lat['note']}\n", "warn")

        # --- Bar suggestions ---
        h("8. BAR CONFIGURATION SUGGESTIONS")
        suggs = r["bar_suggestions"]
        if suggs:
            txt.insert(tk.END, f"  {'Size':<8} {'n':>4} {'As(mm²)':>10} {'Clear sp.':>12}\n", "heading")
            for s in suggs:
                txt.insert(tk.END,
                    f"  {s['bar_size']:<8} {s['n_bars']:>4} {s['As_mm2']:>10.0f} {s['clear_sp_mm']:>10.1f}mm\n",
                    "mono")

        # --- Overall ---
        h("9. OVERALL STATUS")
        ov = r["overall_status"]
        txt.insert(tk.END,
                    f"\n  {'  DESIGN PASSES  ' if ov=='PASS' else '  DESIGN FAILS  ':^50}\n\n",
                    "pass" if ov == "PASS" else "fail")

        txt.config(state=tk.DISABLED)

    # ------------------------------------------------------------------
    # Export to text file
    # ------------------------------------------------------------------
    def _export_txt(self):
        if self._last_results is None:
            messagebox.showinfo("Export", "Run design first.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt"), ("All", "*.*")],
            title="Save Design Report")
        if not path:
            return

        r = self._last_results
        p = self._last_params

        lines = [
            "=" * 70,
            "  NSCP 2015 RC COLUMN DESIGN REPORT — KIRAS Engineering Ltd.",
            "=" * 70,
            f"  Column: {p['b']}×{p['h']} mm  |  f'c={p['fc']}MPa  fy={p['fy']}MPa",
            f"  Bar: {self.inputs['db_name'].get()}  ×{p['n_bars']}  |  Cover={p['cover']}mm",
            f"  Loads: Pu={r['summary']['Pu_kN']}kN  Mux={r['summary']['Mux_kNm']}kN·m  Muy={r['summary']['Muy_kNm']}kN·m",
            "",
            "  REINFORCEMENT RATIO",
            f"    ρg = {r['rho_check']['rho_pct']:.2f}%  [{r['rho_check']['status']}]",
            "",
            "  SLENDERNESS",
            f"    klu/r = {r['slenderness']['klu_r']:.2f}  {'[SLENDER]' if r['slenderness']['is_slender'] else '[SHORT]'}",
            "",
            "  CAPACITY (Design — φ applied)",
            f"    φPn0 = {r['summary']['phi_Pn0_kN']:.2f} kN   (Pure axial)",
            f"    φPnx = {r['summary']['phi_Pnx_kN']:.2f} kN   (Uniaxial x)",
            f"    φPny = {r['summary']['phi_Pny_kN']:.2f} kN   (Uniaxial y)",
            f"    φPni = {r['summary']['phi_Pni_kN']:.2f} kN   (Biaxial — Bresler)",
            "",
            "  DEMAND/CAPACITY RATIOS",
            f"    DCR (x)      = {r['uniaxial_x']['DCR']:.4f}  [{r['uniaxial_x']['status']}]",
            f"    DCR (y)      = {r['uniaxial_y']['DCR']:.4f}  [{r['uniaxial_y']['status']}]",
            f"    DCR (biaxial)= {r['biaxial']['DCR']:.4f}  [{r['biaxial']['status']}]",
            "",
            f"  OVERALL STATUS: {r['overall_status']}",
            "=" * 70,
        ]

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        messagebox.showinfo("Export", f"Report saved to:\n{path}")

    # ------------------------------------------------------------------
    # Default values
    # ------------------------------------------------------------------
    def _populate_defaults(self):
        # Defaults already set via StringVar initialisation — nothing extra needed.
        pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
def main():
    app = RCColumnDesignerApp()
    app.mainloop()


if __name__ == "__main__":
    main()