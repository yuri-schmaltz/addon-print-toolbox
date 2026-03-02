# SPDX-FileCopyrightText: 2021-2025 Mikhail Rachinskiy
# SPDX-License-Identifier: GPL-3.0-or-later

# v1.3.0

from pathlib import Path
from typing import Any

import bpy


def get_classes(modules: tuple[Any]) -> tuple[type]:
    bases = {
        bpy.types.AddonPreferences,
        bpy.types.Menu,
        bpy.types.Operator,
        bpy.types.Panel,
        bpy.types.PropertyGroup,
        bpy.types.UIList,
    }

    classes: list[type] = []
    seen: set[type] = set()

    for module in modules:
        for cls in module.__dict__.values():
            if isinstance(cls, type):
                for base in cls.__bases__:
                    if base in bases:
                        if cls not in seen:
                            classes.append(cls)
                            seen.add(cls)
                        break

    # Register PropertyGroup before AddonPreferences so CollectionProperty
    # types are guaranteed to exist at registration time.
    priority = {
        bpy.types.PropertyGroup: 0,
        bpy.types.AddonPreferences: 1,
        bpy.types.Operator: 2,
        bpy.types.UIList: 3,
        bpy.types.Menu: 4,
        bpy.types.Panel: 5,
    }

    def sort_key(cls: type) -> int:
        for base, value in priority.items():
            if issubclass(cls, base):
                return value
        return 99

    classes.sort(key=sort_key)

    return tuple(classes)


def reload_recursive(path: Path, mods: dict[str, Any]) -> None:
    import importlib

    for child in path.iterdir():

        if child.is_file() and child.suffix == ".py" and not child.name.startswith("__") and child.stem in mods:
            importlib.reload(mods[child.stem])

        elif child.is_dir() and not child.name.startswith((".", "__")):

            if child.name in mods:
                reload_recursive(child, mods[child.name].__dict__)
                importlib.reload(mods[child.name])
                continue

            reload_recursive(child, mods)


def check_integrity(path: Path) -> None:
    """:raises FileNotFoundError:"""

    if not path.exists():
        raise FileNotFoundError("Incorrect package, follow installation guide")
