# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2025 Mikhail Rachinskiy

import re

from bpy.types import Operator
import bmesh
import math

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


def _extract_report_count(report_text: str, label: str) -> int | None:
    if not report_text:
        return None

    pattern = re.compile(rf"{re.escape(label)}:\s*(\d+)")
    match = pattern.search(report_text)
    if not match:
        return None

    return int(match.group(1))
