# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy

import math

import bmesh
import bpy
from bmesh.types import BMEdge, BMFace, BMVert
from bpy.app.translations import pgettext_tip as tip_
from bpy.props import IntProperty
from bpy.types import Object, Operator
from mathutils import Euler, Matrix, Vector

from .. import report
from ..core.models import AnalysisSnapshot
from ..core.runtime import exception_text


def _get_unit(unit_system: str, unit: str) -> tuple[float, str]:
    # Returns unit length relative to meter and unit symbol

    units = {
        "METRIC": {
            "KILOMETERS": (1000.0, "km"),
            "METERS": (1.0, "m"),
            "CENTIMETERS": (0.01, "cm"),
            "MILLIMETERS": (0.001, "mm"),
            "MICROMETERS": (0.000001, "µm"),
        },
        "IMPERIAL": {
            "MILES": (1609.344, "mi"),
            "FEET": (0.3048, "\'"),
            "INCHES": (0.0254, "\""),
            "THOU": (0.0000254, "thou"),
        },
    }

    try:
        return units[unit_system][unit]
    except KeyError:
        fallback_unit = "CENTIMETERS" if unit_system == "METRIC" else "INCHES"
        return units[unit_system][fallback_unit]


class MESH_OT_info_volume(Operator):
    bl_idname = "mesh.print3d_info_volume"
    bl_label = "Calculate Volume"
    bl_description = "Report the volume of the active mesh"

    def execute(self, context):
        from .. import lib

        scene = context.scene
        unit = scene.unit_settings
        scale = 1.0 if unit.system == "NONE" else unit.scale_length
        obj = context.active_object

        bm = lib.bmesh_copy_from_object(obj, apply_modifiers=True)
        volume = bm.calc_volume()
        bm.free()

        if unit.system == "NONE":
            volume_fmt = lib.clean_float(volume, 8)
        else:
            length, symbol = _get_unit(unit.system, unit.length_unit)

            volume_unit = volume * (scale ** 3.0) / (length ** 3.0)
            volume_str = lib.clean_float(volume_unit, 4)
            volume_fmt = f"{volume_str} {symbol}"

        report.update((tip_("Volume: {}³").format(volume_fmt), None))

        return {"FINISHED"}


class MESH_OT_info_area(Operator):
    bl_idname = "mesh.print3d_info_area"
    bl_label = "Calculate Area"
    bl_description = "Report the surface area of the active mesh"

    def execute(self, context):
        from .. import lib

        scene = context.scene
        unit = scene.unit_settings
        scale = 1.0 if unit.system == "NONE" else unit.scale_length
        obj = context.active_object

        bm = lib.bmesh_copy_from_object(obj, apply_modifiers=True)
        area = lib.bmesh_calc_area(bm)
        bm.free()

        if unit.system == "NONE":
            area_fmt = lib.clean_float(area, 8)
        else:
            length, symbol = _get_unit(unit.system, unit.length_unit)

            area_unit = area * (scale ** 2.0) / (length ** 2.0)
            area_str = lib.clean_float(area_unit, 4)
            area_fmt = f"{area_str} {symbol}"

        report.update((tip_("Area: {}²").format(area_fmt), None))

        return {"FINISHED"}


# ---------------
# Geometry Checks


def execute_check(self, context):
    obj = context.active_object
    props = context.scene.print3d_toolbox

    info = []
    try:
        self.main_check(obj, info, context)
    except Exception as exc:
        err = exception_text(exc)
        self.report({"ERROR"}, tip_("{} check failed: {}").format(self.bl_label, err))
        report.update((tip_("{}: Failed ({})").format(self.bl_label, err), None))
        return {"CANCELLED"}

    report.update(*info)

    # Sync to scene properties for Smart Advisor
    if info:
        prop_map = {
            "mesh.print3d_check_solid": "report_solid",
            "mesh.print3d_check_intersect": "report_intersections",
            "mesh.print3d_check_degenerate": "report_degenerate",
            "mesh.print3d_check_nonplanar": "report_distorted",
            "mesh.print3d_check_thick": "report_thickness",
            "mesh.print3d_check_sharp": "report_sharp",
            "mesh.print3d_check_overhang": "report_overhang",
        }
        prop_name = prop_map.get(self.bl_idname)
        if prop_name:
            setattr(props, prop_name, " | ".join([item[0] for item in info]))

    _persist_analysis_snapshot(context, "single_check", info)

    multiple_obj_warning(self, context)

    return {"FINISHED"}


def _persist_analysis_snapshot(context, source: str, info_items: list[tuple[str, tuple | None]]) -> None:
    scene = context.scene
    props = scene.print3d_toolbox
    active_name = context.active_object.name if context.active_object else ""
    lines = [text for text, _data in info_items]
    snapshot = AnalysisSnapshot.create(
        scene_name=scene.name,
        active_object=active_name,
        source=source,
        report_lines=lines,
    )
    props.analysis_snapshot_json = snapshot.to_json()


def multiple_obj_warning(self, context) -> None:
    props = context.scene.print3d_toolbox
    if len(context.selected_objects) > 1 and not props.analyze_selected_objects:
        self.report({"WARNING"}, "Multiple selected objects. Only the active one will be evaluated")


class MESH_OT_check_solid(Operator):
    bl_idname = "mesh.print3d_check_solid"
    bl_label = "Solid"
    bl_description = "Check for geometry is solid (has valid inside/outside) and correct normals"

    @staticmethod
    def main_check(obj: Object, info: list, _context):
        import array
        from .. import lib

        # TODO bow-tie quads

        bm = lib.bmesh_copy_from_object(obj, transform=False, triangulate=False)

        edges_non_manifold = array.array("i", (i for i, ele in enumerate(bm.edges) if not ele.is_manifold))
        edges_non_contig = array.array("i", (i for i, ele in enumerate(bm.edges) if ele.is_manifold and (not ele.is_contiguous)))

        info.append((tip_("Non-manifold Edges: {}").format(len(edges_non_manifold)), (BMEdge, edges_non_manifold)))
        info.append((tip_("Bad Contiguous Edges: {}").format(len(edges_non_contig)), (BMEdge, edges_non_contig)))

        bm.free()

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_intersections(Operator):
    bl_idname = "mesh.print3d_check_intersect"
    bl_label = "Intersections"
    bl_description = "Check for self intersections"

    @staticmethod
    def main_check(obj: Object, info: list, _context):
        from .. import lib

        faces_intersect = lib.bmesh_check_self_intersect_object(obj)
        info.append((tip_("Intersect Face: {}").format(len(faces_intersect)), (BMFace, faces_intersect)))

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_degenerate(Operator):
    bl_idname = "mesh.print3d_check_degenerate"
    bl_label = "Degenerate"
    bl_description = "Check for zero area faces and zero length edges"

    @staticmethod
    def main_check(obj: Object, info: list, context):
        import array
        from .. import lib

        threshold = context.scene.print3d_toolbox.threshold_zero

        bm = lib.bmesh_copy_from_object(obj, transform=False, triangulate=False)

        faces_zero = array.array("i", (i for i, ele in enumerate(bm.faces) if ele.calc_area() <= threshold))
        edges_zero = array.array("i", (i for i, ele in enumerate(bm.edges) if ele.calc_length() <= threshold))

        info.append((tip_("Zero Faces: {}").format(len(faces_zero)), (BMFace, faces_zero)))
        info.append((tip_("Zero Edges: {}").format(len(edges_zero)), (BMEdge, edges_zero)))

        bm.free()

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_nonplanar(Operator):
    bl_idname = "mesh.print3d_check_nonplanar"
    bl_label = "Non-Planar"
    bl_description = "Check for non-flat faces"

    @staticmethod
    def main_check(obj: Object, info: list, context):
        import array
        from .. import lib

        angle_nonplanar = context.scene.print3d_toolbox.angle_nonplanar

        bm = lib.bmesh_copy_from_object(obj, transform=True, triangulate=False)
        bm.normal_update()

        faces_distort = array.array("i", (i for i, ele in enumerate(bm.faces) if lib.face_is_distorted(ele, angle_nonplanar)))

        info.append((tip_("Non-flat Faces: {}").format(len(faces_distort)), (BMFace, faces_distort)))

        bm.free()

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_thick(Operator):
    bl_idname = "mesh.print3d_check_thick"
    bl_label = "Thickness"
    bl_description = "Check for wall thickness below specified value"

    @staticmethod
    def main_check(obj: Object, info: list, context):
        from .. import lib

        thickness_min = context.scene.print3d_toolbox.thickness_min

        faces_error = lib.bmesh_check_thick_object(obj, thickness_min, context)
        info.append((tip_("Thin Faces: {}").format(len(faces_error)), (BMFace, faces_error)))

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_sharp(Operator):
    bl_idname = "mesh.print3d_check_sharp"
    bl_label = "Sharp"
    bl_description = "Check for edges sharper than a specified angle"

    @staticmethod
    def main_check(obj: Object, info: list, context):
        from .. import lib

        angle_sharp = context.scene.print3d_toolbox.angle_sharp

        bm = lib.bmesh_copy_from_object(obj, transform=True, triangulate=False)
        bm.normal_update()

        edges_sharp = [
            ele.index for ele in bm.edges
            if ele.is_manifold and ele.calc_face_angle_signed() > angle_sharp
        ]

        info.append((tip_("Sharp Edge: {}").format(len(edges_sharp)), (BMEdge, edges_sharp)))
        bm.free()

    def execute(self, context):
        return execute_check(self, context)


class MESH_OT_check_overhang(Operator):
    bl_idname = "mesh.print3d_check_overhang"
    bl_label = "Overhang"
    bl_description = "Check for faces that overhang past a specified angle"

    @staticmethod
    def main_check(obj: Object, info: list, context):
        from mathutils import Vector
        from .. import lib

        angle_overhang = (math.pi / 2.0) - context.scene.print3d_toolbox.angle_overhang

        if angle_overhang == math.pi:
            info.append(("Skipping Overhang", ()))
            return

        bm = lib.bmesh_copy_from_object(obj, transform=True, triangulate=False)
        bm.normal_update()

        z_down = Vector((0, 0, -1.0))
        z_down_angle = z_down.angle

        # 4.0 ignores zero area faces
        faces_overhang = [
            ele.index for ele in bm.faces
            if z_down_angle(ele.normal, 4.0) < angle_overhang
        ]

        info.append((tip_("Overhang Face: {}").format(len(faces_overhang)), (BMFace, faces_overhang)))
        bm.free()

    def execute(self, context):
        return execute_check(self, context)


class OBJECT_OT_optimize_overhang(Operator):
    bl_idname = "object.print3d_optimize_overhang"
    bl_label = "Optimize Overhang Orientation"
    bl_description = "Sample orientations and rotate the active object to reduce overhangs"
    bl_options = {"REGISTER", "UNDO"}

    @staticmethod
    def _iter_rotations(iterations: int):
        golden_angle = math.pi * (3.0 - math.sqrt(5.0))

        for i in range(iterations):
            yaw = (i * golden_angle) % (math.tau)
            pitch = math.acos(1.0 - 2.0 * ((i + 0.5) / iterations)) - (math.pi / 2.0)
            yield Euler((pitch, 0.0, yaw)).to_quaternion()

    @staticmethod
    def _overhang_score_fast(normals: list[Vector], quat: Matrix, limit_angle: float) -> tuple[int, float]:
        """Calculate overhang score using vector math instead of mesh transformation."""
        # Rotating the target vector by inverse rotation is equivalent to rotating 
        # the mesh normals by the rotation itself.
        z_down_local = (quat.inverted() @ Vector((0.0, 0.0, -1.0))).normalized()
        z_down_angle = z_down_local.angle
        angle_overhang = (math.pi / 2.0) - limit_angle

        overhang_count = 0
        min_angle = math.pi

        for no in normals:
            angle = z_down_angle(no, 4.0)
            min_angle = min(min_angle, angle)
            if angle < angle_overhang:
                overhang_count += 1

        return overhang_count, min_angle

    @staticmethod
    def _overhang_score(obj: Object, matrix_world: Matrix, limit_angle: float) -> tuple[int, float]:
        from .. import lib

        bm = lib.bmesh_copy_from_object(obj, transform=False, triangulate=False)

        mat = matrix_world.copy()
        mat.translation.zero()
        
        # Simple non-threaded version for initial score
        z_down = Vector((0.0, 0.0, -1.0))
        z_down_angle = z_down.angle
        angle_overhang = (math.pi / 2.0) - limit_angle

        overhang_count = 0
        min_angle = math.pi

        for face in bm.faces:
            world_no = (mat @ face.normal).normalized()
            angle = z_down_angle(world_no, 4.0)
            min_angle = min(min_angle, angle)
            if angle < angle_overhang:
                overhang_count += 1

        bm.free()

        return overhang_count, min_angle

    @staticmethod
    def _is_better(score: tuple[int, float], current: tuple[int, float]) -> bool:
        count, angle = score
        best_count, best_angle = current
        return count < best_count or (count == best_count and angle > best_angle)
    def execute(self, context):
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            return {"CANCELLED"}

        obj = context.active_object

        if obj is None or obj.type != "MESH":
            self.report({"ERROR"}, "Active object is not a mesh")
            return {"CANCELLED"}

        from .. import lib
        from concurrent.futures import ThreadPoolExecutor
        import os

        props = context.scene.print3d_toolbox
        iterations = max(1, props.overhang_optimize_iterations)
        limit_angle = props.overhang_optimize_angle

        loc, rot, scale = obj.matrix_world.decompose()
        
        # Pre-calculating normals in a local space including scale but NOT the solver rotation
        base_rot_mat = Matrix.LocRotScale(None, None, scale).to_3x3()
        bm = lib.bmesh_copy_from_object(obj, transform=False, triangulate=False)
        normals_world = [(base_rot_mat @ face.normal).normalized() for face in bm.faces]
        bm.free()

        best_rot = rot
        best_score = self._overhang_score_fast(normals_world, rot, limit_angle)

        def eval_rotation(quat_iter):
            candidate_rot = quat_iter @ rot
            score = self._overhang_score_fast(normals_world, candidate_rot, limit_angle)
            return candidate_rot, score

        cpu_count = os.cpu_count() or 4
        rotations = list(self._iter_rotations(iterations))
        
        with ThreadPoolExecutor(max_workers=cpu_count) as executor:
            for candidate_rot, score in executor.map(eval_rotation, rotations):
                if self._is_better(score, best_score):
                    best_score = score
                    best_rot = candidate_rot

        obj.matrix_world = Matrix.LocRotScale(loc, best_rot, scale)

        overhang_faces, min_angle = best_score
        angle_deg = math.degrees(min_angle)
        self.report(
            {"INFO"},
            tip_("Overhang optimized: {} overhang faces, smallest angle {:.1f}°").format(
                overhang_faces, angle_deg
            ),
        )

        multiple_obj_warning(self, context)

        return {"FINISHED"}


class MESH_OT_check_all(Operator):
    bl_idname = "mesh.print3d_check_all"
    bl_label = "Check All"
    bl_description = "Run all checks"
    bl_options = {"INTERNAL"}

    check_cls = (
        MESH_OT_check_solid,
        MESH_OT_check_intersections,
        MESH_OT_check_degenerate,
        MESH_OT_check_nonplanar,
        MESH_OT_check_thick,
        MESH_OT_check_sharp,
        MESH_OT_check_overhang,
    )

    @staticmethod
    def _check_object(obj: Object, include_data: bool, context) -> list[tuple[str, tuple | None]]:
        info_obj: list[tuple[str, tuple | None]] = []
        props = context.scene.print3d_toolbox
        prop_map = {
            MESH_OT_check_solid: "report_solid",
            MESH_OT_check_intersections: "report_intersections",
            MESH_OT_check_degenerate: "report_degenerate",
            MESH_OT_check_nonplanar: "report_distorted",
            MESH_OT_check_thick: "report_thickness",
            MESH_OT_check_sharp: "report_sharp",
            MESH_OT_check_overhang: "report_overhang",
        }

        for cls in MESH_OT_check_all.check_cls:
            count_pre = len(info_obj)
            try:
                cls.main_check(obj, info_obj, context)
            except Exception as exc:
                err = exception_text(exc)
                info_obj.append((tip_("{}: Failed ({})").format(cls.bl_label, err), None))
            
            # Sync to scene properties
            prop_name = prop_map.get(cls)
            if prop_name:
                results = info_obj[count_pre:]
                setattr(props, prop_name, " | ".join([item[0] for item in results]))

        if include_data:
            return [(f"{obj.name}: {text}", data) for text, data in info_obj]
        return [(f"{obj.name}: {text}", None) for text, _data in info_obj]

    @staticmethod
    def _assembly_clearance_info(objects: list[Object], tolerance: float) -> list[tuple[str, None]]:
        if len(objects) < 2 or tolerance <= 0.0:
            return []

        from mathutils import Vector

        def _bbox_world(ob: Object) -> tuple[Vector, Vector]:
            coords = [ob.matrix_world @ Vector(corner) for corner in ob.bound_box]
            mins = Vector((min(c[i] for c in coords) for i in range(3)))
            maxs = Vector((max(c[i] for c in coords) for i in range(3)))
            return mins, maxs

        def _axis_gap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
            if max_a < min_b:
                return min_b - max_a
            if max_b < min_a:
                return min_a - max_b
            return 0.0

        info = []
        tol_text = f"{tolerance:.4f}m"

        for i, obj_a in enumerate(objects):
            min_a, max_a = _bbox_world(obj_a)
            for obj_b in objects[i + 1:]:
                min_b, max_b = _bbox_world(obj_b)
                gaps = (
                    _axis_gap(min_a.x, max_a.x, min_b.x, max_b.x),
                    _axis_gap(min_a.y, max_a.y, min_b.y, max_b.y),
                    _axis_gap(min_a.z, max_a.z, min_b.z, max_b.z),
                )
                clearance = max(gaps)
                if clearance < tolerance:
                    info.append((
                        tip_("Assembly clearance {} vs {}: {:.4f}m is below tolerance {}".format(
                            obj_a.name, obj_b.name, clearance, tol_text,
                        )),
                        None,
                    ))

        return info

    def execute(self, context):
        obj = context.active_object
        props = context.scene.print3d_toolbox
        failed_labels = []

        if props.analyze_selected_objects:
            selected = [ob for ob in context.selected_objects if ob.type == "MESH"]
            if not selected:
                self.report({"ERROR"}, "No selected mesh objects to analyze")
                return {"CANCELLED"}

            info_batch: list[tuple[str, tuple | None]] = []
            for ob in selected:
                include_data = ob == obj
                info_batch.extend(self._check_object(ob, include_data, context))

            if props.use_assembly_tolerance:
                info_batch.extend(self._assembly_clearance_info(selected, props.assembly_tolerance))

            report.update(*info_batch)
            _persist_analysis_snapshot(context, "check_all_multi", info_batch)
        else:
            info = []
            for cls in self.check_cls:
                try:
                    cls.main_check(obj, info, context)
                except Exception as exc:
                    err = exception_text(exc)
                    failed_labels.append(cls.bl_label)
                    info.append((tip_("{}: Failed ({})").format(cls.bl_label, err), None))

            report.update(*info)
            _persist_analysis_snapshot(context, "check_all_single", info)

            multiple_obj_warning(self, context)

        if failed_labels:
            self.report({"WARNING"}, tip_("Checks failed: {}").format(", ".join(failed_labels)))

        return {"FINISHED"}


class OBJECT_OT_auto_clearance(Operator):
    bl_idname = "object.print3d_auto_clearance"
    bl_label = "Auto Adjust Clearance"
    bl_description = "Adjust contact regions by local scaling to satisfy assembly tolerance without moving objects"
    bl_options = {"REGISTER", "UNDO"}

    @staticmethod
    def _bbox_world(ob: Object) -> tuple[Vector, Vector]:
        coords = [ob.matrix_world @ Vector(corner) for corner in ob.bound_box]
        mins = Vector((min(c.x for c in coords), min(c.y for c in coords), min(c.z for c in coords)))
        maxs = Vector((max(c.x for c in coords), max(c.y for c in coords), max(c.z for c in coords)))
        return mins, maxs

    @staticmethod
    def _axis_gap(min_a: float, max_a: float, min_b: float, max_b: float) -> float:
        if max_a < min_b:
            return min_b - max_a
        if max_b < min_a:
            return min_a - max_b
        return 0.0

    @classmethod
    def _pair_adjustment(
        cls,
        obj_a: Object,
        obj_b: Object,
        tolerance: float,
        bounds: dict[str, tuple[Vector, Vector]],
    ) -> tuple[float, Vector]:
        min_a, max_a = bounds[obj_a.name]
        min_b, max_b = bounds[obj_b.name]

        gaps = (
            cls._axis_gap(min_a.x, max_a.x, min_b.x, max_b.x),
            cls._axis_gap(min_a.y, max_a.y, min_b.y, max_b.y),
            cls._axis_gap(min_a.z, max_a.z, min_b.z, max_b.z),
        )
        clearance = max(gaps)

        best_axis = 0
        best_dist = float("inf")
        best_sign = 1.0

        for axis in range(3):
            dist_pos = max(0.0, (max_a[axis] + tolerance) - min_b[axis])
            dist_neg = max(0.0, (max_b[axis] + tolerance) - min_a[axis])

            if dist_pos <= dist_neg:
                dist = dist_pos
                sign = 1.0
            else:
                dist = dist_neg
                sign = -1.0

            if dist < best_dist:
                best_dist = dist
                best_axis = axis
                best_sign = sign

        move_vec = Vector((0.0, 0.0, 0.0))
        if best_dist != float("inf"):
            move_vec[best_axis] = best_sign * best_dist

        return clearance, move_vec

    @classmethod
    def _collect_violations(
        cls,
        objects: list[Object],
        tolerance: float,
        bounds: dict[str, tuple[Vector, Vector]],
    ) -> list[tuple[Object, Object, float, Vector]]:
        violations = []

        for i, obj_a in enumerate(objects):
            for obj_b in objects[i + 1:]:
                clearance, move_vec = cls._pair_adjustment(obj_a, obj_b, tolerance, bounds)
                if clearance < tolerance:
                    violations.append((obj_a, obj_b, clearance, move_vec))

        return violations

    @staticmethod
    def _new_side_map(value: float = 0.0) -> dict[tuple[int, str], float]:
        return {(axis, side): value for axis in range(3) for side in ("MIN", "MAX")}

    @staticmethod
    def _ensure_single_user_mesh(obj: Object) -> None:
        if obj.type != "MESH":
            return
        if obj.data is not None and obj.data.users > 1:
            obj.data = obj.data.copy()

    @staticmethod
    def _apply_contact_adjustments(
        obj: Object,
        side_amounts: dict[tuple[int, str], float],
        band_widths: dict[int, float],
    ) -> int:
        me = obj.data
        if me is None or len(me.vertices) == 0:
            return 0

        bm = bmesh.new()
        bm.from_mesh(me)
        bm.verts.ensure_lookup_table()

        mat = obj.matrix_world
        mat_inv = mat.inverted_safe().to_3x3()

        verts = list(bm.verts)
        world_coords = [mat @ v.co for v in verts]
        axis_values = {
            0: [co.x for co in world_coords],
            1: [co.y for co in world_coords],
            2: [co.z for co in world_coords],
        }
        side_values = {
            (0, "MIN"): min(axis_values[0]),
            (0, "MAX"): max(axis_values[0]),
            (1, "MIN"): min(axis_values[1]),
            (1, "MAX"): max(axis_values[1]),
            (2, "MIN"): min(axis_values[2]),
            (2, "MAX"): max(axis_values[2]),
        }

        moved_count = 0
        eps = 1e-12

        for idx, v in enumerate(verts):
            co_w = world_coords[idx]
            delta_w = Vector((0.0, 0.0, 0.0))

            for axis in range(3):
                band = max(band_widths.get(axis, 0.0), 1e-9)
                for side in ("MIN", "MAX"):
                    amount = side_amounts.get((axis, side), 0.0)
                    if amount <= eps:
                        continue

                    boundary = side_values[(axis, side)]
                    distance = (boundary - co_w[axis]) if side == "MAX" else (co_w[axis] - boundary)

                    if distance < -eps or distance > band:
                        continue

                    weight = 1.0 - min(1.0, max(0.0, distance) / band)
                    if weight <= 0.0:
                        continue

                    direction = -1.0 if side == "MAX" else 1.0
                    delta_w[axis] += direction * amount * weight

            if delta_w.length_squared > eps:
                v.co += mat_inv @ delta_w
                moved_count += 1

        if moved_count:
            bm.normal_update()
            bm.to_mesh(me)
            me.update()

        bm.free()
        return moved_count

    def execute(self, context):
        if context.mode not in {"OBJECT", "EDIT_MESH"}:
            return {"CANCELLED"}

        props = context.scene.print3d_toolbox
        selected = [ob for ob in context.selected_objects if ob.type == "MESH"]
        tolerance = props.assembly_tolerance
        scale_iterations = max(1, props.assembly_auto_scale_iterations)
        use_contact_scaling = props.assembly_auto_scale_fallback
        scale_step = min(max(props.assembly_auto_scale_step, 0.0001), 0.5)
        max_reduction = min(max(props.assembly_auto_scale_max_reduction, 0.0), 0.95)

        if len(selected) < 2:
            self.report({"ERROR"}, "Select at least two mesh objects")
            return {"CANCELLED"}

        if tolerance <= 0.0:
            self.report({"ERROR"}, "Tolerance must be greater than zero")
            return {"CANCELLED"}

        if not use_contact_scaling:
            self.report({"ERROR"}, "Enable Contact Scaling to adjust tolerance")
            return {"CANCELLED"}

        mode_orig = context.mode
        fixed_obj = context.active_object if (props.assembly_auto_keep_active and context.active_object in selected) else None

        if mode_orig == "EDIT_MESH":
            bpy.ops.object.mode_set(mode="OBJECT")

        try:
            for ob in selected:
                if fixed_obj is not None and ob == fixed_obj:
                    continue
                self._ensure_single_user_mesh(ob)

            context.view_layer.update()
            bounds = {ob.name: self._bbox_world(ob) for ob in selected}
            initial = self._collect_violations(selected, tolerance, bounds)

            if not initial:
                msg = tip_("Auto clearance: all selected objects already meet {:.4f}m tolerance").format(tolerance)
                report.update((msg, None))
                self.report({"INFO"}, msg)
                return {"FINISHED"}

            initial_extents = {}
            for ob in selected:
                mins, maxs = bounds[ob.name]
                initial_extents[ob.name] = (
                    max(maxs.x - mins.x, 1e-9),
                    max(maxs.y - mins.y, 1e-9),
                    max(maxs.z - mins.z, 1e-9),
                )

            used_reduction = {ob.name: self._new_side_map(0.0) for ob in selected}
            iterations_used = 0
            vertices_adjusted = 0

            for step in range(scale_iterations):
                context.view_layer.update()
                bounds = {ob.name: self._bbox_world(ob) for ob in selected}
                violations = self._collect_violations(selected, tolerance, bounds)
                if not violations:
                    break

                requests = {ob.name: self._new_side_map(0.0) for ob in selected}

                for obj_a, obj_b, _clearance, move_vec in violations:
                    axis = max(range(3), key=lambda i: abs(move_vec[i]))
                    needed = abs(move_vec[axis])
                    if needed <= 1e-12:
                        continue

                    if move_vec[axis] >= 0.0:
                        side_a, side_b = "MAX", "MIN"
                    else:
                        side_a, side_b = "MIN", "MAX"

                    if fixed_obj is not None:
                        if obj_a == fixed_obj and obj_b != fixed_obj:
                            key_b = (axis, side_b)
                            requests[obj_b.name][key_b] = max(requests[obj_b.name][key_b], needed)
                            continue
                        if obj_b == fixed_obj and obj_a != fixed_obj:
                            key_a = (axis, side_a)
                            requests[obj_a.name][key_a] = max(requests[obj_a.name][key_a], needed)
                            continue

                    half = needed * 0.5
                    key_a = (axis, side_a)
                    key_b = (axis, side_b)
                    requests[obj_a.name][key_a] = max(requests[obj_a.name][key_a], half)
                    requests[obj_b.name][key_b] = max(requests[obj_b.name][key_b], half)

                adjusted_any = False
                for ob in selected:
                    if fixed_obj is not None and ob == fixed_obj:
                        continue

                    extents = initial_extents[ob.name]
                    request_map = requests[ob.name]
                    apply_map = self._new_side_map(0.0)
                    band_widths = {}

                    for axis in range(3):
                        extent = extents[axis]
                        step_cap = extent * scale_step
                        side_limit = extent * max_reduction
                        band_widths[axis] = max(
                            extent * max(0.05, scale_step * 4.0),
                            step_cap * 2.0,
                            tolerance * 2.0,
                            1e-6,
                        )

                        for side in ("MIN", "MAX"):
                            key = (axis, side)
                            requested = request_map[key]
                            if requested <= 1e-12:
                                continue

                            remaining_limit = max(0.0, side_limit - used_reduction[ob.name][key])
                            if remaining_limit <= 1e-12:
                                continue

                            amount = min(requested, step_cap, remaining_limit)
                            if amount <= 1e-12:
                                continue
                            apply_map[key] = amount

                    if not any(amount > 1e-12 for amount in apply_map.values()):
                        continue

                    changed = self._apply_contact_adjustments(ob, apply_map, band_widths)
                    if changed > 0:
                        adjusted_any = True
                        vertices_adjusted += changed
                        for key, amount in apply_map.items():
                            if amount > 1e-12:
                                used_reduction[ob.name][key] += amount

                iterations_used = step + 1
                if not adjusted_any:
                    break

            context.view_layer.update()
            bounds = {ob.name: self._bbox_world(ob) for ob in selected}
            remaining = self._collect_violations(selected, tolerance, bounds)
            resolved = len(initial) - len(remaining)

            info = []
            summary = tip_("Auto clearance: resolved {}/{} pairs").format(resolved, len(initial))
            info.append((summary, None))
            self.report({"INFO"}, summary)

            scale_summary = tip_("Auto clearance contact scaling: {} iteration(s), {} vertices adjusted").format(
                iterations_used, vertices_adjusted,
            )
            info.append((scale_summary, None))
            self.report({"INFO"}, scale_summary)

            if remaining:
                warn = tip_("Auto clearance: {} pair(s) still below {:.4f}m tolerance").format(len(remaining), tolerance)
                info.append((warn, None))
                self.report({"WARNING"}, warn)
                for obj_a, obj_b, clearance, _move_vec in remaining[:20]:
                    info.append((
                        tip_("Assembly clearance {} vs {}: {:.4f}m is below tolerance {:.4f}m").format(
                            obj_a.name, obj_b.name, clearance, tolerance,
                        ),
                        None,
                    ))

            report.update(*info)
        finally:
            if mode_orig == "EDIT_MESH" and context.active_object is not None and context.active_object.type == "MESH":
                bpy.ops.object.mode_set(mode="EDIT")

        return {"FINISHED"}


class MESH_OT_report_select(Operator):
    bl_idname = "mesh.print3d_select_report"
    bl_label = "Select"
    bl_description = "Select the data associated with this report"
    bl_options = {"INTERNAL"}

    index: IntProperty()

    _type_to_mode = {
        BMVert: "VERT",
        BMEdge: "EDGE",
        BMFace: "FACE",
    }

    _type_to_attr = {
        BMVert: "verts",
        BMEdge: "edges",
        BMFace: "faces",
    }

    def execute(self, context):
        obj = context.edit_object
        info = report.info()

        if not info or self.index >= len(info):
            self.report({"ERROR"}, "Report is out of date, re-run check")
            return {"CANCELLED"}

        _text, data = info[self.index]

        if data is None:
            self.report({"ERROR"}, "Report is out of date, re-run check")
            return {"CANCELLED"}

        bm_type, bm_array = data

        bpy.ops.mesh.reveal()
        bpy.ops.mesh.select_all(action="DESELECT")
        bpy.ops.mesh.select_mode(type=self._type_to_mode[bm_type])

        bm = bmesh.from_edit_mesh(obj.data)
        elems = getattr(bm, MESH_OT_report_select._type_to_attr[bm_type])[:]

        for i in bm_array:
            try:
                elems[i].select_set(True)
            except IndexError:
                self.report({"ERROR"}, "Report is out of date, re-run check")
                return {"CANCELLED"}

        return {"FINISHED"}


class WM_OT_report_clear(Operator):
    bl_idname = "wm.print3d_report_clear"
    bl_label = "Clear Report"
    bl_description = "Clear report"
    bl_options = {"INTERNAL"}

    def execute(self, context):
        report.clear()
        props = context.scene.print3d_toolbox
        props.report_overhang = ""
        props.report_intersections = ""
        props.report_solid = ""
        props.report_thickness = ""
        props.report_degenerate = ""
        props.report_distorted = ""
        props.report_sharp = ""
        props.analysis_snapshot_json = ""
        props.advisor_suggestions.clear()
        return {"FINISHED"}
