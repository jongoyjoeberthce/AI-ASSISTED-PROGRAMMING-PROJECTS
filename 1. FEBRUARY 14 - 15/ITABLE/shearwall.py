import tkinter as tk
from tkinter import messagebox
import math
import matplotlib.pyplot as plt
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from openstaadpy import os_analytical

# =====================================
# CONNECT TO STAAD
# =====================================
def get_reactions():

    try:
        node = int(entry_node.get())

        staad = os_analytical.connect()
        if staad is None:
            messagebox.showerror("Error", "STAAD not connected.")
            return

        output = staad.Output

        load_case = int(entry_loadcase.get())

        # Get reactions
        Rx = output.GetNodeReaction(node, load_case, 0)
        Ry = output.GetNodeReaction(node, load_case, 1)
        Rz = output.GetNodeReaction(node, load_case, 2)

        Mx = output.GetNodeReaction(node, load_case, 3)
        My = output.GetNodeReaction(node, load_case, 4)
        Mz = output.GetNodeReaction(node, load_case, 5)

        Pu = abs(Ry)  # vertical reaction
        Mu = abs(Mz)  # assume moment about Z

        entry_Pu.delete(0, tk.END)
        entry_Pu.insert(0, f"{Pu:.2f}")

        entry_Mu.delete(0, tk.END)
        entry_Mu.insert(0, f"{Mu:.2f}")

        messagebox.showinfo("Success", "Reactions Imported from STAAD.")

    except:
        messagebox.showerror("Error", "Failed to extract reactions.")


# =====================================
# DESIGN ENGINE
# =====================================
def design_footing():

    try:
        Pu = float(entry_Pu.get())
        Mu = float(entry_Mu.get())
        SBC = float(entry_SBC.get())
        fc = float(entry_fc.get())
        fy = float(entry_fy.get())
        wall_L = float(entry_wallL.get())
        wall_t = float(entry_wallT.get())

        phi = 0.9

        # Required Area
        A_req = Pu / SBC
        B = math.sqrt(A_req)
        L = B

        # Eccentricity
        e = Mu / Pu
        q_avg = Pu / (L * B)
        q_max = q_avg * (1 + 6*e/L)
        q_min = q_avg * (1 - 6*e/L)

        ecc_status = "OK" if abs(e) <= L/6 else "Tension Develops"

        # Depth assumption
        d = 0.6
        h = d + 0.075

        # One-way shear
        Vu = q_max * (L - wall_L) * B / 2
        Vc = 0.17 * math.sqrt(fc) * B * d * 1000
        shear_status = "OK" if Vu*1000 < Vc else "Increase Depth"

        # Punching shear
        bo = 2*(wall_L + wall_t + 2*d)
        Vc_p = 0.33 * math.sqrt(fc) * bo * d * 1000
        punch_status = "OK" if Pu*1000 < Vc_p else "Increase Thickness"

        # Flexure
        Mu_design = q_max * (L - wall_L)**2 * B / 8
        As_req = (Mu_design * 10**6) / (phi * fy * d * 1000)

        result_text = f"""
FOOTING SIZE
L = {L:.2f} m
B = {B:.2f} m
Thickness ≈ {h:.2f} m

ECCENTRICITY
e = {e:.3f} m → {ecc_status}
q_max = {q_max:.1f} kN/m²
q_min = {q_min:.1f} kN/m²

ONE-WAY SHEAR → {shear_status}
PUNCHING SHEAR → {punch_status}

REQUIRED STEEL
As = {As_req:.0f} mm²
"""
        result_label.config(text=result_text)

        draw_figure(L, B, wall_L, wall_t, d)

    except:
        messagebox.showerror("Error", "Check input values.")


# =====================================
# DRAWING
# =====================================
def draw_figure(L, B, wall_L, wall_t, d):

    ax.clear()

    footing_x = [-L/2, L/2, L/2, -L/2, -L/2]
    footing_y = [-B/2, -B/2, B/2, B/2, -B/2]
    ax.plot(footing_x, footing_y)

    wall_x = [-wall_L/2, wall_L/2, wall_L/2, -wall_L/2, -wall_L/2]
    wall_y = [-wall_t/2, -wall_t/2, wall_t/2, wall_t/2, -wall_t/2]
    ax.plot(wall_x, wall_y)

    crit_L = wall_L + 2*d
    crit_B = wall_t + 2*d
    crit_x = [-crit_L/2, crit_L/2, crit_L/2, -crit_L/2, -crit_L/2]
    crit_y = [-crit_B/2, -crit_B/2, crit_B/2, crit_B/2, -crit_B/2]
    ax.plot(crit_x, crit_y, linestyle='--')

    ax.set_aspect('equal')
    ax.set_title("Automated Shear Wall Footing – STAAD Connected")
    ax.grid(True)

    canvas.draw()


# =====================================
# GUI
# =====================================
root = tk.Tk()
root.title("VERSION 3 – STAAD Automated Footing Designer")
root.geometry("950x800")

tk.Label(root, text="STAAD CONNECTED SHEAR WALL FOOTING DESIGNER",
         font=("Arial", 15)).pack(pady=10)

def create_input(label):
    tk.Label(root, text=label).pack()
    e = tk.Entry(root)
    e.pack()
    return e

entry_node = create_input("Support Node Number")
entry_loadcase = create_input("Load Case Number")

tk.Button(root, text="IMPORT REACTIONS FROM STAAD",
          command=get_reactions).pack(pady=5)

entry_Pu = create_input("Pu (Auto-filled)")
entry_Mu = create_input("Mu (Auto-filled)")
entry_SBC = create_input("Allowable Soil Bearing (kN/m²)")
entry_fc = create_input("Concrete Strength f'c (MPa)")
entry_fy = create_input("Steel Yield Strength fy (MPa)")
entry_wallL = create_input("Wall Length (m)")
entry_wallT = create_input("Wall Thickness (m)")

tk.Button(root, text="RUN DESIGN", command=design_footing).pack(pady=15)

result_label = tk.Label(root, text="", justify="left")
result_label.pack()

fig = plt.Figure(figsize=(6,6))
ax = fig.add_subplot(111)

canvas = FigureCanvasTkAgg(fig, master=root)
canvas.get_tk_widget().pack(pady=20)

root.mainloop()
