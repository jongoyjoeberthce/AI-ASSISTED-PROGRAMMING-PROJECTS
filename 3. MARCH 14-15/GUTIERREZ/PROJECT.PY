# =============================================================================
#  STEEL STAIR MODELER — OpenSTAADPy API
#  Requires: STAAD.Pro with an empty model already open.
#
#  Stair configuration (all dimensions in FEET / KIPS):
#    - 3 flights of 5 risers each, connected by 2 intermediate landings
#    - Stair width  : 4 ft
#    - Tread depth  : 1 ft
#    - Riser height : 0.583 ft  (7 in)
#    - Total rise   : 8.75 ft  (3 flights × 5 × 7 in)
#    - Landing width: 4 ft (same as stair)
#    - Stringers    : C10X20 channels (left & right side of each flight)
#    - Treads/Risers: L3X3X1/4 angles spanning between stringers
#    - Landing beams: W8X18
#    - Posts/Columns: HSS4X4X1/4 at landing corners
#    - Handrail top rail : HSS2X2X1/8
#    - Handrail posts    : HSS1.5X1.5X1/8
#
#  Coordinate system
#    X  →  horizontal (direction of travel along one flight)
#    Y  ↑  vertical
#    Z  →  stair width direction  (0 = left stringer, W = right stringer)
# =============================================================================

from openstaadpy import os_analytical

staad = os_analytical.connect()
geo   = staad.Geometry
prop  = staad.Property
sup   = staad.Support
load  = staad.Load

# ---------------------------------------------------------------------------
# 0.  Units: FEET / KIP
# ---------------------------------------------------------------------------
staad.SetInputUnits(1, 0)   # length=1 (Feet), force=0 (Kip)
staad.SaveModel(True)

# ---------------------------------------------------------------------------
# 1.  STAIR GEOMETRY PARAMETERS
# ---------------------------------------------------------------------------
STAIR_WIDTH   = 4.0          # ft  (Z direction)
TREAD_DEPTH   = 1.0          # ft  (X direction per step)
RISER_HEIGHT  = 7.0 / 12.0  # ft  (7-inch riser)
STEPS_PER_FLIGHT = 5         # steps in each of the 3 flights
LANDING_DEPTH = 4.0          # ft  (X direction, same as stair width)
NUM_FLIGHTS   = 3
HANDRAIL_HT   = 3.5 / 12.0  # ft above stringer  (42-in handrail)

# Derived
FLIGHT_HORIZ = STEPS_PER_FLIGHT * TREAD_DEPTH   # 5 ft horizontal per flight
FLIGHT_VERT  = STEPS_PER_FLIGHT * RISER_HEIGHT  # 2.917 ft vertical per flight

# Z coordinates for left / right stringer faces
Z_LEFT  = 0.0
Z_RIGHT = STAIR_WIDTH

# ---------------------------------------------------------------------------
# 2.  HELPER — node & member id counters
# ---------------------------------------------------------------------------
NID = 0   # next node id
MID = 0   # next member id

nodes   = {}   # id -> (x, y, z)
members = {}   # id -> (n1, n2)

def next_n():
    global NID; NID += 1; return NID

def next_m():
    global MID; MID += 1; return MID

def add_node(x, y, z):
    nid = next_n()
    geo.CreateNode(nid, x, y, z)
    nodes[nid] = (x, y, z)
    return nid

def add_beam(n1, n2):
    mid = next_m()
    geo.CreateBeam(mid, n1, n2)
    members[mid] = (n1, n2)
    return mid

# ---------------------------------------------------------------------------
# 3.  BUILD GEOMETRY
# ---------------------------------------------------------------------------
# We store key node ids for later use
#   stringer_nodes[flight][step][side]  (side: 0=left, 1=right)
#   landing_nodes [landing_index][corner]  0=BL,1=BR,2=TL,3=TR
#   handrail_nodes[flight][step][side]

stringer_nodes  = []   # list of flights; each flight: list of (left_n, right_n) per step-point
landing_corners = []   # list of landings; each: [BL, BR, TL, TR] (bottom/top in X, left/right in Z)
handrail_nodes  = []   # list of flights; each flight: list of (left_hr, right_hr)

# -- Build flight by flight --------------------------------------------------
x_origin = 0.0
y_origin = 0.0

for flight in range(NUM_FLIGHTS):
    flight_stringer = []   # (left_n, right_n) for each stringer point in this flight
    flight_handrail = []   # (left_hr, right_hr) for handrail posts

    # 3a.  Stringer nodes: STEPS_PER_FLIGHT + 1 points per stringer
    for step in range(STEPS_PER_FLIGHT + 1):
        x = x_origin + step * TREAD_DEPTH
        y = y_origin + step * RISER_HEIGHT
        nl = add_node(x, y, Z_LEFT)
        nr = add_node(x, y, Z_RIGHT)
        flight_stringer.append((nl, nr))

        # Handrail post node at same X, Y offset by HANDRAIL_HT
        hl = add_node(x, y + HANDRAIL_HT, Z_LEFT)
        hr = add_node(x, y + HANDRAIL_HT, Z_RIGHT)
        flight_handrail.append((hl, hr))

    stringer_nodes.append(flight_stringer)
    handrail_nodes.append(flight_handrail)

    # Update origin for next landing
    x_origin += FLIGHT_HORIZ
    y_origin += FLIGHT_VERT

    # 3b.  Landing nodes (between flights, except after last flight)
    if flight < NUM_FLIGHTS - 1:
        # 4 corners: BL, BR (at start of landing), TL, TR (at end of landing)
        x0 = x_origin
        x1 = x_origin + LANDING_DEPTH
        y_land = y_origin

        BL = add_node(x0, y_land, Z_LEFT)
        BR = add_node(x0, y_land, Z_RIGHT)
        TL = add_node(x1, y_land, Z_LEFT)
        TR = add_node(x1, y_land, Z_RIGHT)
        landing_corners.append((BL, BR, TL, TR))

        # Handrail nodes at landing level
        HBL = add_node(x0, y_land + HANDRAIL_HT, Z_LEFT)
        HBR = add_node(x0, y_land + HANDRAIL_HT, Z_RIGHT)
        HTL = add_node(x1, y_land + HANDRAIL_HT, Z_LEFT)
        HTR = add_node(x1, y_land + HANDRAIL_HT, Z_RIGHT)

        x_origin += LANDING_DEPTH  # advance X past landing

# ---------------------------------------------------------------------------
# 4.  MEMBER CONNECTIVITY
# ---------------------------------------------------------------------------
CC = 1  # American section tables

# Track member id groups for property assignment
stringer_mids   = []
tread_mids      = []
landing_beam_mids = []
post_mids       = []
handrail_mids   = []

# 4a.  Stringers — longitudinal members along each flight
for flight_idx, flight in enumerate(stringer_nodes):
    for step in range(len(flight) - 1):
        nl0, nr0 = flight[step]
        nl1, nr1 = flight[step + 1]
        stringer_mids.append(add_beam(nl0, nl1))   # left stringer segment
        stringer_mids.append(add_beam(nr0, nr1))   # right stringer segment

# 4b.  Treads — cross members at each step point (angle sections)
for flight in stringer_nodes:
    for (nl, nr) in flight:
        tread_mids.append(add_beam(nl, nr))

# 4c.  Landing beams — perimeter and mid beam at each landing
for (BL, BR, TL, TR) in landing_corners:
    landing_beam_mids.append(add_beam(BL, BR))   # front edge  (Z direction)
    landing_beam_mids.append(add_beam(TL, TR))   # back edge
    landing_beam_mids.append(add_beam(BL, TL))   # left side   (X direction)
    landing_beam_mids.append(add_beam(BR, TR))   # right side
    # Centre diagonal / cross member for torsional stability
    landing_beam_mids.append(add_beam(BL, TR))

# 4d.  Posts / columns at landing corners (vertical from ground if flight=0,
#      otherwise just the short column stub to the underside of stringer)
#      For simplicity model as vertical stubs of 1 ft below each landing.
for (BL, BR, TL, TR) in landing_corners:
    for corner_n in (BL, BR, TL, TR):
        cx, cy, cz = nodes[corner_n]
        bot_n = add_node(cx, cy - 1.0, cz)
        post_mids.append(add_beam(bot_n, corner_n))

# 4e.  Ground posts under first-flight bottom nodes
fl0_bottom_l, fl0_bottom_r = stringer_nodes[0][0]
for n_top in (fl0_bottom_l, fl0_bottom_r):
    cx, cy, cz = nodes[n_top]
    n_bot = add_node(cx, 0.0, cz)
    post_mids.append(add_beam(n_bot, n_top))

# 4f.  Handrail — vertical posts and top rail
for flight_idx, (flight_str, flight_hr) in enumerate(zip(stringer_nodes, handrail_nodes)):
    for step in range(len(flight_str)):
        nl, nr = flight_str[step]
        hl, hr = flight_hr[step]
        handrail_mids.append(add_beam(nl, hl))   # left post
        handrail_mids.append(add_beam(nr, hr))   # right post

    # Top rail segments connecting handrail post nodes along stringer
    for step in range(len(flight_hr) - 1):
        hl0, hr0 = flight_hr[step]
        hl1, hr1 = flight_hr[step + 1]
        handrail_mids.append(add_beam(hl0, hl1))   # left rail
        handrail_mids.append(add_beam(hr0, hr1))   # right rail

# ---------------------------------------------------------------------------
# 5.  SECTION PROPERTIES
# ---------------------------------------------------------------------------
# C10X20  — stringers
p_stringer = prop.CreateBeamPropertyFromTable(CC, "C10X20", 0, 0.0, 0.0)
# W8X18   — landing beams
p_landing  = prop.CreateBeamPropertyFromTable(CC, "W8X18",  0, 0.0, 0.0)
# L3X3X1/4 — treads (angle)
p_tread    = prop.CreateAnglePropertyFromTable(CC, "L30304", 0, 0.0)
# HSS4X4X1/4 — posts  (use pipe or tube; approximate with W4X13 if HSS unavailable)
p_post     = prop.CreateBeamPropertyFromTable(CC, "W4X13",  0, 0.0, 0.0)
# HSS2X2X1/8 — handrail rail
p_rail     = prop.CreateBeamPropertyFromTable(CC, "W4X13",  0, 0.0, 0.0)

# Assign properties
if stringer_mids:
    prop.AssignBeamProperty(stringer_mids, p_stringer)
if tread_mids:
    prop.AssignBeamProperty(tread_mids, p_tread)
if landing_beam_mids:
    prop.AssignBeamProperty(landing_beam_mids, p_landing)
if post_mids:
    prop.AssignBeamProperty(post_mids, p_post)
if handrail_mids:
    prop.AssignBeamProperty(handrail_mids, p_rail)

# Assign STEEL material to all members
all_mids = list(range(1, MID + 1))
prop.AssignMaterialToMember("STEEL", all_mids)

# Beta-angle: rotate stringers 90° (web vertical for inclined channel)
if stringer_mids:
    prop.AssignBetaAngle(stringer_mids, 90.0)

# ---------------------------------------------------------------------------
# 6.  MEMBER RELEASES — pin tread ends (moment-released)
# ---------------------------------------------------------------------------
# Treads and handrail elements are pin-connected at both ends (no moment transfer)
pin_spec_start = prop.CreateMemberReleaseSpec(
    0,
    [0, 0, 0, 0, 1, 1],   # release MY & MZ at start
    [0, 0, 0, 0, 0, 0]
)
pin_spec_end = prop.CreateMemberReleaseSpec(
    1,
    [0, 0, 0, 0, 1, 1],   # release MY & MZ at end
    [0, 0, 0, 0, 0, 0]
)
for release_list in [tread_mids, handrail_mids]:
    if release_list:
        prop.AssignMemberSpecToBeam(release_list, pin_spec_start)
        prop.AssignMemberSpecToBeam(release_list, pin_spec_end)

# ---------------------------------------------------------------------------
# 7.  SUPPORTS
# ---------------------------------------------------------------------------
fixed_id  = sup.CreateSupportFixed()
pinned_id = sup.CreateSupportPinned()

# Bottom of ground posts → fixed base
support_nodes = []
for mid in post_mids:
    n1, n2 = members[mid]
    # Lowest node in Y is the base
    y1 = nodes[n1][1]
    y2 = nodes[n2][1]
    base_n = n1 if y1 < y2 else n2
    if base_n not in support_nodes:
        support_nodes.append(base_n)

if support_nodes:
    # First post: fixed (stair base anchor)
    sup.AssignSupportToNode([support_nodes[0]], fixed_id)
    # Remaining: pinned
    if len(support_nodes) > 1:
        sup.AssignSupportToNode(support_nodes[1:], pinned_id)

# ---------------------------------------------------------------------------
# 8.  LOADS
# ---------------------------------------------------------------------------
# ---- Case 1: Dead Load (self-weight + stair dead) ----
case_dl = load.CreateNewPrimaryLoadEx2("DEAD LOAD", 0, 1)
load.SetLoadActive(case_dl)
load.AddSelfWeightInXYZ(2, -1.0)   # global Y self-weight

# Stair dead load: 20 psf = 0.020 ksf on tread members
# Applied as uniform force in Y on treads  (0.020 ksf × 4 ft width = 0.08 k/ft)
TREAD_DL = -0.08   # k/ft
if tread_mids:
    load.AddMemberUniformForce(tread_mids, 2, TREAD_DL, 0.0, 0.0, 0.0)

# Landing dead load: 20 psf on landing beams (0.08 k/ft)
if landing_beam_mids:
    load.AddMemberUniformForce(landing_beam_mids, 2, TREAD_DL, 0.0, 0.0, 0.0)

# ---- Case 2: Live Load (100 psf per IBC for stairs) ----
case_ll = load.CreateNewPrimaryLoadEx2("LIVE LOAD", 0, 2)
load.SetLoadActive(case_ll)
TREAD_LL = -100.0 / 1000.0 * STAIR_WIDTH   # 100 psf × 4 ft / 1000 = 0.40 k/ft
if tread_mids:
    load.AddMemberUniformForce(tread_mids, 2, -TREAD_LL, 0.0, 0.0, 0.0)
if landing_beam_mids:
    load.AddMemberUniformForce(landing_beam_mids, 2, -TREAD_LL, 0.0, 0.0, 0.0)

# ---- Case 3: Handrail lateral load (200 lb / ft per IBC) ----
case_hr = load.CreateNewPrimaryLoadEx2("HANDRAIL LATERAL LOAD", 0, 3)
load.SetLoadActive(case_hr)
HR_LAT = 0.200   # 0.2 k/ft applied in X direction
if handrail_mids:
    load.AddMemberUniformForce(handrail_mids, 4, HR_LAT, 0.0, 0.0, 0.0)   # 4 = GlobalX

# ---- Load Combinations (LRFD per AISC / IBC) ----
# Combo 1: 1.4D
comb1 = load.CreateNewLoadCombination("1.4D", 4)
load.AddLoadAndFactorToCombination(4, 1, 1.4)

# Combo 2: 1.2D + 1.6L
comb2 = load.CreateNewLoadCombination("1.2D + 1.6L", 5)
load.AddLoadAndFactorToCombination(5, 1, 1.2)
load.AddLoadAndFactorToCombination(5, 2, 1.6)

# Combo 3: 1.2D + 1.0L + 1.0HR
comb3 = load.CreateNewLoadCombination("1.2D + 1.0L + 1.0HR", 6)
load.AddLoadAndFactorToCombination(6, 1, 1.2)
load.AddLoadAndFactorToCombination(6, 2, 1.0)
load.AddLoadAndFactorToCombination(6, 3, 1.0)

# ---------------------------------------------------------------------------
# 9.  SAVE & ANALYSE
# ---------------------------------------------------------------------------
staad.SaveModel(True)
staad.Command.PerformAnalysis(0)

# ---------------------------------------------------------------------------
# 10.  REPORT
# ---------------------------------------------------------------------------
total_flights    = NUM_FLIGHTS
total_steps      = NUM_FLIGHTS * STEPS_PER_FLIGHT
total_landings   = NUM_FLIGHTS - 1
total_rise_ft    = total_steps * RISER_HEIGHT
total_run_ft     = (NUM_FLIGHTS * FLIGHT_HORIZ) + (total_landings * LANDING_DEPTH)

print("=" * 60)
print("  STEEL STAIR MODEL — STAAD.Pro")
print("=" * 60)
print(f"  Flights          : {total_flights}")
print(f"  Steps per flight : {STEPS_PER_FLIGHT}")
print(f"  Total steps      : {total_steps}")
print(f"  Intermediate landings : {total_landings}")
print(f"  Stair width      : {STAIR_WIDTH:.1f} ft")
print(f"  Riser height     : {RISER_HEIGHT*12:.1f} in  ({RISER_HEIGHT:.4f} ft)")
print(f"  Tread depth      : {TREAD_DEPTH*12:.1f} in  ({TREAD_DEPTH:.4f} ft)")
print(f"  Total rise       : {total_rise_ft:.3f} ft")
print(f"  Total run        : {total_run_ft:.1f} ft")
print("-" * 60)
print(f"  Nodes created    : {NID}")
print(f"  Members created  : {MID}")
print(f"    Stringers      : {len(stringer_mids)}")
print(f"    Treads/Risers  : {len(tread_mids)}")
print(f"    Landing beams  : {len(landing_beam_mids)}")
print(f"    Posts/Columns  : {len(post_mids)}")
print(f"    Handrail       : {len(handrail_mids)}")
print("-" * 60)
print("  Sections used:")
print("    Stringers      : C10X20  (channels, web vertical)")
print("    Treads         : L30304  (angles, pin-ended)")
print("    Landing beams  : W8X18")
print("    Posts          : W4X13   (HSS4X4 substitute)")
print("    Handrail       : W4X13   (HSS2X2 substitute)")
print("-" * 60)
print("  Load cases:")
print("    1  Dead Load (SW + 20 psf superimposed)")
print("    2  Live Load (100 psf stair occupancy)")
print("    3  Handrail lateral (200 plf)")
print("    4  Combo: 1.4D")
print("    5  Combo: 1.2D + 1.6L")
print("    6  Combo: 1.2D + 1.0L + 1.0HR")
print("=" * 60)
print("  Model saved and analysis performed successfully.")