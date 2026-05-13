from flask import Flask, render_template, request
import matplotlib.pyplot as plt
import os

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    result = None
    if request.method == "POST":
        b = float(request.form["b"])
        h = float(request.form["h"])
        fc = float(request.form["fc"])
        fy = float(request.form["fy"])
        Pu = float(request.form["Pu"])
        Mu = float(request.form["Mu"])

        Ag = b * h
        phi = 0.65

        # Simplified capacity
        Pn = 0.85 * fc * Ag / 1000
        phiPn = phi * Pn

        Mn = 0.10 * Pn
        phiMn = phi * Mn

        safe = (Pu <= phiPn and Mu <= phiMn)

        result = {
            "phiPn": round(phiPn, 2),
            "phiMn": round(phiMn, 2),
            "status": "SAFE" if safe else "UNSAFE"
        }

        # Generate interaction diagram
        plt.figure()
        plt.plot([0, phiMn], [phiPn, 0])  # simple line
        plt.scatter(Mu, Pu)
        plt.xlabel("Moment (kN·m)")
        plt.ylabel("Axial Load (kN)")
        plt.title("P-M Interaction Diagram")
        plt.grid()

        if not os.path.exists("static"):
            os.makedirs("static")

        plt.savefig("static/diagram.png")
        plt.close()

    return render_template("index.html", result=result)

if __name__ == "__main__":
    app.run(debug=True)