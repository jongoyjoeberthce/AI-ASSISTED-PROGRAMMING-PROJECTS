from openstaadpy import os_analytical
import os

# 1. SETUP - Directory and File Name
project_dir = r"D:\TRAININGS\day2\AI-ASSISTED-PROGRAMMING-PROJECTS\FEBRUARY 14-15\LANTICSE"
file_name = "trial.std"
full_path = os.path.join(project_dir, file_name)

# 2. CONNECT - STAAD.Pro must be open!
staad_obj = os_analytical.connect()

if staad_obj is None:
    print("❌ ERROR: Please open STAAD.Pro CONNECT Edition first.")
    exit()

try:
    # 3. CREATE FILE - Fixed with 3 required arguments (Path, Length, Force)
    print(f"Initializing {file_name}...")
    staad_obj.NewSTAADFile(full_path, 4, 5) 
    
    # 4. GEOMETRY - Access the geometry object
    geometry = staad_obj.Geometry
    
    # Create simple 6m span x 4m height Portal Frame
    print("Creating Nodes...")
    geometry.CreateNode(1, 0, 0, 0) # Base Left
    geometry.CreateNode(2, 6, 0, 0) # Base Right
    geometry.CreateNode(3, 0, 4, 0) # Top Left
    geometry.CreateNode(4, 6, 4, 0) # Top Right
    
    print("Creating Beams...")
    geometry.CreateBeam(1, 1, 3) # Left Column
    geometry.CreateBeam(2, 2, 4) # Right Column
    geometry.CreateBeam(3, 3, 4) # Roof Beam
    
    # 5. SUPPORTS - Assign Fixed Supports to base nodes
    print("Assigning Supports...")
    staad_obj.Support.CreateSupportFixed(1)
    staad_obj.Support.CreateSupportFixed(2)
    
    # 6. SAVE
    staad_obj.Save()
    print("-" * 40)
    print(f"✅ SUCCESS: {file_name} created with Metric Units (kN-m).")
    print("-" * 40)

except Exception as e:
    print(f"Failed to create file: {e}")