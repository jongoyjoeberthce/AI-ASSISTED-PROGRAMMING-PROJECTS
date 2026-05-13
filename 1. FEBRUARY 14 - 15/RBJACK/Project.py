import tkinter as tk
from tkinter import messagebox
from openstaadpy import os_analytical


def create_building():
    try:
        bays_x = int(entry_bays_x.get())
        bays_z = int(entry_bays_z.get())
        bay_width = float(entry_bay_width.get())
        bay_depth = float(entry_bay_depth.get())
        stories = int(entry_stories.get())
        story_height = float(entry_story_height.get())

        support_type = support_var.get()

        staad = os_analytical.connect()
        geo = staad.Geometry
        prop = staad.Property
        sup = staad.Support
        load = staad.Load

        # ---------------------------
        # METRIC UNITS (Meter, kN)
        # ---------------------------
        staad.SetInputUnits(4, 1)  # 4 = Meter, 1 = kN
        staad.SaveModel(True)

        node_id = 1
        beam_id = 1
        column_id = 1000
        node_map = {}

        # ---------------------------
        # CREATE NODES
        # ---------------------------
        for level in range(stories + 1):
            y = level * story_height
            for i in range(bays_x + 1):
                for j in range(bays_z + 1):
                    x = i * bay_width
                    z = j * bay_depth
                    geo.CreateNode(node_id, x, y, z)
                    node_map[(level, i, j)] = node_id
                    node_id += 1

        # ---------------------------
        # CREATE BEAMS
        # ---------------------------
        for level in range(1, stories + 1):
            for i in range(bays_x + 1):
                for j in range(bays_z + 1):

                    n1 = node_map[(level, i, j)]

                    if i < bays_x:
                        n2 = node_map[(level, i + 1, j)]
                        geo.CreateBeam(beam_id, n1, n2)
                        beam_id += 1

                    if j < bays_z:
                        n2 = node_map[(level, i, j + 1)]
                        geo.CreateBeam(beam_id, n1, n2)
                        beam_id += 1

        # ---------------------------
        # CREATE COLUMNS
        # ---------------------------
        for level in range(stories):
            for i in range(bays_x + 1):
                for j in range(bays_z + 1):

                    n1 = node_map[(level, i, j)]
                    n2 = node_map[(level + 1, i, j)]
                    geo.CreateBeam(column_id, n1, n2)
                    column_id += 1

        # ---------------------------
        # DEFINE CONCRETE PROPERTY (Metric)
        # ---------------------------
        beam_prop = prop.CreatePrismaticProperty(0.3, 0.45)   # 300x450 mm
        column_prop = prop.CreatePrismaticProperty(0.45, 0.45) # 450x450 mm

        total_beams = list(range(1, beam_id))
        total_columns = list(range(1000, column_id))

        prop.AssignBeamProperty(total_beams, beam_prop)
        prop.AssignBeamProperty(total_columns, column_prop)

        prop.AssignMaterialToMember("CONCR
