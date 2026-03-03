# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Blender Foundation Contributors

import logging


LOGGER_NAME = "print3d_toolbox"
logger = logging.getLogger(LOGGER_NAME)


def exception_text(exc: Exception) -> str:
    text = str(exc).strip().replace("\n", " ")
    return text if text else exc.__class__.__name__

