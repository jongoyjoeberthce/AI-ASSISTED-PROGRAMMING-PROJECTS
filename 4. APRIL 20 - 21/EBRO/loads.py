"""
loads.py – Load case definitions and self-weight
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class SelfWeight:
    """Self-weight loading (global direction)."""
    factor: float   = -1.0    # negative = downward in Y
    direction: str  = "Y"     # global axis


@dataclass
class NodalLoad:
    node_id: int
    Fx: float = 0.0
    Fy: float = 0.0
    Fz: float = 0.0
    Mx: float = 0.0
    My: float = 0.0
    Mz: float = 0.0


@dataclass
class MemberUDL:
    """Uniformly distributed load on a member."""
    member_id: int
    w: float          # intensity [kN/m]
    direction: str    # "GY", "GX", "GZ", "Y", "X", "Z"
    start_dist: float = 0.0   # fractional [0,1]
    end_dist:   float = 1.0


@dataclass
class FloorLoad:
    """Floor/slab uniform area load."""
    intensity: float   # kN/m²
    direction: str = "GY"


@dataclass
class LoadCase:
    id:    int
    title: str
    selfweight: Optional[SelfWeight] = None
    nodal_loads: List[NodalLoad]  = field(default_factory=list)
    member_udls: List[MemberUDL]  = field(default_factory=list)
    floor_loads: List[FloorLoad]  = field(default_factory=list)

    def has_loading(self) -> bool:
        return (self.selfweight is not None or
                bool(self.nodal_loads)      or
                bool(self.member_udls)      or
                bool(self.floor_loads))


# ─── Load Manager ─────────────────────────────────────────────────────────────

class LoadManager:
    """Manages all load cases for the structural model."""

    def __init__(self):
        self.cases: Dict[int, LoadCase] = {}

    # ── Dead Load ─────────────────────────────────────────────────────────────

    def set_dead_load(self, case_id: int = 1,
                      title: str = "DEAD LOAD",
                      selfweight: bool = True,
                      sw_factor: float = 1.0) -> LoadCase:
        """Create / update the dead load case."""
        if sw_factor <= 0:
            raise ValueError("Self-weight factor must be positive.")

        case = LoadCase(id=case_id, title=title)
        if selfweight:
            case.selfweight = SelfWeight(
                factor=-1.0 * sw_factor,
                direction="Y"
            )
        self.cases[case_id] = case
        return case

    # ── Live Load ─────────────────────────────────────────────────────────────

    def add_live_load(self, case_id: int = 2,
                      title: str = "LIVE LOAD",
                      udl: float = 2.0) -> LoadCase:
        """Add a live load case with a floor UDL."""
        if udl < 0:
            raise ValueError("UDL intensity must be non-negative.")
        case = LoadCase(id=case_id, title=title)
        case.floor_loads.append(FloorLoad(intensity=-udl, direction="GY"))
        self.cases[case_id] = case
        return case

    # ── Generic helpers ───────────────────────────────────────────────────────

    def add_nodal_load(self, case_id: int, load: NodalLoad) -> None:
        if case_id not in self.cases:
            raise KeyError(f"Load case {case_id} not defined.")
        self.cases[case_id].nodal_loads.append(load)

    def add_member_udl(self, case_id: int, load: MemberUDL) -> None:
        if case_id not in self.cases:
            raise KeyError(f"Load case {case_id} not defined.")
        self.cases[case_id].member_udls.append(load)

    def get_case(self, case_id: int) -> Optional[LoadCase]:
        return self.cases.get(case_id)

    def all_cases(self) -> List[LoadCase]:
        return list(self.cases.values())

    def is_empty(self) -> bool:
        return len(self.cases) == 0

    def summary(self) -> str:
        lines = [f"Load Cases ({len(self.cases)}):"]
        for case in self.cases.values():
            lines.append(f"  Case {case.id}: {case.title}")
            if case.selfweight:
                lines.append(
                    f"    Self-weight: factor={case.selfweight.factor:.2f}"
                    f"  dir={case.selfweight.direction}")
            if case.nodal_loads:
                lines.append(f"    Nodal loads: {len(case.nodal_loads)}")
            if case.member_udls:
                lines.append(f"    Member UDLs: {len(case.member_udls)}")
            if case.floor_loads:
                fl = case.floor_loads[0]
                lines.append(
                    f"    Floor load:  {fl.intensity:.2f} kN/m²  dir={fl.direction}")
        return "\n".join(lines)

    def __repr__(self):
        return f"LoadManager({len(self.cases)} cases)"
