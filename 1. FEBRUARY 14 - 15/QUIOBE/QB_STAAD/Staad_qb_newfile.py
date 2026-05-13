from openstaadpy import os_analytical

staad_obj = os_analytical.connect()
if staad_obj is None:
    print("staad object not found")
    exit()

staad_obj.NewSTAADFile(
    "C:/Users/Acer/Documents/GitHub/Staad AI Day 2/AI-ASSISTED-PROGRAMMING-PROJECTS/FEBRUARY 14-15/QUIOBE/QB_STAAD/warehouse.std",
    4,
    5
)
