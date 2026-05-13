
import math
import re
from dataclasses import dataclass, asdict
from typing import Optional, List, Dict, Any
import pandas as pd


@dataclass
class Rule:
    rule_key: str
    category: str
    subcategory: str
    keywords: List[str]
    required_test: str
    basis_type: str
    base_qty: Optional[float]
    base_unit: Optional[str]
    need_source_count: bool = False
    need_shipment_count: bool = False
    need_lot_count: bool = False
    need_pouring_days: bool = False
    need_truck_count: bool = False
    need_thickness_count: bool = False
    rule_basis: str = ""
    notes: str = ""


RULES: List[Rule] = [
    Rule(
        rule_key="EXCAVATED_WASTE",
        category="Earthwork",
        subcategory="Waste Excavated Materials",
        keywords=["unsuitable excavation", "waste excavated"],
        required_test="Grading Test; Plasticity Test; Organic Content",
        basis_type="PER_3000_M3_PER_SOURCE",
        base_qty=3000,
        base_unit="m3",
        need_source_count=True,
        rule_basis="One (1) for every 3,000 m³ per source or fraction thereof",
        notes="Based on visible DPWH MTR earthwork pages."
    ),
    Rule(
        rule_key="SUBGRADE_INCORPORATED",
        category="Earthwork",
        subcategory="Excavated Materials to be Incorporated",
        keywords=["subgrade preparation", "unsuitable material", "incorporated into the works"],
        required_test="Grading Test; Plasticity Test; Compaction Test; Organic Content; CBR; FDT",
        basis_type="MIXED_SUBGRADE",
        base_qty=None,
        base_unit=None,
        need_source_count=True,
        rule_basis="Volumetric tests: 1 per 3,000 m³/source; FDT: 1 group per 1,000 m²/layer",
        notes="Needs both volume and area/layer data for full automation."
    ),
    Rule(
        rule_key="BASE_COURSE_300",
        category="Road / Siteworks",
        subcategory="Base / Subbase Course Materials",
        keywords=["aggregate subbase", "aggregate base course", "base course", "subbase course"],
        required_test="Grading Test; Plasticity Test",
        basis_type="PER_300_M3_PER_SOURCE",
        base_qty=300,
        base_unit="m3",
        need_source_count=True,
        rule_basis="One (1) for every 300 m³ per source or fraction thereof",
        notes="Current encoded sample rule."
    ),
    Rule(
        rule_key="PCCP",
        category="Concrete",
        subcategory="Concrete",
        keywords=["portland cement concrete pavement", "pccp", "concrete pavement", "unreinforced"],
        required_test="Compressive Strength Test / Slump Test / component material tests",
        basis_type="CONCRETE_COMPLEX",
        base_qty=None,
        base_unit=None,
        need_pouring_days=True,
        need_truck_count=True,
        rule_basis="Concrete compressive test is per 75 m³/class/day; slump per truck; components by their own rules",
        notes="Needs m³ conversion, truck count, pouring days, and possibly class split."
    ),
    Rule(
        rule_key="REBAR",
        category="Reinforced Concrete",
        subcategory="Reinforcing Steel",
        keywords=["reinforcing steel", "rebar", "deformed bar"],
        required_test="Quality Test",
        basis_type="PER_10000_KG_PER_SOURCE",
        base_qty=10000,
        base_unit="kg",
        need_source_count=True,
        rule_basis="One (1) for every 10,000 kg for each size/source or fraction thereof",
        notes="Split rows by bar size for best results."
    ),
    Rule(
        rule_key="CHB",
        category="Masonry",
        subcategory="Concrete Hollow Blocks",
        keywords=["concrete hollow block", "chb"],
        required_test="Quality Test",
        basis_type="CHB_COMPLEX",
        base_qty=10000,
        base_unit="units",
        rule_basis="1 for every 10,000 units or fraction; 2 if >10,000 and <100,000; +1 per 50,000 units over 100,000",
        notes='100 mm = 4", 150 mm = 6".'
    ),
    Rule(
        rule_key="PAINT",
        category="Finishes",
        subcategory="Paint",
        keywords=["paint", "thermoplastic pavement markings", "reflectorized thermoplastic"],
        required_test="Quality Test",
        basis_type="PER_100_CANS",
        base_qty=100,
        base_unit="cans",
        rule_basis="One (1) for every 100 cans or fraction thereof",
        notes="Only applies where quantity is in cans. Area-based paint needs manual conversion unless can count is supplied."
    ),
]


def normalize(text: Any) -> str:
    return re.sub(r"\s+", " ", str(text or "").strip().lower())


def ceil_div(qty: float, base: float) -> int:
    if qty is None or pd.isna(qty):
        return 0
    return int(math.ceil(float(qty) / float(base)))


def match_rule(description: str) -> Optional[Rule]:
    desc = normalize(description)
    best_rule = None
    best_score = 0
    for rule in RULES:
        score = sum(1 for kw in rule.keywords if kw in desc)
        if score > best_score:
            best_score = score
            best_rule = rule
    return best_rule if best_score > 0 else None


def compute_tests(row: pd.Series, rule: Rule) -> Dict[str, Any]:
    qty = row.get("Quantity")
    source_count = row.get("Source Count", 1)
    shipment_count = row.get("Shipment Count", 1)
    lot_count = row.get("Lot Count", 1)
    pouring_days = row.get("Pouring Days")
    truck_count = row.get("Truck Count")
    area_m2 = row.get("Area (m2)")
    layer_count = row.get("No. of 200mm Layers")
    unit = normalize(row.get("Unit"))

    # Default assumptions if blank and needed
    source_count = 1 if pd.isna(source_count) or source_count in ("", None) else float(source_count)
    shipment_count = 1 if pd.isna(shipment_count) or shipment_count in ("", None) else float(shipment_count)
    lot_count = 1 if pd.isna(lot_count) or lot_count in ("", None) else float(lot_count)

    out = {
        "Category": rule.category,
        "Subcategory": rule.subcategory,
        "Required Test": rule.required_test,
        "Rule Basis": rule.rule_basis,
        "No. of Tests": None,
        "Remarks": "",
        "Review Status": "OK",
        "Rule Key": rule.rule_key,
    }

    if rule.basis_type == "PER_3000_M3_PER_SOURCE":
        if unit not in ("cu.m.", "m3", "cubic meter", "cubic meters"):
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Expected m³ quantity."
        else:
            out["No. of Tests"] = ceil_div(qty, rule.base_qty) * int(source_count)
            out["Remarks"] = f"Computed using {int(source_count)} source(s)."

    elif rule.basis_type == "PER_300_M3_PER_SOURCE":
        if unit not in ("cu.m.", "m3", "cubic meter", "cubic meters"):
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Expected m³ quantity."
        else:
            out["No. of Tests"] = ceil_div(qty, rule.base_qty) * int(source_count)
            out["Remarks"] = f"Computed using {int(source_count)} source(s)."

    elif rule.basis_type == "PER_10000_KG_PER_SOURCE":
        if unit not in ("kg", "kilogram", "kilograms"):
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Expected kg quantity and split by size."
        else:
            out["No. of Tests"] = ceil_div(qty, rule.base_qty) * int(source_count)
            out["Remarks"] = f"Computed using {int(source_count)} source(s)."

    elif rule.basis_type == "PER_100_CANS":
        if "can" not in unit:
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Rule is per 100 cans; convert project quantity to can count."
        else:
            out["No. of Tests"] = ceil_div(qty, rule.base_qty)

    elif rule.basis_type == "CHB_COMPLEX":
        if unit not in ("pcs", "pc", "each", "units", "unit"):
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Expected unit count for CHB."
        else:
            q = float(qty)
            if q <= 10000:
                n = 1
            elif q < 100000:
                n = 2
            else:
                n = 2 + int(math.ceil((q - 100000) / 50000))
            out["No. of Tests"] = n

    elif rule.basis_type == "MIXED_SUBGRADE":
        have_area = not pd.isna(area_m2)
        have_layers = not pd.isna(layer_count)
        have_volume = unit in ("cu.m.", "m3", "cubic meter", "cubic meters")
        if have_volume and have_area and have_layers:
            volumetric_tests = ceil_div(qty, 3000) * int(source_count)
            fdt_tests = ceil_div(float(area_m2) / 1000) * int(layer_count)
            out["No. of Tests"] = volumetric_tests + fdt_tests
            out["Remarks"] = f"Includes {volumetric_tests} volumetric test set(s) + {fdt_tests} FDT group(s)."
        else:
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Needs m³ quantity plus area and layer count for full computation."

    elif rule.basis_type == "CONCRETE_COMPLEX":
        if unit in ("sq.m.", "m2", "square meter", "square meters"):
            # Try transparent conversion if thickness present in description
            desc = normalize(row.get("Description"))
            m = re.search(r"0\.(\d+)\s*m", desc)
            qty_m3 = None
            if m:
                thickness = float("0." + m.group(1))
                qty_m3 = float(qty) * thickness
            if qty_m3 is not None and not pd.isna(pouring_days) and not pd.isna(truck_count):
                comp = ceil_div(qty_m3, 75) * int(float(pouring_days))
                slump = int(float(truck_count))
                out["No. of Tests"] = comp + slump
                out["Remarks"] = f"Computed transparently from {qty_m3:.2f} m³, {int(float(pouring_days))} pouring day(s), {int(float(truck_count))} truck(s). Component-material tests not added."
                out["Review Status"] = "MANUAL REVIEW"
            else:
                out["Review Status"] = "MANUAL REVIEW"
                out["Remarks"] = "Needs pouring days and truck count; component-material tests also separate."
        else:
            out["Review Status"] = "MANUAL REVIEW"
            out["Remarks"] = "Concrete rule needs m³ or transparent m²-to-m³ conversion plus truck/day inputs."

    else:
        out["Review Status"] = "MANUAL REVIEW"
        out["Remarks"] = "Rule basis not implemented."

    return out


def analyze_items(df: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, row in df.iterrows():
        rule_key_override = row.get("Rule Key Override")
        rule = None
        if pd.notna(rule_key_override) and str(rule_key_override).strip():
            rule = next((r for r in RULES if r.rule_key == str(rule_key_override).strip()), None)
        if rule is None:
            rule = match_rule(row.get("Description", ""))

        base = {
            "Item No.": row.get("Item No."),
            "Description": row.get("Description"),
            "Unit": row.get("Unit"),
            "Quantity": row.get("Quantity"),
        }

        if rule is None:
            rows.append({
                **base,
                "Category": None,
                "Subcategory": None,
                "Required Test": None,
                "Rule Basis": None,
                "No. of Tests": None,
                "Remarks": "No rule matched from current Python rule set.",
                "Review Status": "NO MATCH",
                "Rule Key": None,
            })
        else:
            rows.append({**base, **compute_tests(row, rule)})
    return pd.DataFrame(rows)


def sample_input() -> pd.DataFrame:
    data = [
        {"Item No.": "B.5", "Description": "Project Billboard / Signboard", "Unit": "each", "Quantity": 3},
        {"Item No.": "B.7(2)", "Description": "Occupational Safety and Health Program", "Unit": "l.s.", "Quantity": 1},
        {"Item No.": "B.8(2)", "Description": "Traffic Management", "Unit": "l.s.", "Quantity": 1},
        {"Item No.": "B.9", "Description": "Mobilization / Demobilization", "Unit": "l.s.", "Quantity": 1},
        {"Item No.": "101(3)c1", "Description": "Removal of Actual Structures/Obstruction, 0.05 m thick ACP", "Unit": "sq.m.", "Quantity": 15953},
        {"Item No.": "101(3)b6", "Description": "Removal of Actual Structures/Obstruction, 0.3 m thick PCCP (Unreinforced)", "Unit": "sq.m.", "Quantity": 8257},
        {"Item No.": "102(1)", "Description": "Unsuitable Excavation", "Unit": "cu.m.", "Quantity": 2064, "Source Count": 1},
        {"Item No.": "105(1)c", "Description": "Subgrade Preparation, Unsuitable Material", "Unit": "sq.m.", "Quantity": 8257, "Area (m2)": 8257, "Source Count": 1},
        {"Item No.": "200(1)", "Description": "Aggregate Subbase Course (for Intermittent Reblocking)", "Unit": "cu.m.", "Quantity": 1239, "Source Count": 1},
        {"Item No.": "201(1)", "Description": "Aggregate Base Course (for Reblocking)", "Unit": "cu.m.", "Quantity": 826, "Source Count": 1},
        {"Item No.": "302(2)", "Description": "Emulsified Asphalt", "Unit": "sq.m.", "Quantity": 15953},
        {"Item No.": "310(1)e", "Description": "Bituminous Concrete Surface Wearing Course, Hot-Laid, 50mm", "Unit": "sq.m.", "Quantity": 15953},
        {"Item No.": "311(1)f3", "Description": "Portland Cement Concrete Pavement (Unreinforced), 0.30 m thick, 3 days", "Unit": "sq.m.", "Quantity": 8257, "Pouring Days": 3},
        {"Item No.": "504(3)c", "Description": "Cleaning culvert pipe in place, 910 mm dia. half-silted", "Unit": "l.m.", "Quantity": 1777},
        {"Item No.": "612(1)", "Description": "Reflectorized Thermoplastic Pavement Markings White", "Unit": "sq.m.", "Quantity": 678},
        {"Item No.": "612(2)", "Description": "Reflectorized Thermoplastic Pavement Markings Yellow", "Unit": "sq.m.", "Quantity": 71},
    ]
    return pd.DataFrame(data)


def rules_dataframe() -> pd.DataFrame:
    return pd.DataFrame([asdict(r) for r in RULES])


def export_workbook(input_df: pd.DataFrame, output_path: str) -> None:
    result_df = analyze_items(input_df)
    review_df = result_df[result_df["Review Status"] != "OK"].copy()

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        input_df.to_excel(writer, sheet_name="Input", index=False)
        rules_dataframe().to_excel(writer, sheet_name="Rules_Reference", index=False)
        result_df.to_excel(writer, sheet_name="Final_Output", index=False)
        review_df.to_excel(writer, sheet_name="Review_Errors", index=False)

        wb = writer.book
        for ws in wb.worksheets:
            ws.freeze_panes = "A2"
            for col in ws.columns:
                max_len = 0
                col_letter = col[0].column_letter
                for cell in col:
                    try:
                        max_len = max(max_len, len(str(cell.value)) if cell.value is not None else 0)
                    except Exception:
                        pass
                ws.column_dimensions[col_letter].width = min(max(max_len + 2, 12), 45)


if __name__ == "__main__":
    # Demo run using the sample list from the screenshot/reference.
    df = sample_input()
    export_workbook(df, "sample.xlsx")
    print("Created sample.xlsx")
