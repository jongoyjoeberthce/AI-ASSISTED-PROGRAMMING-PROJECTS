"""
export.py – OpenSTAAD interaction and .std file writer

This module provides two export paths:
  1. OpenSTAADPy COM automation (requires STAAD.Pro 2025 installed)
  2. Fallback: write a native STAAD .std text file directly

The STAADExporter auto-detects whether OpenSTAADPy is available and
uses the COM path if possible; otherwise it falls back to the text writer.
"""
from __future__ import annotations

import os
import datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from model     import StructuralModel
    from properties import SectionProperties, MaterialProperties
    from loads      import LoadManager


# ─── OpenSTAAD COM Bridge ──────────────────────────────────────────────────────

def _try_openstaad_com():
    """
    Attempt to connect to STAAD.Pro 2025 via the OpenSTAAD COM interface.
    Returns the root OpenSTAAD object, or None if unavailable.
    """
    try:
        import win32com.client as win32
        # OpenSTAAD 2025 ProgID
        os_obj = win32.Dispatch("StaadPro.OpenSTAAD")
        return os_obj
    except Exception:
        pass
    try:
        # Fallback via openstaadpy wrapper
        from openstaadpy.os_analytical import osview
        os_obj = osview.OpenSTAAD()
        return os_obj
    except Exception:
        return None


class OpenSTAADInterface:
    """
    Thin wrapper around the OpenSTAAD COM object that exposes only the
    operations this application needs.  Mirrors the OpenSTAADPy API as
    documented in Bentley's STAAD.Pro 2025 SDK.
    """

    def __init__(self, com_obj):
        self._os = com_obj
        self._geo = getattr(com_obj, "Geometry",    com_obj)
        self._prop= getattr(com_obj, "Property",    com_obj)
        self._load= getattr(com_obj, "Load",        com_obj)
        self._gen = getattr(com_obj, "General",     com_obj)

    def new_model(self, path: str, unit_length: str = "m",
                  unit_force: str = "kN") -> None:
        """Create a new blank STAAD model file."""
        try:
            self._gen.NewSTAADFile(path, unit_length, unit_force)
        except AttributeError:
            # Older API
            self._os.NewFile(path)

    def add_node(self, node_id: int, x: float, y: float, z: float) -> None:
        """Add a single node."""
        self._geo.AddNode(node_id, x, y, z)

    def add_beam(self, member_id: int,
                 start_node: int, end_node: int) -> None:
        """Add a beam/column element."""
        self._geo.AddBeam(member_id, start_node, end_node)

    def assign_prismatic_section(self, member_ids: list,
                                 prop_id: int, section_type: str,
                                 YD: float, ZD: float) -> None:
        """
        Assign rectangular prismatic section.
          YD = depth in local Y [m]
          ZD = width in local Z [m]
        """
        ids_arr = list(member_ids)
        self._prop.SetPrismaticSection(
            prop_id, "RECT", YD, ZD, ids_arr
        )

    def assign_material(self, member_ids: list, E: float,
                        nu: float, density: float) -> None:
        """Assign material constants."""
        ids_arr = list(member_ids)
        self._prop.SetMaterial(E, nu, density, ids_arr)

    def assign_stiffness_modifier(self, member_id: int,
                                   mods: dict) -> None:
        """Apply member property reduction factors."""
        # OpenSTAAD API: SetMemberPropertyReduction(memberID, Ax, Ay, Az, Ix, Iy, Iz)
        self._prop.SetMemberPropertyReduction(
            member_id,
            mods.get("col_ax", 1.0),   # Ax
            mods.get("bm_av",  1.0),   # Ay
            mods.get("bm_av",  1.0),   # Az
            1.0,                        # Ix (torsion - keep)
            mods.get("beam_iy", 1.0),  # Iy
            mods.get("beam_iz", 1.0),  # Iz
        )

    def add_load_case(self, case_id: int, title: str) -> None:
        self._load.AddLoadCase(case_id, title)

    def add_selfweight(self, case_id: int,
                       direction: str, factor: float) -> None:
        dir_map = {"X": 1, "Y": 2, "Z": 3}
        d = dir_map.get(direction.upper(), 2)
        self._load.AddSelfWeightLoad(case_id, d, factor)

    def save(self) -> None:
        try:
            self._gen.SaveFile()
        except AttributeError:
            self._os.SaveFile()

    def close(self) -> None:
        try:
            self._os.CloseSTAAD(False)
        except Exception:
            pass


# ─── .std Text Writer ─────────────────────────────────────────────────────────

class STDTextWriter:
    """
    Generates a STAAD.Pro native text (.std) file without requiring
    STAAD.Pro to be installed.  The file can be opened directly in
    STAAD.Pro 2025.
    """

    def write(self,
              model:     "StructuralModel",
              sections:  "SectionProperties",
              material:  "MaterialProperties",
              loads:     "LoadManager",
              path:      str) -> None:

        lines = []

        # ── Header ──────────────────────────────────────────────────────────
        lines += [
            "STAAD SPACE",
            f"* Generated by STAAD.Pro 2025 Automation Tool",
            f"* Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"* Nodes: {len(model.nodes)}  Members: {len(model.members)}",
            "UNIT METER KN",
            "JOINT COORDINATES",
        ]

        # ── Nodes ────────────────────────────────────────────────────────────
        for nid, n in sorted(model.nodes.items()):
            lines.append(f"{nid:>6} {n.x:>12.5f} {n.y:>12.5f} {n.z:>12.5f}")

        # ── Members ──────────────────────────────────────────────────────────
        lines.append("MEMBER INCIDENCES")
        for mid, m in sorted(model.members.items()):
            lines.append(f"{mid:>6} {m.start_node:>6} {m.end_node:>6}")

        # ── Supports (pin all base nodes = Y=0) ──────────────────────────────
        base_nodes = [nid for nid, n in model.nodes.items()
                      if abs(n.y) < 1e-6]
        if base_nodes:
            lines.append("SUPPORTS")
            ids_str = " ".join(str(n) for n in sorted(base_nodes))
            lines.append(f"{ids_str} FIXED")

        # ── Member Properties ─────────────────────────────────────────────
        lines.append("MEMBER PROPERTY")
        beam_ids   = [m.id for m in model.get_beams()]
        col_ids    = [m.id for m in model.get_columns()]

        if sections and sections.column and col_ids:
            sec = sections.column
            ids_str = _range_compress(col_ids)
            lines.append(
                f"{ids_str} PRISMATIC YD {sec.d_m:.5f} ZD {sec.b_m:.5f}"
            )

        if sections and sections.beam and beam_ids:
            sec = sections.beam
            ids_str = _range_compress(beam_ids)
            lines.append(
                f"{ids_str} PRISMATIC YD {sec.d_m:.5f} ZD {sec.b_m:.5f}"
            )

        # ── Constants (Material) ──────────────────────────────────────────
        lines.append("CONSTANTS")
        all_ids = _range_compress(sorted(model.members.keys()))
        if material:
            lines += [
                f"E {material.E * 1000:.1f} MEMB {all_ids}",         # kN/m²
                f"POISSON {material.nu:.4f} MEMB {all_ids}",
                f"DENSITY {material.density:.2f} MEMB {all_ids}",     # kN/m³
                f"ALPHA {material.alpha:.2e} MEMB {all_ids}",
            ]

        # ── Member Property Modifiers (Stiffness) ────────────────────────
        if model.stiffness_mods:
            mods = model.stiffness_mods
            lines.append("MEMBER PROPERTY MODIFICATION")

            if col_ids:
                col_str = _range_compress(col_ids)
                lines.append(
                    f"MEMB {col_str} IZ {mods.get('col_iz', 0.70):.3f} "
                    f"IY {mods.get('col_iy', 0.70):.3f} "
                    f"AX {mods.get('col_ax', 0.80):.3f}"
                )
            if beam_ids:
                bm_str = _range_compress(beam_ids)
                lines.append(
                    f"MEMB {bm_str} IZ {mods.get('beam_iz', 0.35):.3f} "
                    f"IY {mods.get('beam_iy', 0.35):.3f} "
                    f"AV {mods.get('bm_av', 1.00):.3f}"
                )

        # ── Slab panel group comments ─────────────────────────────────────
        if model.slab_panels:
            lines.append("*")
            lines.append("* SLAB PANEL CLASSIFICATION")
            for panel in model.slab_panels:
                lines.append(
                    f"* Story {panel['story']} Bay ({panel['bay_x']},{panel['bay_z']}) "
                    f"→ {panel['type'].upper()}"
                )

        # ── Loads ─────────────────────────────────────────────────────────
        if loads and loads.cases:
            lines.append("LOADING")
            for case in loads.all_cases():
                lines.append(f"LOAD {case.id} LOADTYPE Dead TITLE {case.title}")
                if case.selfweight:
                    lines.append(
                        f"SELFWEIGHT Y {case.selfweight.factor:.2f}"
                    )
                for nl in case.nodal_loads:
                    lines.append(
                        f"JOINT LOAD"
                    )
                    lines.append(
                        f"{nl.node_id} FX {nl.Fx:.3f} FY {nl.Fy:.3f} "
                        f"FZ {nl.Fz:.3f} MX {nl.Mx:.3f} MY {nl.My:.3f} "
                        f"MZ {nl.Mz:.3f}"
                    )
                for ml in case.member_udls:
                    lines.append(
                        f"MEMBER LOAD"
                    )
                    lines.append(
                        f"{ml.member_id} UNI {ml.direction} {ml.w:.3f}"
                    )
                for fl in case.floor_loads:
                    lines.append(
                        f"* Floor UDL: {fl.intensity:.3f} kN/m² in {fl.direction}"
                    )

        # ── Analysis ──────────────────────────────────────────────────────
        lines += [
            "PERFORM ANALYSIS",
            "FINISH",
        ]

        # ── Write file ────────────────────────────────────────────────────
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write("\n".join(lines) + "\n")


# ─── Main Exporter ────────────────────────────────────────────────────────────

class STAADExporter:
    """
    Orchestrates the export workflow:
      1. Try OpenSTAAD COM automation (live STAAD.Pro session)
      2. Fall back to STDTextWriter (.std text file)
    """

    def export(self,
               model:    "StructuralModel",
               sections: "SectionProperties",
               material: "MaterialProperties",
               loads:    "LoadManager",
               path:     str) -> None:

        com = _try_openstaad_com()

        if com is not None:
            self._export_via_com(com, model, sections, material, loads, path)
        else:
            self._export_via_text(model, sections, material, loads, path)

    # ── COM path ──────────────────────────────────────────────────────────────

    def _export_via_com(self, com_obj, model, sections, material, loads, path):
        osi = OpenSTAADInterface(com_obj)
        try:
            osi.new_model(path)

            # Nodes
            for nid, n in model.nodes.items():
                osi.add_node(nid, n.x, n.y, n.z)

            # Members
            for mid, m in model.members.items():
                osi.add_beam(mid, m.start_node, m.end_node)

            # Sections
            col_ids  = [m.id for m in model.get_columns()]
            bm_ids   = [m.id for m in model.get_beams()]
            if sections.column and col_ids:
                sec = sections.column
                osi.assign_prismatic_section(
                    col_ids, 1, "RECT", sec.d_m, sec.b_m)
            if sections.beam and bm_ids:
                sec = sections.beam
                osi.assign_prismatic_section(
                    bm_ids, 2, "RECT", sec.d_m, sec.b_m)

            # Material
            all_ids = list(model.members.keys())
            osi.assign_material(
                all_ids,
                material.E * 1000,    # MPa → kN/m²
                material.nu,
                material.density,
            )

            # Stiffness modifiers
            if model.stiffness_mods:
                for m in model.get_columns():
                    col_mods = {k: v for k, v in model.stiffness_mods.items()
                                if "col" in k}
                    osi.assign_stiffness_modifier(m.id, col_mods)
                for m in model.get_beams():
                    bm_mods = {k: v for k, v in model.stiffness_mods.items()
                               if "beam" in k or "bm" in k}
                    osi.assign_stiffness_modifier(m.id, bm_mods)

            # Loads
            for case in loads.all_cases():
                osi.add_load_case(case.id, case.title)
                if case.selfweight:
                    osi.add_selfweight(
                        case.id,
                        case.selfweight.direction,
                        case.selfweight.factor,
                    )

            osi.save()
        finally:
            osi.close()

    # ── Text fallback ─────────────────────────────────────────────────────────

    def _export_via_text(self, model, sections, material, loads, path):
        writer = STDTextWriter()
        writer.write(model, sections, material, loads, path)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _range_compress(ids: list) -> str:
    """
    Compress a sorted list of ints to STAAD range notation.
    E.g. [1,2,3,5,6] → "1 TO 3 5 TO 6"
    """
    if not ids:
        return ""
    ids = sorted(ids)
    parts = []
    start = prev = ids[0]
    for i in ids[1:]:
        if i == prev + 1:
            prev = i
        else:
            parts.append(f"{start} TO {prev}" if prev > start else str(start))
            start = prev = i
    parts.append(f"{start} TO {prev}" if prev > start else str(start))
    return " ".join(parts)
