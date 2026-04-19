from app.parser import parse_codesys_xml
from app.prompts import (
    build_detailed_code_prompt,
    build_system_overview_prompt,
    detailed_required_sections,
    normalize_detail_level,
    system_required_sections,
)


SIMPLE_XML = """
<Project Name="Tank Demo">
  <Device Name="MainPLC">
    <Task Name="MainTask">
      <Program Name="TankControl" />
    </Task>
  </Device>
</Project>
"""


def test_normalize_detail_level_defaults_to_deep() -> None:
    assert normalize_detail_level(None) == "deep"
    assert normalize_detail_level("unknown-value") == "deep"
    assert normalize_detail_level("standard") == "standard"


def test_deep_required_sections_include_extended_headings() -> None:
    system_sections = system_required_sections("deep")
    detailed_sections = detailed_required_sections("deep")

    assert "## Tasking and Execution Model" in system_sections
    assert "## Per-Component Deep Dive" in detailed_sections


def test_prompts_expand_for_deep_mode() -> None:
    parsed = parse_codesys_xml(SIMPLE_XML, source_file="tank.xml")

    system_prompt = build_system_overview_prompt(parsed, detail_level="deep")
    detailed_prompt = build_detailed_code_prompt(parsed, detail_level="deep")

    assert "Target minimum content length" in system_prompt
    assert "## Tasking and Execution Model" in system_prompt
    assert "## Per-Component Deep Dive" in detailed_prompt
