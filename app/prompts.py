from __future__ import annotations

import json

from .models import DETAIL_LEVELS, DetailLevelConfig, ParsedProject


DEFAULT_DETAIL_LEVEL = "deep"


BASE_SYSTEM_SECTIONS: tuple[str, ...] = (
    "# System Overview",
    "## Project Purpose",
    "## Architecture Summary",
    "## Workflow and Control Logic",
    "## Key Components",
    "## Operational Risks and Notes",
)


BASE_DETAILED_SECTIONS: tuple[str, ...] = (
    "# Detailed Code Documentation",
    "## Module and Component Inventory",
    "## Logic Blocks and Responsibilities",
    "## Task-Level Observations",
    "## Integration and Dependency Notes",
    "## Maintenance Recommendations",
)


EXTRA_SYSTEM_SECTIONS: tuple[str, ...] = (
    "## Tasking and Execution Model",
    "## Data and Signal Interfaces",
)


EXTRA_DETAILED_SECTIONS: tuple[str, ...] = (
    "## Per-Component Deep Dive",
    "## Failure Modes and Diagnostics",
)


def normalize_detail_level(detail_level: str | None) -> str:
    normalized = (detail_level or "").strip().lower()
    if normalized in DETAIL_LEVELS:
        return normalized
    return DEFAULT_DETAIL_LEVEL


def detail_level_config(detail_level: str | None) -> DetailLevelConfig:
    return DETAIL_LEVELS[normalize_detail_level(detail_level)]


def system_required_sections(detail_level: str | None) -> tuple[str, ...]:
    normalized = normalize_detail_level(detail_level)
    if normalized in {"deep", "comprehensive"}:
        return BASE_SYSTEM_SECTIONS + EXTRA_SYSTEM_SECTIONS
    return BASE_SYSTEM_SECTIONS


def detailed_required_sections(detail_level: str | None) -> tuple[str, ...]:
    normalized = normalize_detail_level(detail_level)
    if normalized in {"deep", "comprehensive"}:
        return BASE_DETAILED_SECTIONS + EXTRA_DETAILED_SECTIONS
    return BASE_DETAILED_SECTIONS


def _build_snapshot(project: ParsedProject, max_nodes: int = 100) -> dict[str, object]:
    return {
        "source_file": project.source_file,
        "project_name": project.project_name,
        "root_tag": project.root_tag,
        "stats": project.stats,
        "tag_frequencies": project.tag_frequencies,
        "nodes": [
            {
                "name": node.name,
                "node_type": node.node_type,
                "tag": node.tag,
                "path": node.path,
                "attributes": node.attributes,
            }
            for node in project.nodes[:max_nodes]
        ],
    }


def _depth_instruction(config: DetailLevelConfig) -> str:
    if config.key == "basic":
        return "Provide practical detail while keeping the document compact and focused."
    if config.key == "standard":
        return "Provide balanced technical depth with section-level explanations and assumptions."
    if config.key == "deep":
        return "Provide deep technical documentation with explicit execution sequencing, dependencies, and assumptions."
    return "Provide comprehensive technical documentation suitable for onboarding, troubleshooting, and maintenance handover."


def _required_sections_block(sections: tuple[str, ...]) -> str:
    return "\n".join(f"{index}. {section}" for index, section in enumerate(sections, start=1))


def build_system_overview_prompt(project: ParsedProject, detail_level: str = DEFAULT_DETAIL_LEVEL) -> str:
    config = detail_level_config(detail_level)
    required_sections = system_required_sections(config.key)
    snapshot = json.dumps(_build_snapshot(project, max_nodes=config.overview_max_nodes), indent=2)
    return f"""
You are a senior industrial automation documentation engineer.

Create a Markdown system overview from parsed CODESYS project data.
Do not invent components that are not present in the input.
If data is missing, explicitly state assumptions.
{_depth_instruction(config)}
Target minimum content length: approximately {config.min_words_overview} words.

Required sections:
{_required_sections_block(required_sections)}

Input data:
```json
{snapshot}
```
""".strip()


def build_detailed_code_prompt(project: ParsedProject, detail_level: str = DEFAULT_DETAIL_LEVEL) -> str:
    config = detail_level_config(detail_level)
    required_sections = detailed_required_sections(config.key)
    snapshot = json.dumps(_build_snapshot(project, max_nodes=config.detailed_max_nodes), indent=2)
    return f"""
You are a PLC code analyst specializing in CODESYS projects.

Create a detailed Markdown code documentation report based on the parsed project data.
Do not hallucinate variable names or routines that do not exist in the input.
For each item, use what is known and clearly mark unknowns.
{_depth_instruction(config)}
Target minimum content length: approximately {config.min_words_detailed} words.

Required sections:
{_required_sections_block(required_sections)}

Input data:
```json
{snapshot}
```
""".strip()
