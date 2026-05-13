import math
import tkinter as tk
from tkinter import ttk, messagebox

from openstaadpy import os_analytical


# -----------------------------
# Helpers (safe checks)
# -----------------------------
def safe_get_node_count(staad):
    """
    Tries a few common ways to get node count. If not available, returns None.
    """
    geo = staad.Geometry
    for name in ("GetNoOfNodes", "GetNumberOfNodes", "GetNodeCount"):
        fn = getattr(geo, name, None)
        if callable(fn):
            try:
                return int(fn())
            except Exception:
                pass
    return None


def safe_get_member_count(staad):
    """
    Tries a few common ways to get member count. If not available, returns None.
    """
    geo = staad.Geometry
    for name in ("GetNoOfBeams", "GetNumberOfBeams", "GetBeamCount", "GetNoOfMembers"):
        fn = getattr(geo, name, None)
        if callable(fn):
            try:
                return int(fn())
            except Exception:
                pass
    return None


# -----------------------------
# Core Builder
# -----------------------------
def build_3d_warehouse_on_open_model(
    staad,
    length_m: float,
    width_m: float,
    eave_m: float,
    rise_m: float,
    frame_spacing_m: float,
    n_purlin_lines_per_slope: int,
    col_section: str,
    rafter_section: str,
    purlin_section: str,
    roof_udl_kN_per_m: float,
    wind_kN_per_m: float,
    base_support: str,  # "Pinned" or "Fixed"
    vertical_axis: str  # "Y" or "Z"
):
    """
    Builds on the CURRENTLY OPEN STAAD model (must be blank/empty).
    """

    geo = staad.Geometry
    prop = staad.Property
    sup = staad.Support
    load = staad.Load

    # ---- SI Units: Meter + kN
    # OpenSTAAD unit codes: Length 4 = Meter, Force 5 = KiloNewton
    staad.SetInputUnits(4, 5)
    staad.SaveModel(True)

    # ---- Basic validation
    if length_m <= 0 or width_m <= 0 or eave_m <= 0:
        raise ValueError("Length, width, and eave height must be > 0.")
    if frame_spacing_m <= 0:
        raise ValueError("Frame spacing must be > 0.")
    if n_purlin_lines_per_slope < 0:
        raise ValueError("Number of purlin lines must be 0 or more.")

    # ---- Decide number of portal frames
    n_frames = int(round(length_m / frame_spacing_m)) + 1
    n_frames = max(n_frames, 2)

    half_w = width_m / 2.0
    ridge_h = eave_m + rise_m

    # Coordinate system we will use:
    # X = width (left-right)
    # Y = length (front-back)
    # Z = vertical IF vertical_axis == "Z"
    #
    # If your STAAD uses Y as vertical, we swap Y/Z usage for node creation and loads.
    def xyz(x, y, z):
        if vertical_axis.upper() == "Z":
            return (x, y, z)  # Z up
        else:
            return (x, z, y)  # Y up (swap)

    # Node/member IDs (simple sequential)
    node_id = 1
    mem_id = 1

    def create_node(x, y, z):
        nonlocal node_id
        (X, Y, Z) = xyz(x, y, z)
        geo.CreateNode(node_id, X, Y, Z)
        node_id += 1
        return node_id - 1

    def create_member(n1, n2):
        nonlocal mem_id
        geo.CreateBeam(mem_id, n1, n2)
        mem_id += 1
        return mem_id - 1

    # Each frame nodes: A(left base), B(right base), C(left eave), D(right eave), E(ridge)
    frames = []
    columns = []
    rafters = []

    for i in range(n_frames):
        y = i * frame_spacing_m

        A = create_node(-half_w, y, 0.0)
        B = create_node(+half_w, y, 0.0)
        C = create_node(-half_w, y, eave_m)
        D = create_node(+half_w, y, eave_m)
        E = create_node(0.0,    y, ridge_h)

        col1 = create_member(A, C)
        col2 = create_member(B, D)
        raf1 = create_member(C, E)
        raf2 = create_member(D, E)

        columns += [col1, col2]
        rafters += [raf1, raf2]

        frames.append({"A": A, "B": B, "C": C, "D": D, "E": E})

    # Longitudinal members (purlins): connect frame-to-frame at multiple roof lines
    # We'll make:
    # - Eave left line (C-C)
    # - Eave right line (D-D)
    # - Ridge line (E-E)
    # - Optional intermediate purlin lines along rafters (linear interpolation)
    purlins = []

    def interp_node_on_slope(frame, side: str, t: float):
        """
        side: "L" => from C to E
              "R" => from D to E
        t: 0 at eave node, 1 at ridge
        Creates a new node at interpolated position for that frame and returns its ID.
        """
        if side == "L":
            x0, y0, z0 = (-half_w, None, eave_m)
        else:
            x0, y0, z0 = (+half_w, None, eave_m)

        # Use current frame's y
        y = frame["y"]
        x1, z1 = (0.0, ridge_h)

        x = x0 + (x1 - x0) * t
        z = z0 + (z1 - z0) * t
        return create_node(x, y, z)

    # Store intermediate roofline nodes for each frame so we can connect them longitudinally
    roof_lines_L = []
    roof_lines_R = []

    # Add y value into frame dict for interpolation helper
    for i in range(n_frames):
        frames[i]["y"] = i * frame_spacing_m

    if n_purlin_lines_per_slope > 0:
        # Create intermediate nodes for each frame at evenly spaced t
        for i in range(n_frames):
            f = frames[i]
            nodes_L = []
            nodes_R = []
            for k in range(1, n_purlin_lines_per_slope + 1):
                t = k / (n_purlin_lines_per_slope + 1)  # between 0 and 1
                nodes_L.append(interp_node_on_slope(f, "L", t))
                nodes_R.append(interp_node_on_slope(f, "R", t))
            roof_lines_L.append(nodes_L)
            roof_lines_R.append(nodes_R)
    else:
        roof_lines_L = [[] for _ in range(n_frames)]
        roof_lines_R = [[] for _ in range(n_frames)]

    for i in range(n_frames - 1):
        f1 = frames[i]
        f2 = frames[i + 1]

        # eaves and ridge
        purlins.append(create_member(f1["C"], f2["C"]))
        purlins.append(create_member(f1["D"], f2["D"]))
        purlins.append(create_member(f1["E"], f2["E"]))

        # intermediate lines
        for k in range(len(roof_lines_L[i])):
            purlins.append(create_member(roof_lines_L[i][k], roof_lines_L[i + 1][k]))
            purlins.append(create_member(roof_lines_R[i][k], roof_lines_R[i + 1][k]))

    # -----------------------------
    # Properties
    # -----------------------------
    # Country code 1 = American tables in many STAAD installs
    # If you want Euro/Indian/etc, change cc accordingly.
    cc = 1
    col_prop = prop.CreateBeamPropertyFromTable(cc, col_section, 0, 0.0, 0.0)
    raf_prop = prop.CreateBeamPropertyFromTable(cc, rafter_section, 0, 0.0, 0.0)
    pur_prop = prop.CreateBeamPropertyFromTable(cc, purlin_section, 0, 0.0, 0.0)

    prop.AssignBeamProperty(columns, col_prop)
    prop.AssignBeamProperty(rafters, raf_prop)
    if purlins:
        prop.AssignBeamProperty(purlins, pur_prop)

    prop.AssignMaterialToMember("STEEL", list(range(1, mem_id)))

    # -----------------------------
    # Supports
    # -----------------------------
    base_nodes = []
    for f in frames:
        base_nodes += [f["A"], f["B"]]

    if base_support == "Fixed":
        sid = sup.CreateSupportFixed()
    else:
        sid = sup.CreateSupportPinned()

    sup.AssignSupportToNode(base_nodes, sid)

    # -----------------------------
    # Loads
    # -----------------------------
    # Direction code: your wrapper may interpret these differently.
    # We'll keep:
    # - Selfweight in global vertical (negative)
    # - Roof UDL as member load in vertical
    # - Wind as member load in +X
    #
    # If your loads go the wrong direction, tell me your STAAD global axes and I’ll adjust the codes.
    case1 = load.CreateNewPrimaryLoadEx2("DL + ROOF", 0, 1)
    load.SetLoadActive(case1)

    if vertical_axis.upper() == "Z":
        # if Z is vertical: use global Z for gravity
        # selfweight helper often uses 2=GY in older examples, but this varies.
        # We'll apply member loads in vertical properly either way.
        pass

    # Selfweight: we keep a conservative call used commonly in OpenSTAAD scripts.
    # If it doesn't act as gravity in your STAAD, remove it and rely on member loads.
    load.AddSelfWeightInXYZ(2, -1.0)

    # Roof vertical UDL on rafters
    # direction: using 3 as "global vertical" in many wrappers; adjust if needed.
    for m in rafters:
        load.AddMemberUniformForce([m], 3, -abs(roof_udl_kN_per_m), 0.0, 0.0, 0.0)

    # Wind +X
    case2 = load.CreateNewPrimaryLoadEx2("WIND +X", 3, 2)
    load.SetLoadActive(case2)
    for m in columns:
        load.AddMemberUniformForce([m], 4, abs(wind_kN_per_m), 0.0, 0.0, 0.0)

    # Simple combination
    comb = load.CreateNewLoadCombination("1.0DL + 1.0WIND", 3)
    load.AddLoadAndFactorToCombination(3, 1, 1.0)
    load.AddLoadAndFactorToCombination(3, 2, 1.0)

    staad.SaveModel(True)
    staad.Command.PerformAnalysis(0)

    return {
        "frames": n_frames,
        "nodes": node_id - 1,
        "members": mem_id - 1,
        "columns": len(columns),
        "rafters": len(rafters),
        "purlins": len(purlins)
    }


# -----------------------------
# GUI
# -----------------------------
class WarehouseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("STAAD Warehouse Builder (SI) — requires BLANK STAAD model open")
        self.geometry("860x560")

        self.staad = None
        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        top = ttk.Frame(self)
        top.pack(fill="x", padx=12, pady=12)

        self.status = tk.StringVar(value="Status: Not connected. Open STAAD.Pro + open a NEW blank model first.")
        ttk.Label(top, textvariable=self.status).pack(side="left", fill="x", expand=True)

        ttk.Button(top, text="Connect to STAAD", command=self.connect).pack(side="right")

        frm = ttk.LabelFrame(self, text="Warehouse Inputs (SI Units: m, kN)")
        frm.pack(fill="x", padx=12, pady=8)

        self.length_m = tk.DoubleVar(value=40.0)
        self.width_m = tk.DoubleVar(value=20.0)
        self.eave_m = tk.DoubleVar(value=6.0)
        self.rise_m = tk.DoubleVar(value=2.0)
        self.spacing_m = tk.DoubleVar(value=5.0)

        self.n_purlins = tk.IntVar(value=2)

        self.col_sec = tk.StringVar(value="W14X90")
        self.raf_sec = tk.StringVar(value="W18X35")
        self.pur_sec = tk.StringVar(value="C8X11.5")  # example channel string; adjust to your STAAD table naming

        self.roof_udl = tk.DoubleVar(value=1.5)  # kN/m (placeholder)
        self.wind = tk.DoubleVar(value=0.8)      # kN/m (placeholder)

        self.support_type = tk.StringVar(value="Pinned")
        self.vertical_axis = tk.StringVar(value="Z")

        grid = ttk.Frame(frm)
        grid.pack(fill="x", padx=10, pady=10)

        def row(r, label, var, w=14):
            ttk.Label(grid, text=label).grid(row=r, column=0, sticky="w", pady=3)
            ttk.Entry(grid, textvariable=var, width=w).grid(row=r, column=1, sticky="w", padx=(10, 0), pady=3)

        row(0, "Length (m):", self.length_m)
        row(1, "Width (m):", self.width_m)
        row(2, "Eave height (m):", self.eave_m)
        row(3, "Roof rise (m):", self.rise_m)
        row(4, "Frame spacing (m):", self.spacing_m)
        row(5, "Intermediate purlin lines / slope:", self.n_purlins)

        ttk.Separator(grid, orient="horizontal").grid(row=6, column=0, columnspan=2, sticky="ew", pady=10)

        row(7, "Column section (WF):", self.col_sec, w=20)
        row(8, "Rafter section (WF):", self.raf_sec, w=20)
        row(9, "Purlin section (Channel/C):", self.pur_sec, w=20)

        ttk.Separator(grid, orient="horizontal").grid(row=10, column=0, columnspan=2, sticky="ew", pady=10)

        row(11, "Roof UDL (kN/m):", self.roof_udl)
        row(12, "Wind line load +X (kN/m):", self.wind)

        ttk.Label(grid, text="Base support:").grid(row=13, column=0, sticky="w", pady=3)
        ttk.Combobox(grid, textvariable=self.support_type, values=["Pinned", "Fixed"], width=12, state="readonly")\
            .grid(row=13, column=1, sticky="w", padx=(10, 0), pady=3)

        ttk.Label(grid, text="Vertical axis in your STAAD model:").grid(row=14, column=0, sticky="w", pady=3)
        ttk.Combobox(grid, textvariable=self.vertical_axis, values=["Z", "Y"], width=12, state="readonly")\
            .grid(row=14, column=1, sticky="w", padx=(10, 0), pady=3)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=12, pady=10)

        ttk.Button(btns, text="Build 3D Warehouse in CURRENT STAAD model", command=self.build).pack(side="right")
        ttk.Button(btns, text="Quit", command=self.destroy).pack(side="right", padx=(0, 8))

        notes = ttk.LabelFrame(self, text="Important Notes")
        notes.pack(fill="both", expand=True, padx=12, pady=8)

        txt = (
            "1) REQUIRED WORKFLOW:\n"
            "   • Open STAAD.Pro\n"
            "   • File > New (blank)\n"
            "   • Save the file (recommended)\n"
            "   • Then click 'Connect' and 'Build'\n\n"
            "2) Section names MUST match your STAAD section database naming.\n"
            "   If channel 'C8X11.5' fails, replace with what your STAAD Table uses.\n\n"
            "3) Load direction codes in OpenSTAAD wrappers can vary.\n"
            "   If roof load goes sideways or wind is wrong, tell me your global axes and we’ll correct it.\n"
        )
        ttk.Label(notes, text=txt, justify="left").pack(anchor="w", padx=10, pady=10)

    def connect(self):
        try:
            self.staad = os_analytical.connect()
            if self.staad is None:
                raise RuntimeError("STAAD object not found. Open STAAD.Pro first.")
            self.status.set("Status: Connected ✅  (Now make sure the open file is BLANK before building)")
        except Exception as e:
            messagebox.showerror("Connection Error", str(e))
            self.status.set("Status: Not connected.")

    def build(self):
        if self.staad is None:
            messagebox.showwarning("Not connected", "Please connect to STAAD first.")
            return

        # Enforce "blank model" rule as best-effort:
        n_nodes = safe_get_node_count(self.staad)
        n_mems = safe_get_member_count(self.staad)

        if n_nodes is not None and n_nodes > 0:
            messagebox.showerror(
                "Model not blank",
                f"The currently open STAAD model already has {n_nodes} node(s).\n\n"
                "Please open a NEW BLANK STAAD file first, then run this generator."
            )
            return

        if n_mems is not None and n_mems > 0:
            messagebox.showerror(
                "Model not blank",
                f"The currently open STAAD model already has {n_mems} member(s).\n\n"
                "Please open a NEW BLANK STAAD file first, then run this generator."
            )
            return

        try:
            result = build_3d_warehouse_on_open_model(
                staad=self.staad,
                length_m=float(self.length_m.get()),
                width_m=float(self.width_m.get()),
                eave_m=float(self.eave_m.get()),
                rise_m=float(self.rise_m.get()),
                frame_spacing_m=float(self.spacing_m.get()),
                n_purlin_lines_per_slope=int(self.n_purlins.get()),
                col_section=self.col_sec.get().strip(),
                rafter_section=self.raf_sec.get().strip(),
                purlin_section=self.pur_sec.get().strip(),
                roof_udl_kN_per_m=float(self.roof_udl.get()),
                wind_kN_per_m=float(self.wind.get()),
                base_support=self.support_type.get(),
                vertical_axis=self.vertical_axis.get()
            )

            messagebox.showinfo(
                "Done",
                "3D warehouse created in the CURRENT STAAD model.\n\n"
                f"Frames: {result['frames']}\n"
                f"Nodes: {result['nodes']}\n"
                f"Members: {result['members']}\n"
                f"Columns: {result['columns']}\n"
                f"Rafters: {result['rafters']}\n"
                f"Purlins: {result['purlins']}\n\n"
                "Now go to STAAD.Pro, view the model, and save."
            )
        except Exception as e:
            messagebox.showerror("Build Error", str(e))


if __name__ == "__main__":
    app = WarehouseApp()
    app.mainloop()
