# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2024 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy

import math
import bpy

from bpy.props import (
    BoolProperty,
    BoolVectorProperty,
    CollectionProperty,
    EnumProperty,
    FloatProperty,
    IntProperty,
    StringProperty,
)
from bpy.types import AddonPreferences, PropertyGroup

from . import __package__ as base_package
from . import report


BED_PROFILES = {
    "ENDER3": (220.0, 220.0, 250.0, "Ender 3 (220x220x250mm)"),
    "PRUSA_MK4": (250.0, 210.0, 220.0, "Prusa MK4 (250x210x220mm)"),
    "BAMBULAB_P1P": (256.0, 256.0, 256.0, "Bambu Lab P1P (256x256x256mm)"),
    "CUSTOM": (220.0, 220.0, 220.0, "Custom"),
}


def bed_profile_dimensions(props) -> tuple[float, float, float]:
    if props.bed_profile == "CUSTOM":
        return props.bed_size_x, props.bed_size_y, props.bed_size_z

    x, y, z, _label = BED_PROFILES[props.bed_profile]
    return x, y, z


def _preset_items(self, context):
    if context is None:
        return []
    
    try:
        addon = context.preferences.addons.get(base_package)
        if addon is None:
            return []
        
        prefs = addon.preferences
        return [(str(i), preset.name, "") for i, preset in enumerate(prefs.export_presets)]
    except Exception:
        return []


def _operator_exists(module_name: str, op_name: str) -> bool:
    if not hasattr(bpy.ops, module_name):
        return False

    submodule = getattr(bpy.ops, module_name)
    if not hasattr(submodule, op_name):
        return False

    op = getattr(submodule, op_name)
    try:
        op.get_rna_type()
    except (KeyError, AttributeError):
        return False

    return True


def is_3mf_export_available() -> bool:
    return _operator_exists("export_scene", "threemf") or _operator_exists("wm", "threemf_export")


class Print3DExportPreset(PropertyGroup):
    name: StringProperty(name="Name", default="Preset")
    export_format: EnumProperty(
        name="Format",
        items=(("OBJ", "OBJ", ""), ("PLY", "PLY", ""), ("STL", "STL", ""), ("3MF", "3MF", "")),
        default="STL",
    )
    use_ascii_format: BoolProperty(name="ASCII")
    use_scene_scale: BoolProperty(name="Scene Scale")
    use_copy_textures: BoolProperty(name="Copy Textures")
    use_uv: BoolProperty(name="UVs")
    use_normals: BoolProperty(name="Normals")
    use_colors: BoolProperty(name="Colors")
    use_3mf_materials: BoolProperty(name="Materials", default=True)
    use_3mf_units: BoolProperty(name="Units", default=True)
    use_export_decimate: BoolProperty(name="Decimate")
    export_decimate_ratio: FloatProperty(
        name="Ratio",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
    )


class Print3DAddonPreferences(AddonPreferences):
    bl_idname = base_package

    export_presets: CollectionProperty(type=Print3DExportPreset)
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="Export Presets are managed from the 3D Print Toolbox panel.")


class Print3DSceneProperties(PropertyGroup):

    # Analyze
    # -------------------------------------

    threshold_zero: FloatProperty(
        name="Limit",
        subtype="DISTANCE",
        default=0.0001,
        min=0.0,
        max=0.2,
        precision=5,
        step=0.01
    )
    angle_nonplanar: FloatProperty(
        name="Limit",
        subtype="ANGLE",
        default=math.radians(5.0),
        min=0.0,
        max=math.radians(180.0),
        step=100,
    )
    thickness_min: FloatProperty(
        name="Minimum Thickness",
        subtype="DISTANCE",
        default=0.001,  # 1mm
        min=0.0,
        max=10.0,
        precision=3,
        step=0.1
    )
    angle_sharp: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        default=math.radians(160.0),
        min=0.0,
        max=math.radians(180.0),
        step=100,
    )
    angle_overhang: FloatProperty(
        name="Angle",
        subtype="ANGLE",
        default=math.radians(45.0),
        min=0.0,
        max=math.radians(90.0),
        step=100,
    )
    overhang_optimize_angle: FloatProperty(
        name="Target Angle",
        subtype="ANGLE",
        default=math.radians(45.0),
        min=0.0,
        max=math.radians(90.0),
        step=100,
    )
    overhang_optimize_iterations: IntProperty(
        name="Iterations",
        default=48,
        min=1,
        soft_max=256,
    )

    # Results Storage (Hidden)
    # -------------------------------------
    report_overhang: StringProperty(name="Overhang Report", default="", options={'HIDDEN'})
    report_intersections: StringProperty(name="Intersections Report", default="", options={'HIDDEN'})
    report_solid: StringProperty(name="Solid Report", default="", options={'HIDDEN'})
    report_thickness: StringProperty(name="Thickness Report", default="", options={'HIDDEN'})
    report_degenerate: StringProperty(name="Degenerate Report", default="", options={'HIDDEN'})
    report_distorted: StringProperty(name="Distorted Report", default="", options={'HIDDEN'})
    report_sharp: StringProperty(name="Sharp Report", default="", options={'HIDDEN'})

    # Multi-Object
    # -------------------------------------

    analyze_selected_objects: BoolProperty(
        name="All Selected",
        description="Analyze all selected mesh objects",
        default=False,
    )
    use_assembly_tolerance: BoolProperty(
        name="Assembly Tolerance",
        description="Check clearance between selected objects",
        default=False,
    )
    assembly_tolerance: FloatProperty(
        name="Tolerance",
        subtype="DISTANCE",
        default=0.0001,
        min=0.0,
        precision=4,
        step=0.01,
    )
    apply_tolerance_on_export: BoolProperty(
        name="Apply Tolerance on Export",
        description="Scale down export to account for assembly tolerance",
        default=False,
    )
    assembly_auto_iterations: IntProperty(
        name="Iterations",
        description="Maximum iterations used by automatic assembly clearance adjustment",
        default=8,
        min=1,
        soft_max=64,
    )
    assembly_auto_keep_active: BoolProperty(
        name="Keep Active Fixed",
        description="Keep the active object fixed and move only the others",
        default=True,
    )
    assembly_auto_scale_fallback: BoolProperty(
        name="Scale Fallback",
        description="If moving cannot satisfy tolerance, shrink violating objects uniformly",
        default=True,
    )
    assembly_auto_scale_iterations: IntProperty(
        name="Scale Iterations",
        description="Maximum scale fallback iterations",
        default=24,
        min=1,
        soft_max=128,
    )
    assembly_auto_scale_step: FloatProperty(
        name="Scale Step",
        description="Uniform reduction applied each fallback iteration (e.g. 0.01 = 1%)",
        default=0.01,
        min=0.0001,
        max=0.25,
        precision=4,
        step=0.1,
    )
    assembly_auto_scale_max_reduction: FloatProperty(
        name="Max Reduction",
        description="Maximum total uniform reduction per object during fallback",
        default=0.20,
        min=0.0,
        max=0.95,
        precision=3,
        step=0.1,
    )

    # Export
    # -------------------------------------

    export_path: StringProperty(
        name="Export Directory",
        default="//",
        maxlen=1024,
        subtype="DIR_PATH",
    )
    export_format: EnumProperty(
        name="Format",
        description="File format",
        items=(
            ("OBJ", "OBJ", ""),
            ("PLY", "PLY", ""),
            ("STL", "STL", ""),
            ("3MF", "3MF", ""),
        ),
        default="STL",
    )
    export_preset: EnumProperty(
        name="Preset",
        description="Choose a preset to apply saved export settings",
        items=_preset_items,
        update=lambda self, context: self.apply_preset(context),
    )
    use_ascii_format: BoolProperty(
        name="ASCII",
        description="Export file in ASCII format",
    )
    use_scene_scale: BoolProperty(
        name="Scene Scale",
        description="Apply scene scale on export",
    )
    use_copy_textures: BoolProperty(
        name="Copy Textures",
        description="Copy textures on export to the output path",
    )
    use_uv: BoolProperty(name="UVs")
    use_normals: BoolProperty(
        name="Normals",
        description="Export specific vertex normals if available, export calculated normals otherwise"
    )
    use_colors: BoolProperty(
        name="Colors",
        description="Export vertex color attributes",
    )
    use_3mf_materials: BoolProperty(
        name="Materials",
        description="Include materials in the 3MF export",
        default=True,
    )
    use_3mf_units: BoolProperty(
        name="Units",
        description="Write scene unit information to the 3MF export",
        default=True,
    )
    use_export_decimate: BoolProperty(
        name="Decimate",
        description="Automatically reduce mesh complexity on export",
        default=False,
    )
    export_decimate_ratio: FloatProperty(
        name="Decimate Ratio",
        description="Ratio of faces to keep (1.0 = no reduction)",
        default=1.0,
        min=0.0,
        max=1.0,
        precision=3,
        step=0.1,
    )

    def apply_preset(self, context) -> None:
        if not self.export_preset or context is None:
            return

        addon = context.preferences.addons.get(base_package)
        if addon is None:
            return

        prefs = addon.preferences
        index = int(self.export_preset)
        if index >= len(prefs.export_presets):
            return

        preset = prefs.export_presets[index]
        self.export_format = preset.export_format
        self.use_ascii_format = preset.use_ascii_format
        self.use_scene_scale = preset.use_scene_scale
        self.use_copy_textures = preset.use_copy_textures
        self.use_uv = preset.use_uv
        self.use_normals = preset.use_normals
        self.use_colors = preset.use_colors
        self.use_3mf_materials = preset.use_3mf_materials
        self.use_3mf_units = preset.use_3mf_units
        self.use_export_decimate = preset.use_export_decimate
        self.export_decimate_ratio = preset.export_decimate_ratio

    # Build Volume
    # -------------------------------------

    bed_profile: EnumProperty(
        name="Profile",
        description="Select a preset build volume or use a custom size",
        items=(
            ("ENDER3", "Ender 3 (220x220x250mm)", ""),
            ("PRUSA_MK4", "Prusa MK4 (250x210x220mm)", ""),
            ("BAMBULAB_P1P", "Bambu Lab P1P (256x256x256mm)", ""),
            ("CUSTOM", "Custom", ""),
        ),
        default="ENDER3",
    )
    show_bed_bounds: BoolProperty(
        name="Show Build Volume",
        description="Display printer build volume in the 3D Viewport",
        default=False,
    )
    bed_size_x: FloatProperty(
        name="Width",
        subtype="DISTANCE",
        default=BED_PROFILES["CUSTOM"][0],
        min=0.0,
    )
    bed_size_y: FloatProperty(
        name="Depth",
        subtype="DISTANCE",
        default=BED_PROFILES["CUSTOM"][1],
        min=0.0,
    )
    bed_size_z: FloatProperty(
        name="Height",
        subtype="DISTANCE",
        default=BED_PROFILES["CUSTOM"][2],
        min=0.0,
    )
    bed_report: StringProperty(
        name="",
        description="Last build volume validation result",
        default="",
        options={"HIDDEN"},
    )
    bed_axis_overflow: BoolVectorProperty(
        size=3,
        default=(False, False, False),
        options={"HIDDEN"},
    )

    @staticmethod
    def get_report():
        return report.info()
