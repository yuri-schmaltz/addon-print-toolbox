# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2024-2025 Mikhail Rachinskiy

import bpy
import gpu
from gpu_extras.batch import batch_for_shader
from .preferences import bed_profile_dimensions

_handle_view3d = None


def draw_callback_px():
    context = bpy.context
    if not hasattr(context.scene, "print3d_toolbox"):
        return
        
    props = context.scene.print3d_toolbox
    if not props.show_bed_bounds:
        return
        
    x, y, z = bed_profile_dimensions(props)
    if x <= 0 or y <= 0 or z <= 0:
        return
        
    # Bed is usually centered at X/Y and extends Z upwards
    hx, hy = x / 2.0, y / 2.0
    vertices = (
        (-hx, -hy, 0), (hx, -hy, 0), (hx, hy, 0), (-hx, hy, 0),
        (-hx, -hy, z), (hx, -hy, z), (hx, hy, z), (-hx, hy, z)
    )

    indices = (
        (0, 1), (1, 2), (2, 3), (3, 0),
        (4, 5), (5, 6), (6, 7), (7, 4),
        (0, 4), (1, 5), (2, 6), (3, 7)
    )

    try:
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
    except ValueError:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        
    batch = batch_for_shader(shader, 'LINES', {"pos": vertices}, indices=indices)

    # Use theme color for selected edges
    theme = context.preferences.themes[0].view_3d
    color = theme.wire_edit
    
    shader.bind()
    shader.uniform_float("color", (color[0], color[1], color[2], 0.6))
    
    gpu.state.blend_set('ALPHA')
    gpu.state.line_width_set(2.0)
    batch.draw(shader)
    gpu.state.line_width_set(1.0)
    gpu.state.blend_set('NONE')


def register():
    global _handle_view3d
    if _handle_view3d is None:
        _handle_view3d = bpy.types.SpaceView3D.draw_handler_add(
            draw_callback_px, (), 'WINDOW', 'POST_VIEW'
        )


def unregister():
    global _handle_view3d
    if _handle_view3d is not None:
        bpy.types.SpaceView3D.draw_handler_remove(_handle_view3d, 'WINDOW')
        _handle_view3d = None
