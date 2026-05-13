"""
BEAM DEFLECTION CALCULATOR (GUI)
--------------------------------
Description:
    A professional-grade tool to calculate and visualize the deflection of 
    simply supported and cantilever beams under various loading conditions.

Physics Implementation:
    - Simply Supported: Fixed against translation at both ends.
    - Cantilever: Fixed against translation and rotation at x=0 (Built-in).
    - Euler-Bernoulli equations are used for all cases.

Dependencies:
    - tkinter: GUI framework
    - matplotlib: Plotting engine
    - numpy: Numerical array handling for smooth curves
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
import csv

class BeamCalculator:
    def __init__(self, root):
        self.root = root
        self.root.title("Engineering Beam Deflection Calculator")
        self.root.geometry("1100x750")

        # --- Reactive Variables ---
        self.beam_type = tk.StringVar(value="Simply Supported")
        self.load_type = tk.StringVar(value="Point Load at Center")
        self.unit_system = tk.StringVar(value="SI (m, N, Pa, m^4)")
        
        # Physical Parameters
        self.L = tk.DoubleVar(value=10.0)      # Beam Length
        self.E = tk.DoubleVar(value=210e9)     # Young's Modulus (Default: Steel)
        self.I = tk.DoubleVar(value=0.0001)    # Moment of Inertia
        self.P = tk.DoubleVar(value=1000.0)    # Load (Force in N or Weight in N/m)
        self.a = tk.DoubleVar(value=5.0)       # Distance to load from left
        self.x_eval = tk.DoubleVar(value=5.0)  # Point to calculate specific deflection

        self.setup_ui()

    def setup_ui(self):
        """Builds the Tkinter interface layout."""
        # Main Layout: Left for Inputs, Right for Plotting
        left_panel = ttk.Frame(self.root, padding="10")
        left_panel.pack(side=tk.LEFT, fill=tk.Y)

        right_panel = ttk.Frame(self.root, padding="10")
        right_panel.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        # --- Input Section ---
        ttk.Label(left_panel, text="Beam Configuration", font=('Helvetica', 12, 'bold')).grid(row=0, column=0, pady=10)

        # Dropdowns
        ttk.Label(left_panel, text="Units:").grid(row=1, column=0, sticky='w')
        ttk.Combobox(left_panel, textvariable=self.unit_system, values=["SI (m, N, Pa, m^4)", "Imperial (in, lb, psi, in^4)"], state="readonly").grid(row=1, column=1)

        ttk.Label(left_panel, text="Beam Type:").grid(row=2, column=0, sticky='w')
        ttk.Combobox(left_panel, textvariable=self.beam_type, values=["Simply Supported", "Cantilever"], state="readonly").grid(row=2, column=1)

        ttk.Label(left_panel, text="Load Case:").grid(row=3, column=0, sticky='w')
        ttk.Combobox(left_panel, textvariable=self.load_type, values=["Point Load at Center", "Point Load at Arbitrary Position", "UDL (Uniformly Distributed)"], state="readonly").grid(row=3, column=1)

        # Numerical Entries
        fields = [
            ("Length (L):", self.L),
            ("Young's Modulus (E):", self.E),
            ("Moment of Inertia (I):", self.I),
            ("Load Magnitude (P or w):", self.P),
            ("Load Position (a):", self.a),
            ("Evaluate at x:", self.x_eval)
        ]

        for i, (label, var) in enumerate(fields, start=4):
            ttk.Label(left_panel, text=label).grid(row=i, column=0, sticky='w', pady=2)
            ttk.Entry(left_panel, textvariable=var).grid(row=i, column=1, pady=2)

        # Control Buttons
        btn_frame = ttk.Frame(left_panel)
        btn_frame.grid(row=10, column=0, columnspan=2, pady=20)
        
        ttk.Button(btn_frame, text="Calculate", command=self.calculate).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Reset", command=self.reset_fields).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="Export CSV", command=self.export_csv).pack(side=tk.LEFT, padx=5)

        # Results Text Area
        self.output_text = tk.Text(left_panel, height=8, width=40, state='disabled', background="#f0f0f0")
        self.output_text.grid(row=12, column=0, columnspan=2, pady=5)

       # --- Matplotlib integration ---
        # 1. Create the figure and axis with a clean style
        # 'constrained_layout' automatically adjusts subplots to fit in the figure area
        self.fig, self.ax = plt.subplots(figsize=(6, 4), dpi=100, constrained_layout=True)
        
        # 2. Styling the plot area immediately
        self.ax.set_facecolor('#f8f9fa')  # Light grey background
        self.ax.tick_params(axis='both', which='major', labelsize=9)
        
        # 3. Create the Canvas
        self.canvas = FigureCanvasTkAgg(self.fig, master=right_panel)
        canvas_widget = self.canvas.get_tk_widget()
        canvas_widget.pack(fill=tk.BOTH, expand=True)

        # 4. Add the Navigation Toolbar (Bonus Feature)
        # This allows users to zoom, pan, and save the graph as an image
        from matplotlib.backends.backend_tkagg import NavigationToolbar2Tk
        self.toolbar = NavigationToolbar2Tk(self.canvas, right_panel)
        self.toolbar.update()
        self.toolbar.pack(side=tk.BOTTOM, fill=tk.X)

    def validate(self):
        """Check for physical impossibilities and input errors."""
        try:
            if self.L.get() <= 0 or self.E.get() <= 0 or self.I.get() <= 0:
                raise ValueError("Length, E, and I must be greater than zero.")
            if self.a.get() > self.L.get() or self.x_eval.get() > self.L.get():
                raise ValueError("Position 'a' and 'x' cannot be longer than the beam.")
            return True
        except Exception as e:
            messagebox.showerror("Input Error", str(e))
            return False

    def calculate_physics(self):
        """
        The core engine. Implements standard beam deflection formulas.
        Returns: x-coordinates, y-deflections, max deflection, and deflection at x_eval.
        """
        L, E, I, P, a, x_eval = self.L.get(), self.E.get(), self.I.get(), self.P.get(), self.a.get(), self.x_eval.get()
        x_vals = np.linspace(0, L, 200) # Create 200 data points for a smooth curve
        y_vals = []
        max_defl = 0
        defl_at_x = 0
        EI = E * I # Flexural Rigidity

        bt = self.beam_type.get()
        lt = self.load_type.get()

        # --- CASE: SIMPLY SUPPORTED ---
        if bt == "Simply Supported":
            if lt == "Point Load at Center":
                # Max deflection at L/2: (P * L^3) / (48 * E * I)
                max_defl = (P * L**3) / (48 * EI)
                for x in x_vals:
                    # Piecewise logic (symmetric about center)
                    v = x if x <= L/2 else L - x
                    y_vals.append((P * v * (3*L**2 - 4*v**2)) / (48 * EI))
                v_eval = x_eval if x_eval <= L/2 else L - x_eval
                defl_at_x = (P * v_eval * (3*L**2 - 4*v_eval**2)) / (48 * EI)

            elif lt == "Point Load at Arbitrary Position":
                b = L - a # Distance from right support
                # Max deflection occurs at x = sqrt((L^2 - b^2)/3)
                max_defl = (P * b * (L**2 - b**2)**1.5) / (9 * np.sqrt(3) * L * EI)
                for x in x_vals:
                    if x <= a:
                        y = (P * b * x * (L**2 - x**2 - b**2)) / (6 * L * EI)
                    else:
                        y = (P * a * (L - x) * (L**2 - (L - x)**2 - a**2)) / (6 * L * EI)
                    y_vals.append(y)
                # Specific eval point logic
                if x_eval <= a:
                    defl_at_x = (P * b * x_eval * (L**2 - x_eval**2 - b**2)) / (6 * L * EI)
                else:
                    defl_at_x = (P * a * (L - x_eval) * (L**2 - (L - x_eval)**2 - a**2)) / (6 * L * EI)

            elif lt == "UDL (Uniformly Distributed)":
                # Max deflection: (5 * w * L^4) / (384 * E * I)
                max_defl = (5 * P * L**4) / (384 * EI)
                y_vals = [(P * x * (L**3 - 2*L*x**2 + x**3)) / (24 * EI) for x in x_vals]
                defl_at_x = (P * x_eval * (L**3 - 2*L*x_eval**2 + x_eval**3)) / (24 * EI)

        # --- CASE: CANTILEVER (Fixed at x=0) ---
        elif bt == "Cantilever":
            if lt == "Point Load at Center": # Treated as point load at End for this template
                max_defl = (P * L**3) / (3 * EI)
                y_vals = [(P * x**2 * (3*L - x)) / (6 * EI) for x in x_vals]
                defl_at_x = (P * x_eval**2 * (3*L - x_eval)) / (6 * EI)

            elif lt == "Point Load at Arbitrary Position":
                # Max deflection at free end (x=L)
                max_defl = (P * a**2 * (3*L - a)) / (6 * EI)
                for x in x_vals:
                    if x <= a:
                        y = (P * x**2 * (3*a - x)) / (6 * EI)
                    else:
                        y = (P * a**2 * (3*x - a)) / (6 * EI)
                    y_vals.append(y)
                defl_at_x = (P * x_eval**2 * (3*a - x_eval)) / (6 * EI) if x_eval <= a else (P * a**2 * (3*x_eval - a)) / (6 * EI)

            elif lt == "UDL (Uniformly Distributed)":
                # Max deflection: (w * L^4) / (8 * E * I)
                max_defl = (P * L**4) / (8 * EI)
                y_vals = [(P * x**2 * (6*L**2 - 4*L*x + x**2)) / (24 * EI) for x in x_vals]
                defl_at_x = (P * x_eval**2 * (6*L**2 - 4*L*x_eval + x_eval**2)) / (24 * EI)

        return x_vals, y_vals, max_defl, defl_at_x

    def calculate(self):
        """Triggered by 'Calculate' button. Updates UI and Plot."""
        if not self.validate(): return
        
        x_vals, y_vals, max_d, eval_d = self.calculate_physics()
        
        # Plotting logic
        self.ax.clear()
        # Note: -y is used because we want the graph to show the beam sagging 'down'
        self.ax.plot(x_vals, [-y for y in y_vals], 'b-', linewidth=3, label='Elastic Curve')
        self.ax.axhline(0, color='red', linestyle='--', lw=1) # Original beam axis
        self.ax.set_title(f"Deflection Profile: {self.beam_type.get()}")
        self.ax.set_xlabel("Length (Units as per selection)")
        self.ax.set_ylabel("Deflection (m or in)")
        self.ax.grid(True, alpha=0.3)
        self.canvas.draw()

        # Formatting Output Text
        self.output_text.config(state='normal')
        self.output_text.delete('1.0', tk.END)
        summary = (
            f"--- RESULTS ---\n"
            f"Max Deflection: {max_d:.6f}\n"
            f"Deflection at x={self.x_eval.get()}: {eval_d:.6f}\n"
            f"Flexural Rigidity (EI): {self.E.get()*self.I.get():.2e}\n"
        )
        self.output_text.insert(tk.END, summary)
        self.output_text.config(state='disabled')

    def reset_fields(self):
        """Clears inputs and the graph."""
        self.L.set(10.0)
        self.E.set(210e9)
        self.I.set(0.0001)
        self.P.set(1000.0)
        self.a.set(5.0)
        self.x_eval.set(5.0)
        self.ax.clear()
        self.canvas.draw()
        self.output_text.config(state='normal')
        self.output_text.delete('1.0', tk.END)
        self.output_text.config(state='disabled')

    def export_csv(self):
        """Saves the plotted coordinates to a CSV file."""
        if not self.validate(): return
        x_vals, y_vals, _, _ = self.calculate_physics()
        path = filedialog.asksaveasfilename(defaultextension=".csv")
        if path:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow(["X_Position", "Y_Deflection"])
                writer.writerows(zip(x_vals, y_vals))
            messagebox.showinfo("Success", "Data exported.")

if __name__ == "__main__":
    root = tk.Tk()
    app = BeamCalculator(root)
    root.mainloop()