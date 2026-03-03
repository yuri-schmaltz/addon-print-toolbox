# SPDX-License-Identifier: GPL-3.0-or-later
# SPDX-FileCopyrightText: 2026 Blender Foundation Contributors

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


_REPORT_NUMBER_RE = re.compile(r"^(?P<label>.+):\s*(?P<value>-?\d+(?:\.\d+)?)\s*$")


@dataclass(slots=True)
class AnalysisMetric:
    label: str
    value: int | float | str
    raw_text: str

    @staticmethod
    def from_report_line(text: str) -> "AnalysisMetric":
        match = _REPORT_NUMBER_RE.match(text.strip())
        if not match:
            return AnalysisMetric(label=text, value=text, raw_text=text)

        label = match.group("label").strip()
        value_text = match.group("value")
        if "." in value_text:
            value: int | float | str = float(value_text)
        else:
            value = int(value_text)
        return AnalysisMetric(label=label, value=value, raw_text=text)


@dataclass(slots=True)
class AdvisorSuggestion:
    suggestion_id: str
    message: str
    priority: str
    operator_id: str
    icon: str = "LIGHTBULB_ON"
    reason: str = ""
    evidence: str = ""
    data: dict[str, Any] | None = None


@dataclass(slots=True)
class AnalysisSnapshot:
    version: str
    created_at: str
    scene_name: str
    active_object: str
    source: str
    metrics: list[AnalysisMetric]

    @classmethod
    def create(
        cls,
        scene_name: str,
        active_object: str,
        source: str,
        report_lines: list[str],
        version: str = "1.0",
    ) -> "AnalysisSnapshot":
        return cls(
            version=version,
            created_at=datetime.now(timezone.utc).isoformat(),
            scene_name=scene_name,
            active_object=active_object,
            source=source,
            metrics=[AnalysisMetric.from_report_line(line) for line in report_lines],
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), separators=(",", ":"), ensure_ascii=True)

    @staticmethod
    def from_json(value: str) -> "AnalysisSnapshot | None":
        if not value:
            return None

        data = json.loads(value)
        metrics = [AnalysisMetric(**metric) for metric in data.get("metrics", [])]
        return AnalysisSnapshot(
            version=data.get("version", "1.0"),
            created_at=data.get("created_at", ""),
            scene_name=data.get("scene_name", ""),
            active_object=data.get("active_object", ""),
            source=data.get("source", "unknown"),
            metrics=metrics,
        )
