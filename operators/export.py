# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2023 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy

# Export wrappers and integration with external tools.

import bpy
from bpy.app.translations import pgettext_data as data_
from bpy.app.translations import pgettext_tip as tip_
from bpy.props import StringProperty
from bpy.types import Image, Material, Object, Operator


class EXPORT_SCENE_OT_export(Operator):
    bl_idname = "export_scene.print3d_export"
    bl_label = "Export"
    bl_description = "Export selected objects using settings below"
    bl_options = {"INTERNAL"}

    filepath: StringProperty(
        subtype="FILE_PATH",
        options={"SKIP_SAVE", "HIDDEN"},
    )

    @classmethod
    def poll(cls, context):
        return bool(context.selected_objects)

    def execute(self, context):
        unit = context.scene.unit_settings
        props = context.scene.print3d_toolbox

        global_scale = unit.scale_length if (unit.system != "NONE" and props.use_scene_scale) else 1.0

        if (
            props.use_assembly_tolerance
            and props.apply_tolerance_on_export
            and len(context.selected_objects) > 1
        ):
            dims = [max(obj.dimensions) for obj in context.selected_objects if obj.type == "MESH"]
            if dims:
                max_dim = max(dims)
                if max_dim > 0.0:
                    tolerance_scale = max(0.0, 1.0 - (props.assembly_tolerance / max_dim))
                    global_scale *= tolerance_scale

        path_mode = "COPY" if props.use_copy_textures else "AUTO"
        filepath = bpy.path.ensure_ext(self.filepath, f".{props.export_format.lower()}")

        # this can fail with strange errors,
        # if the dir can't be made then we get an error later.
        if not _ensure_export_dir(filepath, self.report):
            return {"CANCELLED"}

        if props.export_format == "STL":
            ret = bpy.ops.wm.stl_export(
                filepath=filepath,
                ascii_format=props.use_ascii_format,
                global_scale=global_scale,
                apply_modifiers=True,
                export_selected_objects=True,
            )
        elif props.export_format == "PLY":
            ret = bpy.ops.wm.ply_export(
                filepath=filepath,
                ascii_format=props.use_ascii_format,
                global_scale=global_scale,
                export_uv=props.use_uv,
                export_normals=props.use_normals,
                export_colors="SRGB" if props.use_colors else "NONE",
                apply_modifiers=True,
                export_selected_objects=True,
                export_attributes=False,
            )
        elif props.export_format == "OBJ":
            ret = bpy.ops.wm.obj_export(
                filepath=filepath,
                global_scale=global_scale,
                export_uv=props.use_uv,
                export_normals=props.use_normals,
                export_colors=props.use_colors,
                export_materials=props.use_copy_textures,
                path_mode=path_mode,
                apply_modifiers=True,
                export_selected_objects=True,
            )
        elif props.export_format == "3MF":
            ret = bpy.ops.export_scene.threemf(
                filepath=filepath,
                global_scale=global_scale,
                use_scene_unit=props.use_3mf_units,
                export_materials=props.use_3mf_materials,
                apply_modifiers=True,
                export_selected_objects=True,
            )
        else:
            assert 0

        # for formats that don't support images
        if path_mode == "COPY" and props.export_format in {"STL", "PLY"}:
            _image_copy_guess(filepath, context.selected_objects)

        if "FINISHED" in ret:
            self.report({"INFO"}, tip_("Exported: {!r}").format(filepath))
            return {"FINISHED"}

        self.report({"ERROR"}, "Export failed")
        return {"CANCELLED"}

    def invoke(self, context, event):
        import re
        from pathlib import Path

        if not context.selected_objects:
            return {"CANCELLED"}

        props = context.scene.print3d_toolbox

        if context.object:
            ob = context.object
        else:
            ob = context.selected_objects[0]

        ob_name = re.sub(r'[\\/:*?"<>|]', "", ob.name)

        if bpy.data.is_saved:
            blend_name = Path(bpy.data.filepath).stem
        else:
            blend_name = data_("Untitled")

        # Ensure blend_name is also safe just in case
        blend_name = re.sub(r'[\\/:*?"<>|]', "", blend_name)
        filename = f"{blend_name}-{ob_name}.{props.export_format.lower()}"

        if bpy.data.is_saved or (props.export_path and not props.export_path.startswith("//")):
            self.filepath = str(Path(bpy.path.abspath(props.export_path)) / filename)
        else:
            self.filepath = str(Path.home() / filename)

            wm = context.window_manager
            wm.fileselect_add(self)

            return {"RUNNING_MODAL"}

        return self.execute(context)


def _image_get(mat: Material) -> Image | None:
    from bpy_extras import node_shader_utils

    if mat.use_nodes:
        mat_wrap = node_shader_utils.PrincipledBSDFWrapper(mat)
        base_color_tex = mat_wrap.base_color_texture
        if base_color_tex and base_color_tex.image:
            return base_color_tex.image


def _image_copy_guess(filepath: str, objects: list[Object]) -> None:
    # 'filepath' is the path we are writing to.
    image = None
    mats = set()

    for obj in objects:
        for slot in obj.material_slots:
            if slot.material:
                mats.add(slot.material)

    for mat in mats:
        image = _image_get(mat)
        if image is not None:
            break

    if image is not None:
        import os
        import shutil

        imagepath = bpy.path.abspath(image.filepath, library=image.library)
        if os.path.exists(imagepath):
            filepath_noext = os.path.splitext(filepath)[0]
            ext = os.path.splitext(imagepath)[1]

            imagepath_dst = filepath_noext + ext
            print(f"copying texture: {imagepath!r} -> {imagepath_dst!r}")

            try:
                shutil.copy(imagepath, imagepath_dst)
            except Exception as exc:
                print(f"Error copying texture: {exc}")
                import traceback
                traceback.print_exc()


def _ensure_export_dir(filepath: str, report) -> bool:
    from pathlib import Path

    try:
        Path(filepath).parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        report({"ERROR"}, f"Cannot create export directory: {exc}")
        return False

    return True
