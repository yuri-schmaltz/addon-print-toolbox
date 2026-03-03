# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Blender Foundation Contributors

import bpy


def operator_exists(module_name: str, op_name: str) -> bool:
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
    return operator_exists("export_scene", "threemf") or operator_exists("wm", "threemf_export")


def filtered_operator_kwargs(op, kwargs: dict) -> dict:
    try:
        rna = op.get_rna_type()
        valid = {prop.identifier for prop in rna.properties}
    except Exception:
        return kwargs

    return {key: value for key, value in kwargs.items() if key in valid}

