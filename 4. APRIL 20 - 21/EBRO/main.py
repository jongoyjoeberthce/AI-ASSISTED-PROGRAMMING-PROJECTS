"""
STAAD.Pro 2025 Automation Tool
main.py - GUI + Workflow Controller
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog, scrolledtext
import threading
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from model import StructuralModel, Node, Member
from properties import SectionProperties, MaterialProperties
from loads import LoadManager
from export import STAADExporter


# ─── Theme Constants ──────────────────────────────────────────────────────────
BG_DARK    = "#0d1117"
BG_PANEL   = "#161b22"
BG_CARD    = "#1c2128"
BG_INPUT   = "#21262d"
ACCENT     = "#238636"
ACCENT_HOV = "#2ea043"
ACCENT2    = "#1f6feb"
BORDER     = "#30363d"
TEXT_PRI   = "#e6edf3"
TEXT_SEC   = "#8b949e"
TEXT_WARN  = "#d29922"
TEXT_ERR   = "#f85149"
TEXT_OK    = "#3fb950"
FONT_HEAD  = ("Consolas", 14, "bold")
FONT_SUB   = ("Consolas", 11, "bold")
FONT_BODY  = ("Consolas", 10)
FONT_SMALL = ("Consolas", 9)


class StyledButton(tk.Button):
    def __init__(self, parent, text, command=None, style="primary", **kwargs):
        colors = {
            "primary": (ACCENT,    ACCENT_HOV,  TEXT_PRI),
            "secondary":(ACCENT2,  "#388bfd",   TEXT_PRI),
            "danger":  (TEXT_ERR,  "#ff6e6e",   TEXT_PRI),
            "neutral": (BG_INPUT,  BORDER,      TEXT_PRI),
        }
        bg, hov, fg = colors.get(style, colors["primary"])
        super().__init__(
            parent, text=text, command=command,
            bg=bg, fg=fg, activebackground=hov, activeforeground=fg,
            relief="flat", bd=0, padx=14, pady=7,
            font=FONT_BODY, cursor="hand2", **kwargs
        )
        self.default_bg = bg
        self.hover_bg   = hov
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self.default_bg))


class LabeledEntry(tk.Frame):
    def __init__(self, parent, label, default="", width=12, **kwargs):
        super().__init__(parent, bg=BG_CARD, **kwargs)
        tk.Label(self, text=label, bg=BG_CARD, fg=TEXT_SEC,
                 font=FONT_SMALL).pack(side="left", padx=(0, 6))
        self.var = tk.StringVar(value=default)
        tk.Entry(self, textvariable=self.var, width=width,
                 bg=BG_INPUT, fg=TEXT_PRI, insertbackground=TEXT_PRI,
                 relief="flat", bd=4, font=FONT_BODY).pack(side="left")

    def get(self):
        return self.var.get().strip()


class SectionFrame(tk.LabelFrame):
    def __init__(self, parent, title, **kwargs):
        super().__init__(
            parent, text=f"  {title}  ",
            bg=BG_CARD, fg=ACCENT2,
            font=FONT_SUB, relief="flat",
            bd=1, highlightbackground=BORDER,
            highlightthickness=1,
            **kwargs
        )


class MainApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STAAD.Pro 2025 – Structural Automation Tool")
        self.geometry("1180x820")
        self.minsize(960, 700)
        self.configure(bg=BG_DARK)
        self.resizable(True, True)

        # Domain objects
        self.model      = StructuralModel()
        self.sections   = SectionProperties()
        self.materials  = MaterialProperties()
        self.loads      = LoadManager()
        self.exporter   = STAADExporter()

        self._build_ui()
        self.log("✔ Application started. Configure your model and click Export.")

    # ──────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        # ── Header ──
        hdr = tk.Frame(self, bg=BG_PANEL, height=54)
        hdr.pack(fill="x", side="top")
        hdr.pack_propagate(False)
        tk.Label(hdr, text="⬡  STAAD.Pro 2025  Automation", bg=BG_PANEL,
                 fg=TEXT_PRI, font=("Consolas", 15, "bold")).pack(side="left", padx=18, pady=12)
        tk.Label(hdr, text="OpenSTAADPy Interface", bg=BG_PANEL,
                 fg=TEXT_SEC, font=FONT_SMALL).pack(side="right", padx=18)

        # ── Main paned split ──
        paned = tk.PanedWindow(self, orient="horizontal",
                               bg=BG_DARK, sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        left  = tk.Frame(paned, bg=BG_DARK)
        right = tk.Frame(paned, bg=BG_DARK, width=340)
        paned.add(left,  minsize=580)
        paned.add(right, minsize=300)

        self._build_left(left)
        self._build_right(right)

    def _build_left(self, parent):
        nb = ttk.Notebook(parent)
        nb.pack(fill="both", expand=True)

        style = ttk.Style()
        style.theme_use("default")
        style.configure("TNotebook",          background=BG_DARK,  borderwidth=0)
        style.configure("TNotebook.Tab",      background=BG_PANEL, foreground=TEXT_SEC,
                        font=FONT_BODY,       padding=[12, 6])
        style.map("TNotebook.Tab",
                  background=[("selected", BG_CARD)],
                  foreground=[("selected", ACCENT2)])

        tabs = [
            ("🟢  Model",       self._tab_model),
            ("📐  Sections",    self._tab_sections),
            ("🧱  Materials",   self._tab_materials),
            ("🏢  Slabs",       self._tab_slabs),
            ("📊  Stiffness",   self._tab_stiffness),
            ("⚖  Loads",       self._tab_loads),
        ]
        for label, builder in tabs:
            frame = tk.Frame(nb, bg=BG_CARD)
            nb.add(frame, text=label)
            builder(frame)

    def _build_right(self, parent):
        # Export controls
        exp = SectionFrame(parent, "🔄  Export to STAAD.Pro")
        exp.pack(fill="x", padx=6, pady=(0, 8))

        tk.Label(exp, text="Output Directory:", bg=BG_CARD,
                 fg=TEXT_SEC, font=FONT_SMALL).pack(anchor="w", padx=10, pady=(8, 2))
        dir_row = tk.Frame(exp, bg=BG_CARD)
        dir_row.pack(fill="x", padx=10, pady=(0, 8))
        self.dir_var = tk.StringVar(value=os.path.expanduser("~/Documents"))
        tk.Entry(dir_row, textvariable=self.dir_var, bg=BG_INPUT,
                 fg=TEXT_PRI, insertbackground=TEXT_PRI, relief="flat",
                 bd=4, font=FONT_SMALL, width=22).pack(side="left", fill="x", expand=True)
        StyledButton(dir_row, "Browse", self._browse_dir,
                     style="neutral").pack(side="right", padx=(6, 0))

        tk.Label(exp, text="Filename (.std):", bg=BG_CARD,
                 fg=TEXT_SEC, font=FONT_SMALL).pack(anchor="w", padx=10, pady=(0, 2))
        self.fname_var = tk.StringVar(value="my_structure")
        tk.Entry(exp, textvariable=self.fname_var, bg=BG_INPUT,
                 fg=TEXT_PRI, insertbackground=TEXT_PRI, relief="flat",
                 bd=4, font=FONT_BODY).pack(fill="x", padx=10, pady=(0, 10))

        StyledButton(exp, "▶  Export to STAAD.Pro",
                     self._run_export, style="primary").pack(fill="x", padx=10, pady=(0, 6))
        StyledButton(exp, "🔎  Validate Model",
                     self._validate_model, style="secondary").pack(fill="x", padx=10, pady=(0, 10))

        # Model summary
        sum_f = SectionFrame(parent, "📋  Model Summary")
        sum_f.pack(fill="x", padx=6, pady=(0, 8))
        self.summary_lbl = tk.Label(sum_f, text="No model data yet.",
                                    bg=BG_CARD, fg=TEXT_SEC, font=FONT_SMALL,
                                    justify="left", anchor="w")
        self.summary_lbl.pack(fill="x", padx=10, pady=8)

        # Console log
        log_f = SectionFrame(parent, "📟  Console Log")
        log_f.pack(fill="both", expand=True, padx=6)
        self.console = scrolledtext.ScrolledText(
            log_f, bg="#010409", fg=TEXT_OK,
            insertbackground=TEXT_OK, font=("Consolas", 9),
            relief="flat", bd=0, wrap="word", state="disabled"
        )
        self.console.pack(fill="both", expand=True, padx=6, pady=6)
        self.console.tag_config("err",  foreground=TEXT_ERR)
        self.console.tag_config("warn", foreground=TEXT_WARN)
        self.console.tag_config("ok",   foreground=TEXT_OK)
        self.console.tag_config("info", foreground=ACCENT2)

        StyledButton(parent, "Clear Log", self._clear_log,
                     style="neutral").pack(padx=6, pady=(4, 6), anchor="e")

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Model
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_model(self, parent):
        pad = dict(padx=14, pady=8)

        # Mode selector
        mode_f = SectionFrame(parent, "Modeling Mode")
        mode_f.pack(fill="x", **pad)
        self.model_mode = tk.StringVar(value="manual")
        for val, txt in [("manual", "Connect-the-Dots (Manual Input)"),
                         ("grid",   "Grid/Node Generator (Auto)")]:
            tk.Radiobutton(mode_f, text=txt, variable=self.model_mode,
                           value=val, bg=BG_CARD, fg=TEXT_PRI,
                           selectcolor=BG_INPUT, activebackground=BG_CARD,
                           font=FONT_BODY, command=self._toggle_model_mode
                           ).pack(anchor="w", padx=12, pady=3)

        # Manual node input
        self.manual_frame = SectionFrame(parent, "Manual Node Input")
        self.manual_frame.pack(fill="x", **pad)

        row1 = tk.Frame(self.manual_frame, bg=BG_CARD)
        row1.pack(fill="x", padx=10, pady=6)
        self.mn_id  = LabeledEntry(row1, "Node ID:", "1", width=6)
        self.mn_id.pack(side="left", padx=(0, 10))
        self.mn_x   = LabeledEntry(row1, "X (m):", "0.0", width=8)
        self.mn_x.pack(side="left", padx=(0, 10))
        self.mn_y   = LabeledEntry(row1, "Y (m):", "0.0", width=8)
        self.mn_y.pack(side="left", padx=(0, 10))
        self.mn_z   = LabeledEntry(row1, "Z (m):", "0.0", width=8)
        self.mn_z.pack(side="left")

        row2 = tk.Frame(self.manual_frame, bg=BG_CARD)
        row2.pack(fill="x", padx=10, pady=(0, 8))
        StyledButton(row2, "+ Add Node",   self._add_node_manual,  style="primary").pack(side="left", padx=(0, 8))
        StyledButton(row2, "Add Member ↔", self._add_member_dialog, style="secondary").pack(side="left", padx=(0, 8))
        StyledButton(row2, "Clear All",    self._clear_model,       style="danger").pack(side="left")

        # Grid generator
        self.grid_frame = SectionFrame(parent, "Grid/Node Generator")
        self.grid_frame.pack(fill="x", **pad)

        gp = tk.Frame(self.grid_frame, bg=BG_CARD)
        gp.pack(fill="x", padx=10, pady=6)
        self.g_bays_x  = LabeledEntry(gp, "Bays X:",    "3",   width=5)
        self.g_bays_x.pack(side="left", padx=(0, 8))
        self.g_bays_z  = LabeledEntry(gp, "Bays Z:",    "3",   width=5)
        self.g_bays_z.pack(side="left", padx=(0, 8))
        self.g_stories = LabeledEntry(gp, "Stories:",   "3",   width=5)
        self.g_stories.pack(side="left", padx=(0, 8))

        gp2 = tk.Frame(self.grid_frame, bg=BG_CARD)
        gp2.pack(fill="x", padx=10, pady=(0, 4))
        self.g_sx = LabeledEntry(gp2, "Bay Spacing X (m):", "5.0", width=6)
        self.g_sx.pack(side="left", padx=(0, 8))
        self.g_sz = LabeledEntry(gp2, "Bay Spacing Z (m):", "5.0", width=6)
        self.g_sz.pack(side="left", padx=(0, 8))
        self.g_sh = LabeledEntry(gp2, "Story Height (m):", "3.0", width=6)
        self.g_sh.pack(side="left")

        StyledButton(self.grid_frame, "⚙  Generate Grid",
                     self._generate_grid, style="primary"
                     ).pack(padx=10, pady=(0, 10))

        # Node/Member list
        list_f = SectionFrame(parent, "Current Nodes & Members")
        list_f.pack(fill="both", expand=True, **pad)
        self.node_list = scrolledtext.ScrolledText(
            list_f, height=8, bg=BG_INPUT, fg=TEXT_PRI,
            font=FONT_SMALL, relief="flat", bd=0, state="disabled"
        )
        self.node_list.pack(fill="both", expand=True, padx=6, pady=6)

        self._toggle_model_mode()

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Sections
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_sections(self, parent):
        pad = dict(padx=14, pady=10)

        col_f = SectionFrame(parent, "Column Section (Rectangular)")
        col_f.pack(fill="x", **pad)
        r = tk.Frame(col_f, bg=BG_CARD); r.pack(fill="x", padx=10, pady=8)
        self.col_b = LabeledEntry(r, "Width  b (mm):", "300", width=8)
        self.col_b.pack(side="left", padx=(0, 12))
        self.col_d = LabeledEntry(r, "Depth  d (mm):", "300", width=8)
        self.col_d.pack(side="left")

        bm_f = SectionFrame(parent, "Beam Section (Rectangular)")
        bm_f.pack(fill="x", **pad)
        r2 = tk.Frame(bm_f, bg=BG_CARD); r2.pack(fill="x", padx=10, pady=8)
        self.bm_b = LabeledEntry(r2, "Width  b (mm):", "250", width=8)
        self.bm_b.pack(side="left", padx=(0, 12))
        self.bm_d = LabeledEntry(r2, "Depth  d (mm):", "400", width=8)
        self.bm_d.pack(side="left")

        StyledButton(parent, "✔  Apply Section Properties",
                     self._apply_sections, style="primary").pack(padx=14, pady=6)

        # Preview
        prev = SectionFrame(parent, "Section Preview")
        prev.pack(fill="x", padx=14, pady=4)
        self.sec_preview = tk.Label(prev, text="No sections defined yet.",
                                    bg=BG_CARD, fg=TEXT_SEC, font=FONT_SMALL,
                                    justify="left", anchor="w")
        self.sec_preview.pack(fill="x", padx=10, pady=8)

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Materials
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_materials(self, parent):
        pad = dict(padx=14, pady=10)
        mat_f = SectionFrame(parent, "Concrete Material Definition")
        mat_f.pack(fill="x", **pad)

        rows = [
            ("Material Name:",         "mat_name",   "CONCRETE"),
            ("Elastic Modulus E (MPa):","mat_E",      "22360"),
            ("Poisson's Ratio ν:",      "mat_nu",     "0.17"),
            ("Density (kN/m³):",        "mat_rho",    "24.0"),
            ("f'c Compressive (MPa):",  "mat_fc",     "20"),
        ]
        for lbl, attr, default in rows:
            r = tk.Frame(mat_f, bg=BG_CARD); r.pack(fill="x", padx=10, pady=4)
            tk.Label(r, text=lbl, width=26, anchor="w", bg=BG_CARD,
                     fg=TEXT_SEC, font=FONT_SMALL).pack(side="left")
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            tk.Entry(r, textvariable=var, width=14, bg=BG_INPUT,
                     fg=TEXT_PRI, insertbackground=TEXT_PRI,
                     relief="flat", bd=4, font=FONT_BODY).pack(side="left")

        tk.Label(mat_f, text="Note: E = 4700√f'c for normal-weight concrete (ACI 318)",
                 bg=BG_CARD, fg=TEXT_WARN, font=FONT_SMALL
                 ).pack(anchor="w", padx=10, pady=(4, 10))

        StyledButton(parent, "✔  Apply Material",
                     self._apply_material, style="primary").pack(padx=14, pady=4)

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Slabs
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_slabs(self, parent):
        pad = dict(padx=14, pady=10)
        tk.Label(parent, text="Define floor panel behavior for load distribution.",
                 bg=BG_CARD, fg=TEXT_SEC, font=FONT_SMALL
                 ).pack(anchor="w", padx=14, pady=(14, 0))

        add_f = SectionFrame(parent, "Add Slab Panel")
        add_f.pack(fill="x", **pad)
        r = tk.Frame(add_f, bg=BG_CARD); r.pack(fill="x", padx=10, pady=8)
        self.sl_story   = LabeledEntry(r, "Story Level:", "1",        width=5)
        self.sl_story.pack(side="left", padx=(0, 10))
        self.sl_bay_x   = LabeledEntry(r, "Bay X Index:", "1",        width=5)
        self.sl_bay_x.pack(side="left", padx=(0, 10))
        self.sl_bay_z   = LabeledEntry(r, "Bay Z Index:", "1",        width=5)
        self.sl_bay_z.pack(side="left", padx=(0, 10))
        self.sl_type = tk.StringVar(value="two_way")
        tk.OptionMenu(r, self.sl_type, "one_way", "two_way").configure(
            bg=BG_INPUT, fg=TEXT_PRI, activebackground=ACCENT,
            relief="flat", font=FONT_BODY
        )
        tk.OptionMenu(r, self.sl_type, "one_way", "two_way").pack(side="left", padx=8)

        StyledButton(add_f, "+ Add Panel", self._add_slab, style="primary"
                     ).pack(padx=10, pady=(0, 8))

        list_f = SectionFrame(parent, "Defined Panels")
        list_f.pack(fill="both", expand=True, **pad)
        self.slab_list = scrolledtext.ScrolledText(
            list_f, height=10, bg=BG_INPUT, fg=TEXT_PRI,
            font=FONT_SMALL, relief="flat", bd=0, state="disabled"
        )
        self.slab_list.pack(fill="both", expand=True, padx=6, pady=6)

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Stiffness Modifiers
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_stiffness(self, parent):
        pad = dict(padx=14, pady=10)
        info = (
            "ACI 318-19 §6.6.3.1 stiffness reduction factors for\n"
            "elastic second-order analysis:\n\n"
            "  Beams:   0.35 Ig\n"
            "  Columns: 0.70 Ig\n\n"
            "These reduce the effective moment of inertia to\n"
            "account for cracking and creep."
        )
        tk.Label(parent, text=info, bg=BG_CARD, fg=TEXT_SEC,
                 font=FONT_SMALL, justify="left").pack(anchor="w", padx=14, pady=14)

        mod_f = SectionFrame(parent, "Stiffness Reduction Factors")
        mod_f.pack(fill="x", **pad)

        rows = [
            ("Beam  Iz factor (default 0.35):", "stiff_beam_iz",  "0.35"),
            ("Beam  Iy factor (default 0.35):", "stiff_beam_iy",  "0.35"),
            ("Column Iz factor (default 0.70):", "stiff_col_iz",  "0.70"),
            ("Column Iy factor (default 0.70):", "stiff_col_iy",  "0.70"),
            ("Axial Area factor (columns):",     "stiff_col_ax",  "0.80"),
            ("Shear Area factor (beams):",       "stiff_bm_av",   "1.00"),
        ]
        for lbl, attr, default in rows:
            r = tk.Frame(mod_f, bg=BG_CARD); r.pack(fill="x", padx=10, pady=4)
            tk.Label(r, text=lbl, width=32, anchor="w", bg=BG_CARD,
                     fg=TEXT_SEC, font=FONT_SMALL).pack(side="left")
            var = tk.StringVar(value=default)
            setattr(self, attr, var)
            tk.Entry(r, textvariable=var, width=8, bg=BG_INPUT,
                     fg=TEXT_PRI, insertbackground=TEXT_PRI,
                     relief="flat", bd=4, font=FONT_BODY).pack(side="left")

        StyledButton(parent, "✔  Apply Stiffness Modifiers",
                     self._apply_stiffness, style="primary").pack(padx=14, pady=6)

    # ──────────────────────────────────────────────────────────────────────────
    # Tab: Loads
    # ──────────────────────────────────────────────────────────────────────────

    def _tab_loads(self, parent):
        pad = dict(padx=14, pady=10)

        dl_f = SectionFrame(parent, "Dead Load Case")
        dl_f.pack(fill="x", **pad)
        r = tk.Frame(dl_f, bg=BG_CARD); r.pack(fill="x", padx=10, pady=8)
        tk.Label(r, text="Case ID:", bg=BG_CARD, fg=TEXT_SEC,
                 font=FONT_SMALL).pack(side="left", padx=(0, 6))
        self.dl_id = tk.StringVar(value="1")
        tk.Entry(r, textvariable=self.dl_id, width=6, bg=BG_INPUT,
                 fg=TEXT_PRI, insertbackground=TEXT_PRI,
                 relief="flat", bd=4, font=FONT_BODY).pack(side="left", padx=(0, 16))
        tk.Label(r, text="Title:", bg=BG_CARD, fg=TEXT_SEC,
                 font=FONT_SMALL).pack(side="left", padx=(0, 6))
        self.dl_title = tk.StringVar(value="DEAD LOAD")
        tk.Entry(r, textvariable=self.dl_title, width=20, bg=BG_INPUT,
                 fg=TEXT_PRI, insertbackground=TEXT_PRI,
                 relief="flat", bd=4, font=FONT_BODY).pack(side="left")

        sw_f = SectionFrame(parent, "Self-Weight")
        sw_f.pack(fill="x", **pad)
        sw_r = tk.Frame(sw_f, bg=BG_CARD); sw_r.pack(fill="x", padx=10, pady=8)
        self.sw_enable = tk.BooleanVar(value=True)
        tk.Checkbutton(sw_r, text="Apply Self-Weight in Global -Y (Gravity)",
                       variable=self.sw_enable, bg=BG_CARD, fg=TEXT_PRI,
                       selectcolor=BG_INPUT, activebackground=BG_CARD,
                       font=FONT_BODY).pack(side="left")
        sw_r2 = tk.Frame(sw_f, bg=BG_CARD); sw_r2.pack(fill="x", padx=10, pady=(0, 8))
        self.sw_factor = LabeledEntry(sw_r2, "Factor (multiplier):", "1.0", width=6)
        self.sw_factor.pack(side="left")

        ll_f = SectionFrame(parent, "Live Load Case (Optional)")
        ll_f.pack(fill="x", **pad)
        self.ll_enable = tk.BooleanVar(value=False)
        tk.Checkbutton(ll_f, text="Add Live Load Case",
                       variable=self.ll_enable, bg=BG_CARD, fg=TEXT_PRI,
                       selectcolor=BG_INPUT, activebackground=BG_CARD,
                       font=FONT_BODY).pack(anchor="w", padx=10, pady=6)
        r3 = tk.Frame(ll_f, bg=BG_CARD); r3.pack(fill="x", padx=10, pady=(0, 8))
        self.ll_udl = LabeledEntry(r3, "Floor UDL (kN/m²):", "2.0", width=8)
        self.ll_udl.pack(side="left")

        StyledButton(parent, "✔  Apply Load Definitions",
                     self._apply_loads, style="primary").pack(padx=14, pady=6)

    # ──────────────────────────────────────────────────────────────────────────
    # Model Logic
    # ──────────────────────────────────────────────────────────────────────────

    def _toggle_model_mode(self):
        mode = self.model_mode.get()
        if mode == "manual":
            self.manual_frame.configure(fg=ACCENT2)
            self.grid_frame.configure(fg=TEXT_SEC)
        else:
            self.manual_frame.configure(fg=TEXT_SEC)
            self.grid_frame.configure(fg=ACCENT2)

    def _add_node_manual(self):
        try:
            nid = int(self.mn_id.get())
            x   = float(self.mn_x.get())
            y   = float(self.mn_y.get())
            z   = float(self.mn_z.get())
            self.model.add_node(Node(nid, x, y, z))
            self._refresh_node_list()
            self.log(f"✔ Node {nid} added at ({x}, {y}, {z})")
            self.mn_id.var.set(str(nid + 1))
            self._update_summary()
        except ValueError as e:
            self.log(f"✖ Invalid input: {e}", tag="err")

    def _add_member_dialog(self):
        dlg = tk.Toplevel(self)
        dlg.title("Add Member")
        dlg.configure(bg=BG_CARD)
        dlg.resizable(False, False)

        tk.Label(dlg, text="Add Member", bg=BG_CARD, fg=TEXT_PRI,
                 font=FONT_SUB).pack(padx=20, pady=(14, 8))
        r = tk.Frame(dlg, bg=BG_CARD); r.pack(padx=20, pady=6)

        mid_e  = LabeledEntry(r, "Mem ID:", str(len(self.model.members) + 1), width=6)
        mid_e.pack(side="left", padx=(0, 10))
        sn_e   = LabeledEntry(r, "Start Node:", "1", width=6)
        sn_e.pack(side="left", padx=(0, 10))
        en_e   = LabeledEntry(r, "End Node:", "2", width=6)
        en_e.pack(side="left", padx=(0, 10))

        tp_var = tk.StringVar(value="BEAM")
        tk.OptionMenu(r, tp_var, "BEAM", "COLUMN").pack(side="left")

        def confirm():
            try:
                mid = int(mid_e.get())
                sn  = int(sn_e.get())
                en  = int(en_e.get())
                m   = Member(mid, sn, en, tp_var.get())
                self.model.add_member(m)
                self._refresh_node_list()
                self.log(f"✔ Member {mid} added ({sn}→{en}) type={tp_var.get()}")
                self._update_summary()
                dlg.destroy()
            except (ValueError, KeyError) as e:
                self.log(f"✖ {e}", tag="err")

        StyledButton(dlg, "Add", confirm, style="primary").pack(pady=12)

    def _generate_grid(self):
        try:
            bx = int(self.g_bays_x.get())
            bz = int(self.g_bays_z.get())
            st = int(self.g_stories.get())
            sx = float(self.g_sx.get())
            sz = float(self.g_sz.get())
            sh = float(self.g_sh.get())

            if any(v <= 0 for v in [bx, bz, st, sx, sz, sh]):
                raise ValueError("All grid parameters must be positive.")

            self.model.clear()
            self.model.generate_grid(bx, bz, st, sx, sz, sh)
            self._refresh_node_list()
            n = len(self.model.nodes)
            m = len(self.model.members)
            self.log(f"✔ Grid generated: {n} nodes, {m} members "
                     f"({bx}×{bz} bays, {st} stories)", tag="ok")
            self._update_summary()
        except ValueError as e:
            self.log(f"✖ Grid generation error: {e}", tag="err")

    def _clear_model(self):
        if messagebox.askyesno("Clear Model", "Remove all nodes and members?"):
            self.model.clear()
            self._refresh_node_list()
            self._update_summary()
            self.log("Model cleared.", tag="warn")

    def _refresh_node_list(self):
        self.node_list.config(state="normal")
        self.node_list.delete("1.0", "end")
        self.node_list.insert("end", f"{'ID':>4}  {'X':>8}  {'Y':>8}  {'Z':>8}\n")
        self.node_list.insert("end", "─" * 36 + "\n")
        for nid, n in sorted(self.model.nodes.items()):
            self.node_list.insert("end",
                f"{nid:>4}  {n.x:>8.3f}  {n.y:>8.3f}  {n.z:>8.3f}\n")
        self.node_list.insert("end", f"\nMembers ({len(self.model.members)}):\n")
        self.node_list.insert("end", "─" * 36 + "\n")
        for mid, m in sorted(self.model.members.items()):
            self.node_list.insert("end",
                f"M{mid:>3}  {m.start_node:>4} → {m.end_node:>4}  [{m.type}]\n")
        self.node_list.config(state="disabled")

    # ──────────────────────────────────────────────────────────────────────────
    # Property / Load Logic
    # ──────────────────────────────────────────────────────────────────────────

    def _apply_sections(self):
        try:
            cb = float(self.col_b.get())
            cd = float(self.col_d.get())
            bb = float(self.bm_b.get())
            bd = float(self.bm_d.get())
            self.sections.set_column(cb, cd)
            self.sections.set_beam(bb, bd)
            self.model.assign_sections(self.sections)
            txt = (f"Column: {cb}×{cd} mm  A={cb*cd/1e6:.6f} m²\n"
                   f"        Iz={cb*cd**3/12/1e12:.4e} m⁴\n"
                   f"Beam:   {bb}×{bd} mm  A={bb*bd/1e6:.6f} m²\n"
                   f"        Iz={bb*bd**3/12/1e12:.4e} m⁴")
            self.sec_preview.config(text=txt, fg=TEXT_OK)
            self.log("✔ Section properties applied.", tag="ok")
            self._update_summary()
        except ValueError as e:
            self.log(f"✖ Section error: {e}", tag="err")

    def _apply_material(self):
        try:
            self.materials.set(
                name=self.mat_name.get(),
                E=float(self.mat_E.get()),
                nu=float(self.mat_nu.get()),
                density=float(self.mat_rho.get()),
                fc=float(self.mat_fc.get()),
            )
            self.model.assign_material(self.materials)
            self.log(f"✔ Material '{self.mat_name.get()}' applied "
                     f"(E={self.mat_E.get()} MPa, f'c={self.mat_fc.get()} MPa)", tag="ok")
            self._update_summary()
        except ValueError as e:
            self.log(f"✖ Material error: {e}", tag="err")

    def _add_slab(self):
        panel = {
            "story": self.sl_story.get(),
            "bay_x": self.sl_bay_x.get(),
            "bay_z": self.sl_bay_z.get(),
            "type":  self.sl_type.get(),
        }
        self.model.add_slab_panel(panel)
        self.slab_list.config(state="normal")
        self.slab_list.insert("end",
            f"Story {panel['story']} | Bay ({panel['bay_x']},{panel['bay_z']}) "
            f"| {panel['type'].replace('_', '-').upper()}\n")
        self.slab_list.config(state="disabled")
        self.log(f"✔ Slab panel added: {panel}", tag="ok")

    def _apply_stiffness(self):
        try:
            mods = {
                "beam_iz":  float(self.stiff_beam_iz.get()),
                "beam_iy":  float(self.stiff_beam_iy.get()),
                "col_iz":   float(self.stiff_col_iz.get()),
                "col_iy":   float(self.stiff_col_iy.get()),
                "col_ax":   float(self.stiff_col_ax.get()),
                "bm_av":    float(self.stiff_bm_av.get()),
            }
            self.model.assign_stiffness_modifiers(mods)
            self.log("✔ Stiffness modifiers applied (ACI 318-19 §6.6.3.1)", tag="ok")
        except ValueError as e:
            self.log(f"✖ Stiffness error: {e}", tag="err")

    def _apply_loads(self):
        try:
            self.loads.set_dead_load(
                case_id=int(self.dl_id.get()),
                title=self.dl_title.get(),
                selfweight=self.sw_enable.get(),
                sw_factor=float(self.sw_factor.get()),
            )
            if self.ll_enable.get():
                self.loads.add_live_load(udl=float(self.ll_udl.get()))
            self.model.assign_loads(self.loads)
            self.log("✔ Load definitions applied.", tag="ok")
            self._update_summary()
        except ValueError as e:
            self.log(f"✖ Load error: {e}", tag="err")

    # ──────────────────────────────────────────────────────────────────────────
    # Export / Validate
    # ──────────────────────────────────────────────────────────────────────────

    def _validate_model(self):
        errors = self.model.validate()
        if errors:
            for e in errors:
                self.log(f"⚠ {e}", tag="warn")
            messagebox.showwarning("Validation Issues",
                                   "\n".join(errors))
        else:
            self.log("✔ Model validation passed — no issues found.", tag="ok")
            messagebox.showinfo("Validation", "Model is valid and ready to export.")

    def _browse_dir(self):
        d = filedialog.askdirectory(initialdir=self.dir_var.get())
        if d:
            self.dir_var.set(d)

    def _run_export(self):
        errors = self.model.validate()
        if errors:
            msg = "Validation issues found:\n" + "\n".join(errors)
            if not messagebox.askyesno("Proceed?", msg + "\n\nExport anyway?"):
                return
        self.log("▶ Starting export to STAAD.Pro…", tag="info")
        threading.Thread(target=self._export_worker, daemon=True).start()

    def _export_worker(self):
        try:
            out_dir  = self.dir_var.get()
            fname    = self.fname_var.get()
            if not fname.endswith(".std"):
                fname += ".std"
            path = os.path.join(out_dir, fname)

            self.log(f"  Writing .std file → {path}", tag="info")
            self.exporter.export(self.model, self.sections,
                                 self.materials, self.loads, path)
            self.log(f"✔ Export complete: {path}", tag="ok")
            self.after(0, lambda: messagebox.showinfo(
                "Export Complete",
                f"STAAD.Pro file saved:\n{path}\n\n"
                "Open with STAAD.Pro 2025 to review the model."))
        except Exception as e:
            self.log(f"✖ Export failed: {e}", tag="err")
            self.after(0, lambda: messagebox.showerror("Export Error", str(e)))

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def log(self, msg, tag="ok"):
        self.console.config(state="normal")
        self.console.insert("end", msg + "\n", tag)
        self.console.see("end")
        self.console.config(state="disabled")

    def _clear_log(self):
        self.console.config(state="normal")
        self.console.delete("1.0", "end")
        self.console.config(state="disabled")

    def _update_summary(self):
        m = self.model
        lines = [
            f"Nodes:    {len(m.nodes)}",
            f"Members:  {len(m.members)}",
            f"Beams:    {sum(1 for v in m.members.values() if v.type=='BEAM')}",
            f"Columns:  {sum(1 for v in m.members.values() if v.type=='COLUMN')}",
            f"Slabs:    {len(m.slab_panels)}",
            f"Section:  {'✔' if m.sections_assigned else '—'}",
            f"Material: {'✔' if m.material_assigned else '—'}",
            f"Loads:    {'✔' if m.loads_assigned else '—'}",
        ]
        self.summary_lbl.config(text="\n".join(lines), fg=TEXT_PRI)


if __name__ == "__main__":
    app = MainApp()
    app.mainloop()
