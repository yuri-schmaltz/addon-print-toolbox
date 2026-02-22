# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy

import array
import random
import os
from concurrent.futures import ThreadPoolExecutor
from collections.abc import Iterator, MutableSequence

import bmesh
import bpy
import mathutils
from bmesh.types import BMesh, BMFace
from bpy.types import Object
from mathutils import Vector


def clean_float(value: float, precision: int = 0) -> str:
    # Avoid scientific notation and strip trailing zeros: 0.000 -> 0.0

    text = f"{value:.{precision}f}"
    index = text.rfind(".")

    if index != -1:
        index += 2
        head, tail = text[:index], text[index:]
        tail = tail.rstrip("0")
        text = head + tail

    return text


# Mesh
# -------------------------------------


def bmesh_copy_from_object(obj: Object, transform=True, triangulate=True, apply_modifiers=False) -> BMesh:
    """Returns a transformed, triangulated copy of the mesh"""

    assert obj.type == "MESH"

    if apply_modifiers and obj.modifiers:
        depsgraph = bpy.context.evaluated_depsgraph_get()
        obj_eval = obj.evaluated_get(depsgraph)
        me = obj_eval.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(me)
        obj_eval.to_mesh_clear()
    else:
        me = obj.data
        if obj.mode == "EDIT":
            bm_orig = bmesh.from_edit_mesh(me)
            bm = bm_orig.copy()
        else:
            bm = bmesh.new()
            bm.from_mesh(me)

    # TODO. remove all customdata layers.
    # would save ram

    if transform:
        mat = obj.matrix_world.copy()
        # Avoid floating-point error when object is far away from scene center
        mat.translation.zero()
        if not mat.is_identity:
            bm.transform(mat)
            # Update normals if matrix has no rotation.
            bm.normal_update()

    if triangulate:
        bmesh.ops.triangulate(bm, faces=bm.faces)

    return bm


def bmesh_from_object(obj: Object) -> BMesh:
    """Object/Edit Mode get mesh, use bmesh_to_object() to write back."""
    me = obj.data

    if obj.mode == "EDIT":
        bm = bmesh.from_edit_mesh(me)
    else:
        bm = bmesh.new()
        bm.from_mesh(me)

    return bm


def bmesh_to_object(obj: Object, bm: BMesh) -> None:
    """Object/Edit Mode update the object."""
    me = obj.data

    if obj.mode == "EDIT":
        bmesh.update_edit_mesh(me, loop_triangles=True)
    else:
        bm.to_mesh(me)
        me.update()


def bmesh_calc_area(bm: BMesh) -> float:
    """Calculate the surface area."""
    return sum(f.calc_area() for f in bm.faces)


def bmesh_check_self_intersect_object(obj: Object) -> MutableSequence[int]:
    """Check if any faces self intersect returns an array of edge index values."""

    if not obj.data.polygons:
        return array.array("i", ())

    bm = bmesh_copy_from_object(obj, transform=False, triangulate=False)
    tree = mathutils.bvhtree.BVHTree.FromBMesh(bm, epsilon=0.00001)
    overlap = tree.overlap(tree)
    faces_error = {i for i_pair in overlap for i in i_pair}

    return array.array("i", faces_error)


def _bmesh_face_points_random(f: BMFace, num_points=1, margin=0.05) -> Iterator[Vector]:
    # for pradictable results
    random.seed(f.index)

    uniform_args = 0.0 + margin, 1.0 - margin
    vecs = [v.co for v in f.verts]

    for _ in range(num_points):
        u1 = random.uniform(*uniform_args)
        u2 = random.uniform(*uniform_args)
        u_tot = u1 + u2

        if u_tot > 1.0:
            u1 = 1.0 - u1
            u2 = 1.0 - u2

        side1 = vecs[1] - vecs[0]
        side2 = vecs[2] - vecs[0]

        yield vecs[0] + u1 * side1 + u2 * side2


def bmesh_check_thick_object(obj: Object, thickness: float, context) -> MutableSequence[int]:
    """Check for wall thickness using parallel BVH raycasting.
    
    This replaces the slow sequential scene-based raycasting with a 
    pure-memory BVH tree approach that scales with CPU cores.
    """
    import mathutils

    # Triangulate for consistent ray-intersection
    bm = bmesh_copy_from_object(obj, transform=True, triangulate=False)
    face_index_map_org = {f: i for i, f in enumerate(bm.faces)}
    ret = bmesh.ops.triangulate(bm, faces=bm.faces)
    face_map = ret["face_map"]
    
    # Build BVH Tree for fast raycasting
    tree = mathutils.bvhtree.BVHTree.FromBMesh(bm)
    
    faces_error = set()
    bm_faces_new = bm.faces[:]
    num_faces = len(bm_faces_new)
    
    if num_faces == 0:
        bm.free()
        return array.array("i", [])

    # Optimization: tune chunk size based on face count
    cpu_count = os.cpu_count() or 4
    chunk_size = max(100, num_faces // (cpu_count * 4))
    
    def process_face_chunk(faces_chunk):
        local_errors = set()
        EPS_BIAS = 0.0001
        
        for f in faces_chunk:
            no = f.normal
            no_sta = no * EPS_BIAS
            no_end = no * thickness
            
            # Use random sampling for better surface coverage
            for p in _bmesh_face_points_random(f, num_points=6):
                p_a = p - no_sta
                p_b = p - no_end
                p_dir = p_b - p_a
                dist_max = p_dir.length
                
                # tree.ray_cast(origin, direction, distance)
                _co, _no, index, _dist = tree.ray_cast(p_a, p_dir, dist_max)
                
                if index != -1:
                    # Found a hit within thickness threshold
                    for f_iter in (f, bm_faces_new[index]):
                        f_org = face_map.get(f_iter, f_iter)
                        local_errors.add(face_index_map_org[f_org])
        return local_errors

    # Execute in parallel
    chunks = [bm_faces_new[i:i + chunk_size] for i in range(0, num_faces, chunk_size)]
    
    with ThreadPoolExecutor(max_workers=cpu_count) as executor:
        results = executor.map(process_face_chunk, chunks)
        for local_set in results:
            faces_error.update(local_set)

    bm.free()
    return array.array("i", faces_error)


def face_is_distorted(face: BMFace, angle: float) -> bool:
    face_no = face.normal
    get_angle = face_no.angle

    for loop in face.loops:
        loop_no = loop.calc_normal()

        if loop_no.dot(face_no) < 0.0:
            loop_no.negate()

        # For some reason Split Non-Planar Faces operator calculates 2x angle
        if (get_angle(loop_no, 1000.0) * 2.0) > angle:
            return True

    return False
