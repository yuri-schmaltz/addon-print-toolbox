# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 Mikhail Rachinskiy

import re

from bpy.types import Operator
import bmesh
import math
from mathutils import Vector

# Storage for suggestions
_suggestions = []

def get_suggestions():
    return _suggestions

def clear_suggestions():
    _suggestions.clear()

def add_suggestion(id, message, priority, operator_id, icon="LIGHTBULB_ON", data=None):
    _suggestions.append({
        "id": id,
        "message": message,
        "priority": priority,
        "operator_id": operator_id,
        "icon": icon,
        "data": data
    })

class MESH_OT_smart_advisor_analyze(Operator):
    bl_idname = "mesh.print3d_advisor_analyze"
    bl_label = "Analyze for Suggestions"
    bl_description = "Analyze the mesh and provide intelligent design suggestions"
    
    def execute(self, context):
        obj = context.active_object
        if not obj or obj.type != 'MESH':
            return {'CANCELLED'}
        
        clear_suggestions()
        
        # 1. Check for Support Optimization
        self._check_support(obj, context)
        
        # 2. Check for Stress Concentration (Sharp internal edges)
        self._check_stress_relief(obj, context)
        
        # 3. Check for Low Mesh Density (Large flat faces that might print poorly)
        self._check_mesh_density(obj, context)
        
        # 4. Check for Thin Walls (Integrate with existing check)
        self._check_thin_walls(obj, context)

        # 5. Check assembly clearance between selected parts
        self._check_assembly_clearance(context)
        
        if not _suggestions:
            self.report({'INFO'}, "No suggestions found for this mesh.")
        else:
            self.report({'INFO'}, f"Found {len(_suggestions)} suggestions.")
            
        return {'FINISHED'}

    def _check_support(self, obj, context):
        props = context.scene.print3d_toolbox
        overhang_count = _extract_report_count(props.report_overhang, "Overhang Face")
        if overhang_count is None:
            return

        if overhang_count > 0:
            add_suggestion(
                "SUPPORT_REDUCE",
                f"Detected {overhang_count} overhang faces. Optimize orientation to reduce support.",
                "HIGH",
                "object.print3d_optimize_overhang",
                icon="ORIENTATION_GIMBAL"
            )

    def _check_stress_relief(self, obj, context):
        # Find internal sharp edges (concave) that could cause stress fractures
        bm = bmesh.new()
        bm.from_mesh(obj.data)
        bm.edges.ensure_lookup_table()
        
        sharp_concave = 0
        for edge in bm.edges:
            if edge.is_manifold:
                angle = edge.calc_face_angle_signed()
                # Negative angle in Blender usually means concave/internal
                if angle < -math.radians(45.0):
                    sharp_concave += 1
        
        bm.free()
        
        if sharp_concave > 5:
            add_suggestion(
                "STRESS_RELIEF",
                f"Found {sharp_concave} sharp internal edges. Add fillets to reduce stress.",
                "MEDIUM",
                "mesh.print3d_apply_stress_relief",
                icon="MOD_BEVEL"
            )

    def _check_mesh_density(self, obj, context):
        # Large objects with few faces might have visible faceting
        face_count = len(obj.data.polygons)
        dims = obj.dimensions
        max_dim = max(dims)
        
        if max_dim > 0.1 and face_count < 500: # 10cm wide but very low poly
             add_suggestion(
                "LOW_POLY",
                "Low mesh density for size. Subdivide for smoother surface.",
                "LOW",
                "mesh.print3d_apply_subdivision",
                icon="MOD_SUBSURF"
            )

    def _check_thin_walls(self, obj, context):
        props = context.scene.print3d_toolbox
        thin_faces = _extract_report_count(props.report_thickness, "Thin Faces")
        if thin_faces is None:
            add_suggestion(
                "THICKNESS_CHECK",
                "Run thickness analysis to verify minimum wall thickness.",
                "LOW",
                "mesh.print3d_check_thick",
                icon="LINCURVE"
            )
            return

        if thin_faces > 0:
            add_suggestion(
                "THICKNESS_FIX",
                f"Detected {thin_faces} thin faces. Add Solidify to increase wall thickness.",
                "MEDIUM",
                "mesh.print3d_apply_solidify",
                icon="MOD_SOLIDIFY"
            )

    def _check_assembly_clearance(self, context):
        props = context.scene.print3d_toolbox
        selected = [ob for ob in context.selected_objects if ob.type == 'MESH']

        if len(selected) < 2 or not props.use_assembly_tolerance:
            return

        tolerance = props.assembly_tolerance
        if tolerance <= 0.0:
            return

        def _bbox_world(ob):
            coords = [ob.matrix_world @ Vector(corner) for corner in ob.bound_box]
            mins = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
            maxs = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
            return mins, maxs

        def _axis_gap(min_a, max_a, min_b, max_b):
            if max_a < min_b:
                return min_b - max_a
            if max_b < min_a:
                return min_a - max_b
            return 0.0

        violating_pairs = 0
        for i, obj_a in enumerate(selected):
            min_a, max_a = _bbox_world(obj_a)
            for obj_b in selected[i + 1:]:
                min_b, max_b = _bbox_world(obj_b)
                clearance = max(
                    _axis_gap(min_a.x, max_a.x, min_b.x, max_b.x),
                    _axis_gap(min_a.y, max_a.y, min_b.y, max_b.y),
                    _axis_gap(min_a.z, max_a.z, min_b.z, max_b.z),
                )
                if clearance < tolerance:
                    violating_pairs += 1

        if violating_pairs <= 0:
            return

        if not props.assembly_auto_scale_fallback:
            add_suggestion(
                "ASSEMBLY_CONTACT_SCALING_ENABLE",
                "Assembly conflicts detected. Enable contact scaling before auto-adjust.",
                "HIGH",
                "mesh.print3d_enable_contact_scaling",
                icon="MOD_PHYSICS",
            )

        add_suggestion(
            "ASSEMBLY_CLEARANCE_FIX",
            f"Detected {violating_pairs} assembly clearance conflicts below {tolerance:.4f}m. Apply local contact scaling.",
            "HIGH",
            "object.print3d_auto_clearance",
            icon="MOD_PHYSICS",
        )

class MESH_OT_apply_stress_relief(Operator):
    bl_idname = "mesh.print3d_apply_stress_relief"
    bl_label = "Apply Stress Relief"
    bl_description = "Automatically add bevel/fillet to sharp internal edges"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        # Implementation: Add a Bevel modifier limited to sharp edges
        mod = obj.modifiers.new(name="Stress Relief", type='BEVEL')
        mod.limit_method = 'ANGLE'
        mod.angle_limit = math.radians(30.0)
        mod.width = 0.002 # 2mm default
        mod.segments = 3
        return {'FINISHED'}

class MESH_OT_apply_subdivision(Operator):
    bl_idname = "mesh.print3d_apply_subdivision"
    bl_label = "Apply Subdivision"
    bl_description = "Add a subdivision surface modifier for better print quality"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        mod = obj.modifiers.new(name="Print Smoothness", type='SUBSURF')
        mod.levels = 1
        mod.render_levels = 2
        return {'FINISHED'}

class MESH_OT_apply_solidify(Operator):
    bl_idname = "mesh.print3d_apply_solidify"
    bl_label = "Apply Solidify"
    bl_description = "Add a solidify modifier to ensure minimum wall thickness"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        obj = context.active_object
        props = context.scene.print3d_toolbox
        mod = obj.modifiers.new(name="Wall Thickness", type='SOLIDIFY')
        mod.thickness = props.thickness_min
        return {'FINISHED'}


class MESH_OT_enable_contact_scaling(Operator):
    bl_idname = "mesh.print3d_enable_contact_scaling"
    bl_label = "Enable Contact Scaling"
    bl_description = "Enable contact scaling and assembly checks for automatic tolerance adjustment"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        props = context.scene.print3d_toolbox
        props.analyze_selected_objects = True
        props.use_assembly_tolerance = True
        props.assembly_auto_scale_fallback = True
        self.report({'INFO'}, "Contact scaling enabled for assembly auto-adjust")
        return {'FINISHED'}


def _extract_report_count(report_text: str, label: str) -> int | None:
    if not report_text:
        return None

    pattern = re.compile(rf"{re.escape(label)}:\s*(\d+)")
    match = pattern.search(report_text)
    if not match:
        return None

    return int(match.group(1))
