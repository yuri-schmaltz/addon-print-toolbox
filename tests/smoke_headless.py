# SPDX-License-Identifier: GPL-3.0-or-later

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import bpy


def _load_addon_module(root: Path):
    module_name = "print3d_toolbox"
    init_file = root / "__init__.py"

    spec = importlib.util.spec_from_file_location(
        module_name,
        init_file,
        submodule_search_locations=[str(root)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to create module spec for add-on")

    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


def _ensure_object_mode():
    if bpy.context.mode != "OBJECT":
        bpy.ops.object.mode_set(mode="OBJECT")


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    bpy.ops.wm.read_factory_settings(use_empty=True)
    _ensure_object_mode()

    addon = _load_addon_module(root)

    registered = False
    try:
        addon.register()
        registered = True

        bpy.ops.mesh.primitive_cube_add(size=1.0, enter_editmode=False)
        obj = bpy.context.active_object
        if obj is None or obj.type != "MESH":
            raise RuntimeError("Failed to create active mesh object")

        props = bpy.context.scene.print3d_toolbox

        result = bpy.ops.mesh.print3d_check_all()
        if "FINISHED" not in result:
            raise RuntimeError("Check All did not finish")

        if len(props.report_items) == 0:
            raise RuntimeError("No report items were produced")

        if not props.analysis_snapshot_json:
            raise RuntimeError("Analysis snapshot was not persisted")

        result = bpy.ops.mesh.print3d_advisor_analyze()
        if "FINISHED" not in result:
            raise RuntimeError("Advisor analysis did not finish")

        export_dir = root / "zips" / "smoke"
        export_path = export_dir / "smoke_cube.stl"
        props.export_format = "STL"
        result = bpy.ops.export_scene.print3d_export(filepath=str(export_path))
        if "FINISHED" not in result:
            raise RuntimeError("Export operator did not finish")
        if not export_path.exists():
            raise RuntimeError("Export file was not generated")

        result = bpy.ops.wm.print3d_report_clear()
        if "FINISHED" not in result:
            raise RuntimeError("Report clear did not finish")

        if props.analysis_snapshot_json:
            raise RuntimeError("Analysis snapshot was not cleared")
        if len(props.report_items) != 0:
            raise RuntimeError("Report items were not cleared")
        if len(props.advisor_suggestions) != 0:
            raise RuntimeError("Advisor suggestions were not cleared")

        print("Smoke test passed")
        return 0
    finally:
        if registered:
            addon.unregister()


if __name__ == "__main__":
    sys.exit(main())
