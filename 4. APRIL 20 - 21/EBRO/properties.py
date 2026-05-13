"""
properties.py – Section and Material property definitions
"""
from __future__ import annotations
import math
from dataclasses import dataclass, field
from typing import Optional


# ─── Section Properties ───────────────────────────────────────────────────────

@dataclass
class RectSection:
    """Rectangular prismatic section."""
    name:  str
    b:     float   # width  [mm]
    d:     float   # depth  [mm]

    # Derived properties (mm units, converted to m² / m⁴ for STAAD)
    @property
    def b_m(self) -> float: return self.b / 1000.0
    @property
    def d_m(self) -> float: return self.d / 1000.0
    @property
    def area(self) -> float:
        """Cross-sectional area [m²]."""
        return self.b_m * self.d_m
    @property
    def Iz(self) -> float:
        """Moment of inertia about z-axis (strong axis) [m⁴]."""
        return (self.b_m * self.d_m**3) / 12.0
    @property
    def Iy(self) -> float:
        """Moment of inertia about y-axis (weak axis) [m⁴]."""
        return (self.d_m * self.b_m**3) / 12.0
    @property
    def J(self) -> float:
        """Torsional constant (approximate for rectangle) [m⁴]."""
        # Bredt approximation for solid rectangle
        a, b = max(self.b_m, self.d_m), min(self.b_m, self.d_m)
        return (a * b**3) * (1/3 - 0.21 * (b/a) * (1 - b**4 / (12 * a**4)))
    @property
    def Av_y(self) -> float:
        """Shear area in Y [m²]."""
        return 5/6 * self.b_m * self.d_m
    @property
    def Av_z(self) -> float:
        """Shear area in Z [m²]."""
        return 5/6 * self.b_m * self.d_m

    def summary(self) -> str:
        return (
            f"{self.name}:  b={self.b:.0f}mm × d={self.d:.0f}mm\n"
            f"  A  = {self.area:.6f} m²\n"
            f"  Iz = {self.Iz:.4e} m⁴\n"
            f"  Iy = {self.Iy:.4e} m⁴\n"
            f"  J  = {self.J:.4e} m⁴\n"
        )

    def __repr__(self):
        return f"RectSection({self.name}: {self.b}×{self.d} mm)"


class SectionProperties:
    """Manages column and beam section definitions."""

    def __init__(self):
        self.column: Optional[RectSection] = None
        self.beam:   Optional[RectSection] = None

    def set_column(self, b: float, d: float) -> None:
        if b <= 0 or d <= 0:
            raise ValueError("Column dimensions must be positive.")
        if b > 3000 or d > 3000:
            raise ValueError("Column dimensions seem unreasonably large (> 3000 mm).")
        self.column = RectSection("COLUMN", b, d)

    def set_beam(self, b: float, d: float) -> None:
        if b <= 0 or d <= 0:
            raise ValueError("Beam dimensions must be positive.")
        if b > 3000 or d > 6000:
            raise ValueError("Beam dimensions seem unreasonably large.")
        self.beam = RectSection("BEAM", b, d)

    def is_complete(self) -> bool:
        return self.column is not None and self.beam is not None

    def get_for_type(self, member_type: str) -> Optional[RectSection]:
        if member_type == "COLUMN":
            return self.column
        return self.beam

    def summary(self) -> str:
        lines = []
        if self.column:
            lines.append(self.column.summary())
        if self.beam:
            lines.append(self.beam.summary())
        return "\n".join(lines) or "No sections defined."

    def __repr__(self):
        return f"SectionProperties(column={self.column}, beam={self.beam})"


# ─── Material Properties ──────────────────────────────────────────────────────

@dataclass
class MaterialProperties:
    """Concrete material definition."""
    name:    str   = "CONCRETE"
    E:       float = 22360.0   # Elastic modulus [MPa]  = 4700√20
    nu:      float = 0.17      # Poisson's ratio
    density: float = 24.0      # Density [kN/m³]
    fc:      float = 20.0      # Compressive strength [MPa]
    alpha:   float = 1.0e-5    # Coefficient of thermal expansion [/°C]

    def set(self, name: str, E: float, nu: float,
            density: float, fc: float) -> None:
        if E <= 0:
            raise ValueError("Elastic modulus E must be positive.")
        if not (0 < nu < 0.5):
            raise ValueError("Poisson's ratio must be between 0 and 0.5.")
        if density <= 0:
            raise ValueError("Density must be positive.")
        if fc <= 0:
            raise ValueError("Compressive strength must be positive.")
        self.name    = name
        self.E       = E
        self.nu      = nu
        self.density = density
        self.fc      = fc
        # Auto-compute E from f'c if not overridden (ACI 318-19 Eq. 19.2.2.1b)
        # Only update if default E was used
        auto_E = 4700 * math.sqrt(fc)   # MPa
        if abs(E - 22360.0) < 1:        # user is using default → update
            self.E = auto_E

    @property
    def G(self) -> float:
        """Shear modulus [MPa]."""
        return self.E / (2 * (1 + self.nu))

    @property
    def E_Pa(self) -> float:
        """Elastic modulus in Pa."""
        return self.E * 1e6

    @property
    def density_kNm3(self) -> float:
        return self.density

    def summary(self) -> str:
        return (
            f"Material: {self.name}\n"
            f"  f'c = {self.fc:.1f} MPa\n"
            f"  E   = {self.E:.1f} MPa\n"
            f"  G   = {self.G:.1f} MPa\n"
            f"  ν   = {self.nu:.3f}\n"
            f"  ρ   = {self.density:.1f} kN/m³\n"
        )

    def __repr__(self):
        return (f"MaterialProperties({self.name}: "
                f"f'c={self.fc}MPa, E={self.E:.0f}MPa)")
