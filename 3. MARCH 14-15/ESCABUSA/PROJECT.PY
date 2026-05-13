"""
STAAD.Pro – Rectangular Section Assigner & Analyzer
=====================================================
Workflow:
  1. Connects to the open STAAD.Pro model via openstaadpy
  2. Shows ALL members with their CURRENT section assignments
  3. You type a rectangular section size (B x D in model units)
  4. You choose which member numbers get that section
  5. Repeat steps 3-4 for as many sizes as you need
  6. Shows a final summary before applying
  7. Assigns sections, saves, updates, then runs analysis

Requirements:
  - STAAD.Pro installed and a model OPEN in the UI (Windows only)
  - pip install openstaadpy
"""

import sys
import time
from openstaadpy import os_analytical


# ─────────────────────────────────────────────────────────────────────────────
# 1. CONNECT
# ─────────────────────────────────────────────────────────────────────────────

def connect_to_staad():
    print("\n" + "=" * 64)
    print("   STAAD.Pro  –  Section Assigner & Analyzer")
    print("=" * 64)
    print("\n  Connecting to STAAD.Pro ...")
    try:
        staad_obj = os_analytical.connect()
        if staad_obj is None:
            sys.exit("\n  ERROR: connect() returned None.\n"
                     "  -> Make sure STAAD.Pro is running with a model open.\n")
        file_path = staad_obj.GetSTAADFile()
        print(f"  Connected  |  File: {file_path}\n")
        return staad_obj
    except Exception as exc:
        sys.exit(f"\n  ERROR: Could not connect to STAAD.Pro.\n  {exc}\n"
                 "  -> Make sure STAAD.Pro is running with a model open.\n")


# ─────────────────────────────────────────────────────────────────────────────
# 2. FETCH MEMBERS & CURRENT SECTIONS
# ─────────────────────────────────────────────────────────────────────────────

def get_member_ids(staad_obj):
    return list(staad_obj.Geometry.GetBeamList())


def get_current_sections(staad_obj, member_ids):
    """
    Returns dict: { member_id: { name, B, D, material } }
    Captures material name via GetBeamMaterialName() so it can be
    re-assigned after the section changes (assigning a new section
    removes the material assignment in STAAD.Pro).
    """
    info = {}
    for mid in member_ids:
        try:
            name = staad_obj.Property.GetBeamSectionName(mid)
        except Exception:
            name = "(none)"

        try:
            props = staad_obj.Property.GetBeamProperty(mid)
            B = props[0]
            D = props[1]
        except Exception:
            B, D = 0.0, 0.0

        try:
            material = staad_obj.Property.GetBeamMaterialName(mid)
        except Exception:
            material = None

        info[mid] = {
            "name":     name if name else "(none)",
            "B":        B,
            "D":        D,
            "material": material if material else None,
        }
    return info


# ─────────────────────────────────────────────────────────────────────────────
# 3. PRE-RUN REPORT
# ─────────────────────────────────────────────────────────────────────────────

def display_pre_run_report(member_ids, current_sections):
    print("─" * 80)
    print("  CURRENT SECTION ASSIGNMENTS  (before changes)")
    print("─" * 80)
    print(f"  {'Member':>8}  {'Section Name':<22}  {'B':>10}  {'D':>10}  {'Material':<20}")
    print(f"  {'-'*8}  {'-'*22}  {'-'*10}  {'-'*10}  {'-'*20}")

    for mid in member_ids:
        sec  = current_sections[mid]
        name = sec["name"]
        B    = sec["B"]
        D    = sec["D"]
        mat  = sec["material"] if sec["material"] else "(none)"
        if name == "(none)":
            print(f"  {mid:>8}  {'(no section)':^22}  {'--':>10}  {'--':>10}  {mat:<20}")
        else:
            print(f"  {mid:>8}  {name:<22}  {B:>10.4f}  {D:>10.4f}  {mat:<20}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# 4. INPUT HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def prompt_float(label, min_val=0.0001):
    while True:
        raw = input(f"    {label}: ").strip()
        try:
            val = float(raw)
            if val >= min_val:
                return val
            print(f"    Must be > 0. Try again.")
        except ValueError:
            print("    Invalid number. Try again.")


def prompt_member_list(valid_ids):
    valid_set = set(valid_ids)
    while True:
        raw = input(
            "    Member numbers (e.g. 1 3 5  or  2-8  or  all): "
        ).strip().lower()

        if not raw:
            print("    No input. Try again.")
            continue

        if raw == "all":
            return sorted(valid_ids)

        chosen = set()
        tokens = raw.replace(",", " ").split()
        error  = False

        for tok in tokens:
            sep = None
            if tok.count("-") == 1 and not tok.startswith("-"):
                sep = "-"
            elif ":" in tok:
                sep = ":"

            if sep:
                parts = tok.split(sep)
                try:
                    lo, hi = int(parts[0]), int(parts[1])
                    for n in range(lo, hi + 1):
                        if n in valid_set:
                            chosen.add(n)
                        else:
                            print(f"    Member {n} not in model – skipped.")
                    continue
                except (ValueError, IndexError):
                    pass

            try:
                n = int(tok)
                if n in valid_set:
                    chosen.add(n)
                else:
                    print(f"    Member {n} not in model – skipped.")
            except ValueError:
                print(f"    '{tok}' is not a valid number.")
                error = True

        if error:
            retry = input("    Continue with valid selections? (y/n): ").strip().lower()
            if retry != "y":
                continue

        if not chosen:
            print("    No valid members selected. Try again.")
            continue

        return sorted(chosen)


# ─────────────────────────────────────────────────────────────────────────────
# 5. COLLECT SECTION ASSIGNMENTS FROM USER
# ─────────────────────────────────────────────────────────────────────────────

def collect_assignments(member_ids):
    assignments = []
    new_map     = {}

    print("─" * 64)
    print("  SECTION DEFINITION")
    print("─" * 64)
    print("  Enter rectangular section sizes and assign them to members.")
    print("  Type 'done' when finished.\n")

    entry_num = 1

    while True:
        print(f"  ── Entry #{entry_num} " + "─" * 48)
        action = input("  Type dimensions or 'done' to finish: ").strip().lower()

        if action == "done":
            if not assignments:
                print("  Define at least one section first.")
                continue
            break

        print()
        B = prompt_float("Width  B (in model length units)")
        D = prompt_float("Depth  D (in model length units)")
        print(f"\n    -> PRISMATIC RECTANGLE  B={B}  D={D}\n")

        chosen = prompt_member_list(member_ids)
        print(f"    -> Members selected: {chosen}\n")

        assignments.append({"B": B, "D": D, "members": chosen})

        for mid in chosen:
            new_map[mid] = (B, D)

        entry_num += 1

        again = input("  Add another section? (y/n): ").strip().lower()
        if again != "y":
            break

    return assignments, new_map


# ─────────────────────────────────────────────────────────────────────────────
# 6. FINAL SUMMARY TABLE
# ─────────────────────────────────────────────────────────────────────────────

def show_final_summary(member_ids, current_sections, new_map):
    print("─" * 64)
    print("  FINAL SUMMARY  –  Changes to be applied")
    print("─" * 64)
    print(f"  {'Member':>8}  {'Current Section':<22}  {'New B':>8}  {'New D':>8}  Status")
    print(f"  {'-'*8}  {'-'*22}  {'-'*8}  {'-'*8}  {'-'*14}")

    for mid in member_ids:
        cur_name = current_sections[mid]["name"]
        if mid in new_map:
            B, D   = new_map[mid]
            b_str  = f"{B:.4f}"
            d_str  = f"{D:.4f}"
            status = "<-- WILL CHANGE"
        else:
            b_str  = "--"
            d_str  = "--"
            status = "unchanged"
        print(f"  {mid:>8}  {cur_name:<22}  {b_str:>8}  {d_str:>8}  {status}")

    print(f"\n  Members to change : {len(new_map)}")
    print(f"  Members unchanged : {len(member_ids) - len(new_map)}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 7. ASSIGN SECTIONS TO STAAD MODEL
# ─────────────────────────────────────────────────────────────────────────────

def assign_sections(staad_obj, assignments, current_sections):
    """
    CreatePrismaticRectangleProperty(depth_along_y_axis, depth_along_z_axis)
      depth_along_y_axis = D  (section depth / height)
      depth_along_z_axis = B  (section width)
    Returns property_id which is then passed to AssignBeamProperty().
    """
    print("─" * 64)
    print("  ASSIGNING SECTIONS")
    print("─" * 64)

    for entry in assignments:
        B       = entry["B"]
        D       = entry["D"]
        members = entry["members"]

        try:
            property_id = staad_obj.Property.CreatePrismaticRectangleProperty(D, B)
            if not property_id:
                print(f"  Could not create section B={B} D={D}  (returned 0)")
                continue
            print(f"\n  Created: B={B}  D={D}  property_id={property_id}")
        except Exception as exc:
            print(f"  Error creating section B={B} D={D}: {exc}")
            continue

        for mid in members:
            try:
                result = staad_obj.Property.AssignBeamProperty(mid, property_id)
                if result == 0:
                    print(f"    Member {mid:>4}  section OK", end="")
                else:
                    print(f"    Member {mid:>4}  Return code: {result}", end="")

                # Re-assign the original material – assigning a new section
                # clears the material in STAAD.Pro
                mat = current_sections[mid]["material"]
                if mat:
                    try:
                        staad_obj.Property.AssignMaterialToMember(mat, [mid])
                        print(f"  |  material '{mat}' restored")
                    except Exception as me:
                        print(f"  |  material restore error: {me}")
                else:
                    print("  |  no material to restore")
            except Exception as exc:
                print(f"    Member {mid:>4}  Error: {exc}")

    print()

    # Save so changes are written to the .std file
    print("  Saving model ...")
    try:
        staad_obj.SaveModel(saveSilent=True)
        print("  Model saved.")
    except Exception as exc:
        print(f"  SaveModel error: {exc}")

    # Refresh the STAAD.Pro UI so the new sections are visible
    print("  Refreshing STAAD.Pro UI ...")
    try:
        staad_obj.UpdateStructure()
        print("  Structure updated.\n")
    except Exception as exc:
        print(f"  UpdateStructure error: {exc}\n")


# ─────────────────────────────────────────────────────────────────────────────
# 8. RUN ANALYSIS
# ─────────────────────────────────────────────────────────────────────────────

def run_analysis(staad_obj):
    print("─" * 64)
    print("  RUNNING ANALYSIS")
    print("─" * 64)
    print("  Please wait ...")
    try:
        # silentMode=1 suppresses dialogs
        # hiddenMode=0 keeps analysis dialog visible
        # waitTillComplete=1 blocks until done
        status = staad_obj.AnalyzeEx(1, 0, 1)
        status_map = {
            -1: "Analysis Terminated",
             0: "General Error",
             1: "Analysis In Progress",
             2: "Completed – no errors or warnings",
             3: "Completed – with warnings (check output)",
             4: "Completed – WITH ERRORS (check output)",
             5: "Analysis not performed",
        }
        msg = status_map.get(status, f"Unknown status {status}")
        print(f"  Status: {msg}\n")
        return status
    except Exception as exc:
        print(f"  Analysis error: {exc}\n")
        return -1


# ─────────────────────────────────────────────────────────────────────────────
# 9. PRINT RESULTS
# ─────────────────────────────────────────────────────────────────────────────

def print_results(staad_obj, member_ids):
    try:
        num_lc = staad_obj.Load.GetNoOfPrimaryLoadCases()
    except Exception:
        num_lc = 1

    print("─" * 64)
    print(f"  MEMBER END FORCES  ({num_lc} load case(s))")
    print("─" * 64)

    for lc in range(1, num_lc + 1):
        print(f"\n  Load Case {lc}:")
        print(
            f"  {'Mbr':>5}  {'Axial':>12}  {'Shear-Y':>12}"
            f"  {'Shear-Z':>12}  {'Mom-Y':>12}  {'Mom-Z':>12}"
        )
        print("  " + "-" * 65)
        for mid in member_ids:
            try:
                f  = staad_obj.Output.GetMemberEndForces(mid, lc)
                ax = max(abs(f[0]),  abs(f[6]))
                sy = max(abs(f[1]),  abs(f[7]))
                sz = max(abs(f[2]),  abs(f[8]))
                my = max(abs(f[4]),  abs(f[10]))
                mz = max(abs(f[5]),  abs(f[11]))
                print(
                    f"  {mid:>5}  {ax:>12.3f}  {sy:>12.3f}"
                    f"  {sz:>12.3f}  {my:>12.3f}  {mz:>12.3f}"
                )
            except Exception:
                print(f"  {mid:>5}  (force data unavailable)")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    # 1. Connect
    staad_obj = connect_to_staad()

    # 2. Get all beam IDs
    member_ids = get_member_ids(staad_obj)
    if not member_ids:
        sys.exit("  No members found in the model. Exiting.")

    # 3. Read current section assignments
    current_sections = get_current_sections(staad_obj, member_ids)

    # 4. Show pre-run report (what is there NOW before any change)
    display_pre_run_report(member_ids, current_sections)

    # 5. User defines new sections and picks members
    assignments, new_map = collect_assignments(member_ids)
    if not assignments:
        sys.exit("  No sections defined. Exiting.")

    # 6. Show final summary of what will change vs what stays
    show_final_summary(member_ids, current_sections, new_map)

    # 7. Confirm before touching the model
    go = input("  Apply changes and run analysis? (y/n): ").strip().lower()
    if go != "y":
        print("\n  Cancelled. No changes made.\n")
        sys.exit(0)
    print()

    # 8. Assign sections, save, refresh UI
    assign_sections(staad_obj, assignments, current_sections)

    # 9. Run analysis
    analysis_status = run_analysis(staad_obj)

    # 10. Print member force results
    if analysis_status in (2, 3):
        print_results(staad_obj, member_ids)
    else:
        print("  Skipping result output – check STAAD.Pro for analysis errors.\n")

    print("=" * 64)
    print("  Done. Review full results inside STAAD.Pro.")
    print("=" * 64 + "\n")


if __name__ == "__main__":
    main()
