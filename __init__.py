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


classes = essentials.get_classes((operators, preferences, ui))


def register():
    for cls in classes:
        try:
            bpy.utils.register_class(cls)
        except ValueError:
            # Already registered as something else? Log it.
            print(f"Print3D Toolbox: Skipping registration of {cls}, already active.")

    bpy.types.Scene.print3d_toolbox = PointerProperty(type=preferences.Print3DSceneProperties)

    if 'draw_volume' in globals():
        draw_volume.register()

    # Translations
    # ---------------------------

    bpy.app.translations.register(__package__, localization.DICTIONARY)


def unregister():
    # Defensive unregistration
    for cls in reversed(classes if isinstance(classes, (list, tuple)) else list(classes)):
        try:
            bpy.utils.unregister_class(cls)
        except Exception:
            pass

    if hasattr(bpy.types.Scene, "print3d_toolbox"):
        del bpy.types.Scene.print3d_toolbox
    
    if 'draw_volume' in globals():
        draw_volume.unregister()

    # Translations
    # ---------------------------

    try:
        bpy.app.translations.unregister(__package__)
    except Exception:
        pass
