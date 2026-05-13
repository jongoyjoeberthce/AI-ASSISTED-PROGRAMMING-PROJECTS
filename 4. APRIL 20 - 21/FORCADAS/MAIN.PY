import pandas as pd
import math

# ============================================================
# MATERIAL DATABASE (Tests + Standards + Frequency Rules)
# Based on international practices (ASTM, ISO, AASHTO)
# ============================================================
MATERIAL_RULES = {
    "concrete": {
        "keywords": ["concrete"],
        "tests": ["Slump Test", "Compressive Strength Test"],
        "standards": ["ASTM C143", "ASTM C39"],
        "frequency": {"unit": "m3", "rate": 75}
    },
    "cement": {
        "keywords": ["cement"],
        "tests": ["Compressive Strength Test", "Fineness Test"],
        "standards": ["ASTM C109", "ASTM C204"],
        "frequency": {"unit": "bags", "rate": 200}
    },
    "steel": {
        "keywords": ["steel", "rebar"],
        "tests": ["Tensile Test", "Bend Test"],
        "standards": ["ASTM A615", "ISO 6892"],
        "frequency": {"unit": "tons", "rate": 10}
    },
    "aggregate": {
        "keywords": ["aggregate", "sand", "gravel"],
        "tests": ["Sieve Analysis", "Specific Gravity Test"],
        "standards": ["ASTM C136", "ASTM C127"],
        "frequency": {"unit": "m3", "rate": 100}
    },
    "asphalt": {
        "keywords": ["asphalt", "bitumen"],
        "tests": ["Marshall Stability Test", "Penetration Test"],
        "standards": ["ASTM D6927", "AASHTO T245"],
        "frequency": {"unit": "tons", "rate": 50}
    }
}

# ============================================================
# FUNCTION: Detect Material Type
# ============================================================
def detect_material(description):
    desc = description.lower()
    for material, data in MATERIAL_RULES.items():
        for keyword in data["keywords"]:
            if keyword in desc:
                return material
    return None


# ============================================================
# FUNCTION: Assign Tests & Standards
# ============================================================
def get_test_info(material):
    if material in MATERIAL_RULES:
        data = MATERIAL_RULES[material]
        return data["tests"], data["standards"], data["frequency"]
    return ["Check manually"], ["Check manually"], None


# ============================================================
# FUNCTION: Compute Number of Tests
# ============================================================
def compute_test_count(quantity, unit, freq_rule):
    if freq_rule is None:
        return "-", "-"

    expected_unit = freq_rule["unit"]
    rate = freq_rule["rate"]

    # Normalize unit string
    unit = unit.lower().strip()

    if expected_unit not in unit:
        return "Unit mismatch", f"Expected unit: {expected_unit}"

    if pd.isna(quantity):
        return "Quantity required", f"1 test per {rate} {expected_unit}"

    num_tests = math.ceil(quantity / rate)
    return num_tests, f"1 test per {rate} {expected_unit}"


# ============================================================
# MAIN FUNCTION: Analyze BoM
# ============================================================
def analyze_bom(file_path):
    # Load file
    if file_path.endswith(".csv"):
        df = pd.read_csv(file_path)
    elif file_path.endswith(".xlsx"):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file format. Use CSV or XLSX.")

    # Clean column names
    df.columns = df.columns.str.strip()

    # Validate required columns
    required_cols = ["Item Description", "Quantity", "Unit"]
    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    results = []

    # Process each row
    for _, row in df.iterrows():
        desc = str(row["Item Description"])
        qty = row["Quantity"]
        unit = str(row["Unit"])

        material = detect_material(desc)

        if material:
            tests, standards, freq_rule = get_test_info(material)
            num_tests, freq_desc = compute_test_count(qty, unit, freq_rule)
            material_name = material.capitalize()
        else:
            material_name = "Not Identified"
            tests = ["Check manually"]
            standards = ["Check manually"]
            num_tests = "-"
            freq_desc = "-"

        results.append({
            "Item Description": desc,
            "Material Type": material_name,
            "Quantity": qty,
            "Unit": unit,
            "Required Tests": ", ".join(tests),
            "Standards": ", ".join(standards),
            "Frequency Rule": freq_desc,
            "Number of Required Tests": num_tests
        })

    output_df = pd.DataFrame(results)

    # Save to Excel
    output_df.to_excel("material_testing_plan.xlsx", index=False)

    return output_df


# ============================================================
# USAGE
# ============================================================
if __name__ == "__main__":
    file_path = "bom.xlsx"  # Change to your file path

    result = analyze_bom(file_path)

    print("\n=== MATERIAL TESTING PLAN ===\n")
    print(result.to_string(index=False))
