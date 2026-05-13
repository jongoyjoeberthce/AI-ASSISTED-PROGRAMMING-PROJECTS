"""
model.py – Node/Member generation and structural model container
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any
import math


# ─── Data Classes ─────────────────────────────────────────────────────────────

@dataclass
class Node:
    id: int
    x: float
    y: float
    z: float

    def distance_to(self, other: "Node") -> float:
        return math.sqrt((self.x - other.x)**2 +
                         (self.y - other.y)**2 +
                         (self.z - other.z)**2)

    def __repr__(self):
        return f"Node({self.id}: {self.x:.3f}, {self.y:.3f}, {self.z:.3f})"


@dataclass
class Member:
    id: int
    start_node: int
    end_node: int
    type: str = "BEAM"   # "BEAM" | "COLUMN"
    section_id: Optional[int] = None
    material_id: Optional[int] = None
    stiffness_mods: Optional[Dict[str, float]] = None

    def __repr__(self):
        return f"Member({self.id}: {self.start_node}→{self.end_node} [{self.type}])"


@dataclass
class SlabPanel:
    story: int
    bay_x: int
    bay_z: int
    slab_type: str = "two_way"   # "one_way" | "two_way"
    member_ids: List[int] = field(default_factory=list)


# ─── StructuralModel ──────────────────────────────────────────────────────────

class StructuralModel:
    """Central container for all structural data."""

    def __init__(self):
        self.nodes:    Dict[int, Node]   = {}
        self.members:  Dict[int, Member] = {}
        self.slab_panels: List[dict]     = []

        # State flags
        self.sections_assigned: bool  = False
        self.material_assigned: bool  = False
        self.loads_assigned:    bool  = False

        # Stored references (set by assign_* methods)
        self.sections  = None
        self.material  = None
        self.loads     = None
        self.stiffness_mods: Optional[dict] = None

    # ── Node management ───────────────────────────────────────────────────────

    def add_node(self, node: Node) -> None:
        if node.id in self.nodes:
            raise ValueError(f"Node {node.id} already exists. "
                             "Use a unique ID or remove the existing node first.")
        # Check for duplicate coordinates (tolerance = 1e-6 m)
        for existing in self.nodes.values():
            if existing.distance_to(node) < 1e-6:
                raise ValueError(
                    f"Node {node.id} coordinates ({node.x}, {node.y}, {node.z}) "
                    f"clash with existing Node {existing.id}.")
        self.nodes[node.id] = node

    def remove_node(self, node_id: int) -> None:
        if node_id not in self.nodes:
            raise KeyError(f"Node {node_id} not found.")
        # Remove dependent members
        dep = [mid for mid, m in self.members.items()
               if m.start_node == node_id or m.end_node == node_id]
        for mid in dep:
            del self.members[mid]
        del self.nodes[node_id]

    # ── Member management ─────────────────────────────────────────────────────

    def add_member(self, member: Member) -> None:
        if member.id in self.members:
            raise ValueError(f"Member {member.id} already exists.")
        if member.start_node not in self.nodes:
            raise KeyError(f"Start node {member.start_node} not defined.")
        if member.end_node not in self.nodes:
            raise KeyError(f"End node {member.end_node} not defined.")
        if member.start_node == member.end_node:
            raise ValueError("Start and end nodes must be different.")
        # Check zero-length
        n1 = self.nodes[member.start_node]
        n2 = self.nodes[member.end_node]
        if n1.distance_to(n2) < 1e-6:
            raise ValueError(f"Member {member.id} has near-zero length.")
        self.members[member.id] = member

    # ── Grid generator ────────────────────────────────────────────────────────

    def generate_grid(self,
                      bays_x: int, bays_z: int, stories: int,
                      spacing_x: float, spacing_z: float,
                      story_height: float) -> None:
        """
        Generate a regular 3-D frame grid.

        Grid coordinate system:
          X → along bays (horizontal)
          Y → along stories (vertical)
          Z → along depth bays (horizontal perpendicular)
        """
        node_id  = 1
        member_id = 1

        # Build node array [story][ix][iz]
        node_grid: List[List[List[int]]] = []

        for s in range(stories + 1):
            layer_x = []
            for ix in range(bays_x + 1):
                layer_z = []
                for iz in range(bays_z + 1):
                    x = ix * spacing_x
                    y = s  * story_height
                    z = iz * spacing_z
                    self.nodes[node_id] = Node(node_id, x, y, z)
                    layer_z.append(node_id)
                    node_id += 1
                layer_x.append(layer_z)
            node_grid.append(layer_x)

        # ── Columns (vertical members) ──
        for s in range(stories):
            for ix in range(bays_x + 1):
                for iz in range(bays_z + 1):
                    sn = node_grid[s][ix][iz]
                    en = node_grid[s + 1][ix][iz]
                    self.members[member_id] = Member(member_id, sn, en, "COLUMN")
                    member_id += 1

        # ── Beams X-direction ──
        for s in range(1, stories + 1):
            for ix in range(bays_x):
                for iz in range(bays_z + 1):
                    sn = node_grid[s][ix][iz]
                    en = node_grid[s][ix + 1][iz]
                    self.members[member_id] = Member(member_id, sn, en, "BEAM")
                    member_id += 1

        # ── Beams Z-direction ──
        for s in range(1, stories + 1):
            for ix in range(bays_x + 1):
                for iz in range(bays_z):
                    sn = node_grid[s][ix][iz]
                    en = node_grid[s][ix][iz + 1]
                    self.members[member_id] = Member(member_id, sn, en, "BEAM")
                    member_id += 1

    # ── Slab panels ───────────────────────────────────────────────────────────

    def add_slab_panel(self, panel: dict) -> None:
        self.slab_panels.append(panel)

    # ── Assignment methods ────────────────────────────────────────────────────

    def assign_sections(self, sections) -> None:
        self.sections = sections
        self.sections_assigned = True

    def assign_material(self, material) -> None:
        self.material = material
        self.material_assigned = True

    def assign_loads(self, loads) -> None:
        self.loads = loads
        self.loads_assigned = True

    def assign_stiffness_modifiers(self, mods: dict) -> None:
        for key, val in mods.items():
            if val < 0 or val > 2.0:
                raise ValueError(f"Stiffness modifier '{key}' = {val} is out of "
                                 "reasonable range [0, 2.0].")
        self.stiffness_mods = mods
        for m in self.members.values():
            m.stiffness_mods = mods.copy()

    # ── Validation ────────────────────────────────────────────────────────────

    def validate(self) -> List[str]:
        errors = []
        if not self.nodes:
            errors.append("No nodes defined.")
        if not self.members:
            errors.append("No members defined.")
        if not self.sections_assigned:
            errors.append("Section properties not assigned.")
        if not self.material_assigned:
            errors.append("Material properties not assigned.")
        if not self.loads_assigned:
            errors.append("Load cases not defined.")

        # Orphan nodes
        used_nodes = set()
        for m in self.members.values():
            used_nodes.add(m.start_node)
            used_nodes.add(m.end_node)
        orphans = set(self.nodes.keys()) - used_nodes
        if orphans:
            errors.append(f"Orphan nodes (not connected to any member): "
                          f"{sorted(orphans)}")

        # Duplicate member connectivity
        seen_pairs = set()
        for m in self.members.values():
            pair = (min(m.start_node, m.end_node),
                    max(m.start_node, m.end_node))
            if pair in seen_pairs:
                errors.append(f"Duplicate member connectivity: "
                              f"nodes {pair[0]}↔{pair[1]}")
            seen_pairs.add(pair)

        return errors

    # ── Utility ───────────────────────────────────────────────────────────────

    def clear(self) -> None:
        self.nodes.clear()
        self.members.clear()
        self.slab_panels.clear()
        self.sections_assigned = False
        self.material_assigned = False
        self.loads_assigned    = False
        self.sections          = None
        self.material          = None
        self.loads             = None
        self.stiffness_mods    = None

    def get_columns(self) -> List[Member]:
        return [m for m in self.members.values() if m.type == "COLUMN"]

    def get_beams(self) -> List[Member]:
        return [m for m in self.members.values() if m.type == "BEAM"]

    def bbox(self):
        """Return (min_x, min_y, min_z, max_x, max_y, max_z)."""
        xs = [n.x for n in self.nodes.values()]
        ys = [n.y for n in self.nodes.values()]
        zs = [n.z for n in self.nodes.values()]
        return min(xs), min(ys), min(zs), max(xs), max(ys), max(zs)

    def __repr__(self):
        return (f"StructuralModel("
                f"{len(self.nodes)} nodes, "
                f"{len(self.members)} members, "
                f"{len(self.slab_panels)} slab panels)")
