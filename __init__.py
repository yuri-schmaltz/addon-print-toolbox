# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2024 Campbell Barton
# SPDX-FileCopyrightText: 2016-2025 Mikhail Rachinskiy


if "bpy" in locals():
    from pathlib import Path
    essentials.reload_recursive(Path(__file__).parent, locals())
else:
    import bpy
    from bpy.props import PointerProperty

    from . import essentials, localization, operators, preferences, ui, draw_volume

from .core.runtime import logger


classes = essentials.get_classes((operators, preferences, ui))


def _safe_register_class(cls) -> None:
    try:
        bpy.utils.register_class(cls)
    except ValueError as exc:
        if "already registered" in str(exc):
            logger.info("Class already registered, skipping %s", cls.__name__)
            return
        raise


def _safe_unregister_class(cls) -> None:
    try:
        bpy.utils.unregister_class(cls)
    except RuntimeError as exc:
        if "missing bl_rna" in str(exc) or "not registered" in str(exc):
            return
        logger.warning("Failed to unregister %s: %s", cls.__name__, exc)


def register():
    for cls in classes:
        _safe_register_class(cls)

    if hasattr(bpy.types.Scene, "print3d_toolbox"):
        del bpy.types.Scene.print3d_toolbox
    bpy.types.Scene.print3d_toolbox = PointerProperty(type=preferences.Print3DSceneProperties)

    if "draw_volume" in globals():
        draw_volume.register()

    # Translations
    # ---------------------------

    try:
        bpy.app.translations.register(__package__, localization.DICTIONARY)
    except ValueError as exc:
        if "already registered" not in str(exc):
            raise


def unregister():
    # Defensive unregistration
    for cls in reversed(classes if isinstance(classes, (list, tuple)) else list(classes)):
        _safe_unregister_class(cls)

    if hasattr(bpy.types.Scene, "print3d_toolbox"):
        del bpy.types.Scene.print3d_toolbox
    
    if "draw_volume" in globals():
        draw_volume.unregister()

    # Translations
    # ---------------------------

    try:
        bpy.app.translations.unregister(__package__)
    except ValueError:
        # Can happen during reload/partial registration failures.
        return
