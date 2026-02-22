# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy
# SPDX-FileCopyrightText: 2022 Align XY by Jaggz H.
# SPDX-FileCopyrightText: 2024-2025 Hollow by Ubiratan Freitas

import math

import importlib
import importlib.util

import bmesh
import bpy
from bpy.app.translations import pgettext_tip as tip_
from bpy.props import BoolProperty, EnumProperty, FloatProperty, IntProperty
from bpy.types import Operator


class MESH_OT_hollow(Operator):
    bl_idname = "mesh.print3d_hollow"
    bl_label = "Hollow"
    bl_description = "Create offset surface"
    bl_options = {"REGISTER", "UNDO", "PRESET"}

    offset_direction: EnumProperty(
        name="Offset Direction",
        description="Offset direction relative to the object surface",
        items=(
            ("INSIDE", "Inside", ""),
            ("OUTSIDE", "Outside", ""),
        ),
        default="INSIDE",
    )
    offset: FloatProperty(
        name="Offset",
        description="Surface offset in relation to original mesh",
        subtype="DISTANCE",
        min=0.0,
        step=1,
        default=1.0,
    )
    voxel_size: FloatProperty(
        name="Voxel Size",
        description="Size of the voxel used for volume evaluation. Lower values preserve finer details",
        subtype="DISTANCE",
        min=0.0001,
        step=1,
        default=1.0,
    )
    make_hollow_duplicate: BoolProperty(
        name="Hollow Duplicate",
        description="Create hollowed out copy of the object",
    )

    def draw(self, context):
        layout = self.layout
        layout.use_property_split = True
        layout.use_property_decorate = False

        layout.separator()

        layout.prop(self, "offset_direction", expand=True)
        layout.prop(self, "offset")
        layout.prop(self, "voxel_size")
        layout.prop(self, "make_hollow_duplicate")

    def execute(self, context):
        numpy_spec = importlib.util.find_spec("numpy")
        if numpy_spec is None:
            self.report({"ERROR"}, "NumPy is required for hollowing. Install numpy and try again")
            return {"CANCELLED"}

        np = importlib.import_module("numpy")

        vdb_module = "openvdb" if bpy.app.version >= (4, 4, 0) else "pyopenvdb"
        vdb_spec = importlib.util.find_spec(vdb_module)
        if vdb_spec is None:
            self.report({"ERROR"}, f"{vdb_module} is required for hollowing. Install the dependency and try again")
            return {"CANCELLED"}

        vdb = importlib.import_module(vdb_module)

        if not self.offset:
            return {"FINISHED"}

        obj = context.active_object
        depsgraph = context.evaluated_depsgraph_get()
        mesh_target = bpy.data.meshes.new_from_object(obj.evaluated_get(depsgraph))

        # Apply transforms, avoid translating the mesh
        mat = obj.matrix_world.copy()
        mat.translation.zero()
        mesh_target.transform(mat)

        # Read mesh to numpy arrays
        nverts = len(mesh_target.vertices)
        ntris = len(mesh_target.loop_triangles)
        verts = np.zeros(3 * nverts, dtype=np.float32)
        tris = np.zeros(3 * ntris, dtype=np.int32)
        mesh_target.vertices.foreach_get("co", verts)
        verts.shape = (-1, 3)
        mesh_target.loop_triangles.foreach_get("vertices", tris)
        tris.shape = (-1, 3)

        # Generate VDB levelset
        half_width = max(3.0, math.ceil(abs(self.offset) / self.voxel_size) + 2.0) # half_width has to envelop offset
        trans = vdb.createLinearTransform(self.voxel_size)
        levelset = vdb.FloatGrid.createLevelSetFromPolygons(verts, triangles=tris, transform=trans, halfWidth=half_width)

        # Generate offset surface
        if self.offset_direction == "INSIDE":
            newverts, newquads = levelset.convertToQuads(-self.offset)
            if newquads.size == 0:
                self.report({"ERROR"}, "Make sure target mesh has closed surface and offset value is less than half of target thickness")
                return {"FINISHED"}
        else:
            newverts, newquads = levelset.convertToQuads(self.offset)

        bpy.ops.object.select_all(action="DESELECT")
        mesh_offset = bpy.data.meshes.new(mesh_target.name + " offset")
        mesh_offset.from_pydata(newverts, [], list(newquads))

        # For some reason OpenVDB has inverted normals
        mesh_offset.flip_normals()
        obj_offset = bpy.data.objects.new(obj.name + " offset", mesh_offset)
        obj_offset.matrix_world.translation = obj.matrix_world.translation
        bpy.context.collection.objects.link(obj_offset)
        obj_offset.select_set(True)
        context.view_layer.objects.active = obj_offset

        if self.make_hollow_duplicate:
            obj_hollow = bpy.data.objects.new(obj.name + " hollow", mesh_target)
            bpy.context.collection.objects.link(obj_hollow)
            obj_hollow.matrix_world.translation = obj.matrix_world.translation
            obj_hollow.select_set(True)
            if self.offset_direction == "INSIDE":
                mesh_offset.flip_normals()
            else:
                mesh_target.flip_normals()
            context.view_layer.objects.active = obj_hollow
            bpy.ops.object.join()
        else:
            bpy.data.meshes.remove(mesh_target)

        return {"FINISHED"}

    def invoke(self, context, event):
        if not context.selected_objects:
            return {"CANCELLED"}

        if context.mode == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="OBJECT")

        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class OBJECT_OT_align_xy(Operator):
    bl_idname = "object.print3d_align_xy"
    bl_label = "Align XY"
    bl_description = "Rotate object so the selected faces lie, on average, parallel to the XY plane"
    bl_options = {"REGISTER", "UNDO"}

    use_face_area: BoolProperty(
        name="Weight by Face Area",
        description="Take face area into account when calculating rotation",
        default=True,
    )

    def execute(self, context):
        """Perform object alignment rotation using face normal weighting.
        
        Calculates the average normal of selected faces and rotates the 
        object world matrix via pure Quaternion decomposition. This ensures 
        existing scale and positional data remains intact.
        
        Args:
            context: The execution context containing selected objects.
        """
        # FIXME: Undo is inconsistent.
        # FIXME: Would be nicer if rotate could pick some object-local axis.

        from mathutils import Vector

        self.context = context
        mode_orig = context.mode
        skip_invalid = []

        for obj in context.selected_objects:
            orig_loc = obj.location.copy()
            orig_scale = obj.scale.copy()

            # When in edit mode, do as the edit mode does.
            if mode_orig == "EDIT_MESH":
                bm = bmesh.from_edit_mesh(obj.data)
                faces = [f for f in bm.faces if f.select]
            else:
                faces = [p for p in obj.data.polygons if p.select]

            if not faces:
                skip_invalid.append(obj.name)
                continue

            # Rotate object so average normal of selected faces points down.
            normal = Vector((0.0, 0.0, 0.0))
            if self.use_face_area:
                for face in faces:
                    if mode_orig == "EDIT_MESH":
                        normal += (face.normal * face.calc_area())
                    else:
                        normal += (face.normal * face.area)
            else:
                for face in faces:
                    normal += face.normal
                    
            if normal.length_squared < 1e-6:
                skip_invalid.append(obj.name)
                continue
                
            normal = normal.normalized()
            normal.rotate(obj.matrix_world)  # local -> world.
            
            # Decompose current matrix to extract pure rotation
            loc, rot, scale = obj.matrix_world.decompose()
            
            offset_quat = normal.rotation_difference(Vector((0.0, 0.0, -1.0)))
            
            # Pre-multiply offset by current rotation
            new_rot = offset_quat @ rot
            
            # Recompose the matrix without modifying original translation and scale
            # To handle non-uniform scale correctly, we construct a 4x4 matrix from parts
            from mathutils import Matrix
            new_mat = Matrix.LocRotScale(loc, new_rot, scale)
            obj.matrix_world = new_mat

        if len(skip_invalid) > 0:
            for name in skip_invalid:
                print(tip_("Align to XY: Skipping object {}. No faces selected").format(name))
            if len(skip_invalid) == 1:
                self.report({"WARNING"}, tip_("Skipping object {}. No faces selected").format(skip_invalid[0]))
            else:
                self.report({"WARNING"}, "Skipping some objects. No faces selected. See terminal")
        return {"FINISHED"}

    def invoke(self, context, event):
        if context.mode not in {"EDIT_MESH", "OBJECT"}:
            return {"CANCELLED"}
        return self.execute(context)


def _bounds_lengths(obj, depsgraph):
    from mathutils import Vector

    obj_eval = obj.evaluated_get(depsgraph)
    coords = [Vector(v) @ obj_eval.matrix_world for v in obj_eval.bound_box]
    return tuple(max(c[i] for c in coords) - min(c[i] for c in coords) for i in range(3))


class OBJECT_OT_check_bed_fit(Operator):
    bl_idname = "object.print3d_check_bed_fit"
    bl_label = "Check Bed Fit"
    bl_description = "Compare the active object's bounds against the selected build volume"
    bl_options = {"REGISTER", "UNDO"}

    auto_scale: BoolProperty(
        name="Auto Scale",
        description="Scale the selection uniformly to fit the selected build volume",
        default=False,
    )
    highlight_axes: BoolProperty(
        name="Highlight Overflow Axes",
        description="Flag axes that exceed the build volume in the panel output",
        default=True,
    )

    def _update_report(self, props, lines: list[str], flags: tuple[bool, bool, bool]):
        props.bed_report = "\n".join(lines)
        props.bed_axis_overflow = flags

    def execute(self, context):
        from .. import lib
        from ..preferences import bed_profile_dimensions

        obj = context.active_object
        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Active object must be a mesh")
            return {"CANCELLED"}

        props = context.scene.print3d_toolbox
        bed_dims = bed_profile_dimensions(props)

        if any(dim <= 0.0 for dim in bed_dims):
            self.report({"ERROR"}, "Build volume dimensions must be greater than zero")
            return {"CANCELLED"}

        depsgraph = context.evaluated_depsgraph_get()
        lengths = _bounds_lengths(obj, depsgraph)

        overflows = []
        for i, axis in enumerate("XYZ"):
            if lengths[i] > bed_dims[i]:
                overflows.append((i, axis))

        lines = [tip_("Build volume"), tip_("X/Y/Z: {} / {} / {}").format(*[lib.clean_float(v, 4) for v in bed_dims])]
        flags = [False, False, False]

        if overflows and self.auto_scale:
            valid_lengths = [bed_dims[i] / lengths[i] for i in range(3) if lengths[i] > 0]
            if not valid_lengths:
                self.report({"WARNING"}, "Object has zero bounds")
                return {"CANCELLED"}

            scale = min(valid_lengths)
            _scale(scale, report=self.report, report_suffix=tip_(", Fit to build volume"))

            lengths = _bounds_lengths(obj, depsgraph)
            overflows.clear()
            for i, axis in enumerate("XYZ"):
                if lengths[i] > bed_dims[i]:
                    overflows.append((i, axis))

            lines.append(tip_("Auto scale applied: {}x").format(lib.clean_float(scale, 4)))

        if not overflows:
            lines.append(tip_("Fits within build volume"))
        else:
            lines.append(tip_("Does not fit: exceeds {} axis").format(", ".join(axis for _, axis in overflows)))

        for i, axis in enumerate("XYZ"):
            limit = bed_dims[i]
            length = lengths[i]
            overflow = max(length - limit, 0.0)
            label = tip_("{0}: {1} / {2}").format(axis, lib.clean_float(length, 4), lib.clean_float(limit, 4))
            if overflow > 0.0:
                label += tip_(" (+{})").format(lib.clean_float(overflow, 4))
                flags[i] = True
            lines.append(label)

        if not self.highlight_axes:
            flags = (False, False, False)
        else:
            flags = tuple(flags)

        self._update_report(props, lines, flags)
        return {"FINISHED"}


def _scale(scale: float, report=None, report_suffix="") -> None:
    from .. import lib

    if scale != 1.0:
        bpy.ops.transform.resize(value=(scale,) * 3)

    if report is not None:
        scale_fmt = lib.clean_float(scale, 6)
        report({"INFO"}, tip_("Scaled by {}").format(scale_fmt) + report_suffix)


class MESH_OT_scale_to_volume(Operator):
    bl_idname = "mesh.print3d_scale_to_volume"
    bl_label = "Scale to Volume"
    bl_description = "Scale edit-mesh or selected-objects to a set volume"
    bl_options = {"REGISTER", "UNDO"}

    volume_init: FloatProperty(
        options={"HIDDEN"},
    )
    volume: FloatProperty(
        name="Volume",
        unit="VOLUME",
        min=0.0,
        max=100000.0,
        step=1,
    )

    def execute(self, context):
        from .. import lib
        
        if self.volume_init <= 1e-6:
            self.report({"WARNING"}, "Object original volume is too small or invalid for scaling")
            return {"CANCELLED"}
            
        scale = math.pow(self.volume, 1 / 3) / math.pow(self.volume_init, 1 / 3)
        scale_fmt = lib.clean_float(scale, 6)
        self.report({"INFO"}, tip_("Scaled by {}").format(scale_fmt))
        _scale(scale, self.report)
        return {"FINISHED"}

    def invoke(self, context, event):

        def calc_volume(obj):
            from .. import lib

            bm = lib.bmesh_copy_from_object(obj, apply_modifiers=True)
            volume = bm.calc_volume(signed=True)
            bm.free()
            return volume

        if not context.selectable_objects:
            self.report({"ERROR"}, "At least one mesh object must be selected")
            return {"CANCELLED"}

        if context.mode == "EDIT_MESH":
            volume = calc_volume(context.edit_object)
        else:
            volume = sum(calc_volume(obj) for obj in context.selected_editable_objects if obj.type == "MESH")

        if volume == 0.0:
            self.report({"WARNING"}, "Object has zero volume")
            return {"CANCELLED"}

        self.volume_init = self.volume = abs(volume)

        wm = context.window_manager
        return wm.invoke_props_dialog(self)


class MESH_OT_scale_to_bounds(Operator):
    bl_idname = "mesh.print3d_scale_to_bounds"
    bl_label = "Scale to Bounds"
    bl_description = "Scale edit-mesh or selected-objects to fit within a maximum length"
    bl_options = {"REGISTER", "UNDO"}

    length_init: FloatProperty(
        options={"HIDDEN"},
    )
    axis_init: IntProperty(
        options={"HIDDEN"},
    )
    length: FloatProperty(
        name="Length",
        unit="LENGTH",
        min=0.0,
        max=100000.0,
        step=1,
    )

    def execute(self, context):
        if self.length_init <= 1e-6:
            self.report({"WARNING"}, "Object original bounds are too small for scaling")
            return {"CANCELLED"}
            
        scale = self.length / self.length_init
        axis = "XYZ"[self.axis_init]
        _scale(scale, report=self.report, report_suffix=tip_(", Clamping {}-Axis").format(axis))
        return {"FINISHED"}

    def invoke(self, context, event):
        from mathutils import Vector

        def calc_length(vecs):
            return max(((max(v[i] for v in vecs) - min(v[i] for v in vecs)), i) for i in range(3))

        if not context.selectable_objects:
            self.report({"ERROR"}, "At least one mesh object must be selected")
            return {"CANCELLED"}

        if context.mode == "EDIT_MESH":
            length, axis = calc_length(
                [Vector(v) @ obj.matrix_world for obj in [context.edit_object] for v in obj.bound_box]
            )
        else:
            length, axis = calc_length(
                [
                    Vector(v) @ obj.matrix_world for obj in context.selected_editable_objects
                    if obj.type == "MESH"
                    for v in obj.bound_box
                ]
            )

        if length == 0.0:
            self.report({"WARNING"}, "Object has zero bounds")
            return {"CANCELLED"}

        self.length_init = self.length = length
        self.axis_init = axis

        wm = context.window_manager
        return wm.invoke_props_dialog(self)
