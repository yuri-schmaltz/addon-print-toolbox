# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2017-2025 Mikhail Rachinskiy

import bmesh
from bpy.app.translations import pgettext_tip as tip_
from bpy.types import Object, Panel

from . import report
from .preferences import bed_profile_dimensions
from .operators import advisor


def _is_mesh(ob: Object) -> bool:
    return ob is not None and ob.type == "MESH"


class Sidebar:
    bl_category = "3D Print"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"

    @classmethod
    def poll(cls, context):
        return context.mode in {"OBJECT", "EDIT_MESH"}


class VIEW3D_PT_print3d_analyze(Sidebar, Panel):
    bl_label = "Analyze"

    _type_to_icon = {
        bmesh.types.BMVert: "VERTEXSEL",
        bmesh.types.BMEdge: "EDGESEL",
        bmesh.types.BMFace: "FACESEL",
    }

    def draw_report(self, context):
        layout = self.layout
        info = report.info()

        if info:
            is_edit = context.edit_object is not None

            layout.separator()
            row = layout.row()
            row.label(text="Result", icon="OUTLINER_OB_FONT")
            row.operator("wm.print3d_report_clear", text="", icon="X")

            box = layout.box()
            col = box.column()

            for i, (text, data) in enumerate(info):
                
                # Simple heuristic to determine if it's a "Zero issue" check
                # Text usually looks like "Non-manifold Edges: 0"
                has_issues = False
                if ":" in text:
                    number_part = text.split(":")[-1].strip()
                    if number_part.isdigit() and int(number_part) > 0:
                        has_issues = True
                
                icon = "ERROR" if has_issues else "CHECKMARK"
                
                # Check alert (red line) highlights problematic returns visually
                row = col.row()
                row.alert = has_issues

                if is_edit and data and data[1]:
                    bm_type, _bm_array = data
                    # Override generic error icon with selection icon if clickable
                    sel_icon = self._type_to_icon.get(bm_type, icon)
                    row.operator("mesh.print3d_select_report", text=text, icon=sel_icon).index = i
                else:
                    row.label(text=text, icon=icon)

    def draw(self, context):
        layout = self.layout
        layout.enabled = _is_mesh(context.object)

        props = context.scene.print3d_toolbox

        box = layout.box()
        box.label(text="Statistics", icon="INFO")
        row = box.row(align=True)
        row.operator("mesh.print3d_info_volume", text="Volume", icon="MESH_CUBE")
        row.operator("mesh.print3d_info_area", text="Area", icon="SURFACE_NCURVE")

        box = layout.box()
        box.label(text="Checks", icon="MODIFIER")
        col = box.column(align=True)
        col.operator("mesh.print3d_check_solid", icon="MOD_SOLIDIFY")
        col.operator("mesh.print3d_check_intersect", icon="UV_FACESEL")
        
        row = col.row(align=True)
        row.operator("mesh.print3d_check_degenerate", icon="SNAP_VERTEX")
        row.prop(props, "threshold_zero", text="")
        
        row = col.row(align=True)
        row.operator("mesh.print3d_check_nonplanar", icon="SNAP_FACE")
        row.prop(props, "angle_nonplanar", text="")
        
        row = col.row(align=True)
        row.operator("mesh.print3d_check_thick", icon="LINECURVE")
        row.prop(props, "thickness_min", text="")
        
        row = col.row(align=True)
        row.operator("mesh.print3d_check_sharp", icon="MOD_BEVEL")
        row.prop(props, "angle_sharp", text="")
        
        row = col.row(align=True)
        row.operator("mesh.print3d_check_overhang", icon="FILE_PARENT")
        row.prop(props, "angle_overhang", text="")
        
        box.separator()
        box.operator("mesh.print3d_check_all", icon="RIGHTARROW_THIN")

        box = layout.box()
        box.label(text="Orientation", icon="ORIENTATION_GIMBAL")
        row = box.row(align=True)
        row.operator("object.print3d_optimize_overhang", text="Optimize Overhang", icon="PLAY")
        row.prop(props, "overhang_optimize_angle", text="")
        row.prop(props, "overhang_optimize_iterations", text="")

        box = layout.box()
        box.label(text="Multi-Object", icon="SCENE_DATA")
        row = box.row(align=True)
        row.prop(props, "analyze_selected_objects")
        
        row = box.row(align=True)
        row.prop(props, "use_assembly_tolerance")
        row.prop(props, "assembly_tolerance", text="")

        self.draw_report(context)


class VIEW3D_PT_print3d_cleanup(Sidebar, Panel):
    bl_label = "Clean Up"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.enabled = _is_mesh(context.object)
        
        box = layout.box()
        box.operator("mesh.print3d_clean_non_manifold", icon="BRUSH_DATA")


class VIEW3D_PT_print3d_edit(Sidebar, Panel):
    bl_label = "Edit"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        is_mesh = _is_mesh(context.object)
        props = context.scene.print3d_toolbox

        box = layout.box()
        box.label(text="Transform", icon="NONE")
        box.operator("mesh.print3d_hollow", icon="MOD_THICKNESS")

        row = box.row()
        row.enabled = is_mesh
        row.operator("object.print3d_align_xy", icon="CON_ROTLIKE")

        box = layout.box()
        box.label(text="Build Volume", icon="BBOX")
        row = box.row(align=True)
        row.prop(props, "bed_profile", text="")
        row.prop(props, "show_bed_bounds", icon="RESTRICT_VIEW_OFF" if props.show_bed_bounds else "RESTRICT_VIEW_ON", text="")

        if props.bed_profile == "CUSTOM":
            col = box.column(align=True)
            col.enabled = is_mesh
            col.prop(props, "bed_size_x")
            col.prop(props, "bed_size_y")
            col.prop(props, "bed_size_z")
        else:
            dims = bed_profile_dimensions(props)
            box.label(text=tip_("Preset: {} x {} x {} mm").format(*[round(v, 2) for v in dims]), icon="INFO")

        row = box.row(align=True)
        row.enabled = is_mesh
        row.operator("object.print3d_check_bed_fit", text="Check Fit", icon="ZOOM_ALL")
        op = row.operator("object.print3d_check_bed_fit", text="Auto Scale to Fit", icon="FULLSCREEN_ENTER")
        op.auto_scale = True

        if props.bed_report:
            report_box = box.box()
            report_box.label(text="Build Volume Report", icon="OUTLINER_OB_FONT")
            for line in props.bed_report.splitlines():
                row = report_box.row()
                if line.startswith("X:"):
                    row.alert = props.bed_axis_overflow[0]
                elif line.startswith("Y:"):
                    row.alert = props.bed_axis_overflow[1]
                elif line.startswith("Z:"):
                    row.alert = props.bed_axis_overflow[2]
                row.label(text=line)

        box = layout.box()
        box.label(text="Scale To", icon="ARROW_LEFTRIGHT")
        row = box.row(align=True)
        row.enabled = is_mesh
        row.operator("mesh.print3d_scale_to_volume", text="Volume", icon="MESH_CUBE")
        row.operator("mesh.print3d_scale_to_bounds", text="Bounds", icon="VIEWORTHO")


class VIEW3D_PT_print3d_advisor(Sidebar, Panel):
    bl_label = "Smart Advisor (Beta)"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.enabled = _is_mesh(context.object)
        
        box = layout.box()
        box.label(text="Design Suggestions", icon="LIGHTBULB_ON")
        box.operator("mesh.print3d_advisor_analyze", text="Analyze Mesh for DfAM", icon="NODETREE")
        
        suggestions = advisor.get_suggestions()
        
        if suggestions:
            layout.separator()
            for sug in suggestions:
                sbox = layout.box()
                row = sbox.row()
                row.label(text=sug["message"], icon=sug["icon"])
                
                # Highlight priority
                if sug["priority"] == "HIGH":
                    row.label(text="", icon="ERROR")
                
                row = sbox.row()
                row.operator(sug["operator_id"], text="Apply Suggestion", icon="CHECKMARK")
        else:
            layout.label(text="Run analysis to see suggestions", icon="INFO")


class VIEW3D_PT_print3d_export(Sidebar, Panel):
    bl_label = "Export"
    bl_options = {"DEFAULT_CLOSED"}

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        props = context.scene.print3d_toolbox

        layout.prop(props, "export_path", text="")
        layout.prop(props, "export_format")
        
        row = layout.row(align=True)
        row.prop(props, "export_preset")
        row.operator("wm.print3d_preset_add", text="", icon="ADD")
        row.operator("wm.print3d_preset_remove", text="", icon="REMOVE")

        layout.operator("export_scene.print3d_export", icon="EXPORT")

        header, panel = layout.panel("options", default_closed=True)
        header.label(text="Options")
        if panel:
            col = panel.column(heading="General")
            sub = col.column()
            sub.active = props.export_format not in {"OBJ", "3MF"}
            sub.prop(props, "use_ascii_format")
            col.prop(props, "use_scene_scale")

            col = panel.column(heading="Geometry")
            col.active = props.export_format != "STL"
            col.prop(props, "use_uv")
            col.prop(props, "use_normals", text="Normals")
            col.prop(props, "use_colors", text="Colors")

            col = panel.column(heading="Materials")
            col.prop(props, "use_copy_textures")

            col = panel.column(heading="Mesh Optimization")
            col.prop(props, "use_export_decimate")
            sub = col.column()
            sub.active = props.use_export_decimate
            sub.prop(props, "export_decimate_ratio", text="Ratio")

            col = panel.column(heading="3MF")
            col.active = props.export_format == "3MF"
            col.prop(props, "use_3mf_materials")
            col.prop(props, "use_3mf_units")
