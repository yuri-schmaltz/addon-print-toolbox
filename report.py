# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2024-2025 Mikhail Rachinskiy
# SPDX-FileCopyrightText: 2026 Blender Foundation Contributors

from __future__ import annotations

import array

import bmesh
import bpy


_BM_TYPE_TO_ID = {
    bmesh.types.BMVert: "VERT",
    bmesh.types.BMEdge: "EDGE",
    bmesh.types.BMFace: "FACE",
}
_BM_ID_TO_TYPE = {value: key for key, value in _BM_TYPE_TO_ID.items()}


def _get_props(context=None):
    if context is None:
        context = bpy.context

    scene = getattr(context, "scene", None)
    if scene is None:
        return None

    return getattr(scene, "print3d_toolbox", None)


def _encode_indices(bm_array) -> str:
    return ",".join(str(int(index)) for index in bm_array)


def _decode_indices(text: str):
    if not text:
        return array.array("i", ())
    return array.array("i", (int(value) for value in text.split(",") if value))


def update(*args, context=None):
    props = _get_props(context)
    if props is None:
        return

    props.report_items.clear()
    for item in args:
        if not item:
            continue

        text, data = item
        entry = props.report_items.add()
        entry.text = str(text)
        entry.bm_type = "NONE"
        entry.bm_indices = ""

        if not data:
            continue

        if not isinstance(data, tuple) or len(data) != 2:
            continue

        bm_type, bm_array = data
        entry.bm_type = _BM_TYPE_TO_ID.get(bm_type, "NONE")
        if entry.bm_type != "NONE" and bm_array:
            entry.bm_indices = _encode_indices(bm_array)


def info(context=None):
    props = _get_props(context)
    if props is None:
        return tuple()

    data = []
    for entry in props.report_items:
        bm_type = _BM_ID_TO_TYPE.get(entry.bm_type)
        if bm_type is not None and entry.bm_indices:
            data_item = (bm_type, _decode_indices(entry.bm_indices))
        else:
            data_item = None
        data.append((entry.text, data_item))

    return tuple(data)


def clear(context=None):
    props = _get_props(context)
    if props is None:
        return
    props.report_items.clear()
