# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2013-2022 Campbell Barton
# SPDX-FileCopyrightText: 2024-2025 Mikhail Rachinskiy

class ReportManager:
    def __init__(self):
        self._data = []

    def update(self, *args):
        self._data[:] = args

    def info(self):
        return tuple(self._data)

    def clear(self):
        self._data.clear()

# Global instance for backward compatibility (could be attached to WindowManager ideally)
_manager = ReportManager()
update = _manager.update
info = _manager.info
clear = _manager.clear
