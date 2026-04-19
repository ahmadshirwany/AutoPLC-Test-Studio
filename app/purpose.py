from __future__ import annotations

from collections import defaultdict
import re

from .models import ParsedProject, PurposeResult


PURPOSE_KEYWORDS: dict[str, tuple[str, ...]] = {
    "material-handling": (
        "conveyor",
        "sorting",
        "sorter",
        "pallet",
        "transfer",
        "packaging",
        "bottle",
        "line",
    ),
    "liquid-handling": (
        "pump",
        "valve",
        "tank",
        "dosing",
        "mixing",
        "filling",
        "flow",
    ),
    "thermal-control": (
        "temperature",
        "heater",
        "cooling",
        "chiller",
        "furnace",
        "thermal",
    ),
    "safety-monitoring": (
        "alarm",
        "safety",
        "interlock",
        "trip",
        "emergency",
        "fault",
    ),
    "robotics-motion": (
        "robot",
        "servo",
        "axis",
        "motion",
        "position",
        "trajectory",
    ),
    "utilities-energy": (
        "compressor",
        "boiler",
        "power",
        "energy",
        "generator",
        "hvac",
    ),
}


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower())
    slug = re.sub(r"-+", "-", slug).strip("-")
    return slug[:64] if slug else "automation-project"


def _build_corpus(project: ParsedProject) -> str:
    parts = [project.project_name, project.root_tag]
    for node in project.nodes[:500]:
        parts.append(node.name)
        parts.append(node.tag)
    return " ".join(part.lower() for part in parts if part)


def detect_project_purpose(project: ParsedProject) -> PurposeResult:
    corpus = _build_corpus(project)
    scores: dict[str, int] = {}
    signals_by_label: dict[str, list[str]] = defaultdict(list)

    for label, keywords in PURPOSE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            occurrences = len(re.findall(rf"\b{re.escape(keyword)}\b", corpus))
            if occurrences:
                score += occurrences
                signals_by_label[label].append(keyword)
        scores[label] = score

    best_label = max(scores, key=scores.get)
    best_score = scores[best_label]
    total_score = sum(scores.values())

    if best_score < 2:
        fallback_slug = _slugify(project.project_name)
        return PurposeResult(
            purpose_label="general-automation",
            slug=fallback_slug,
            confidence=0.0,
            signals=[],
        )

    confidence = round(best_score / total_score, 2) if total_score else 0.0
    return PurposeResult(
        purpose_label=best_label,
        slug=_slugify(best_label),
        confidence=confidence,
        signals=sorted(set(signals_by_label[best_label])),
    )
