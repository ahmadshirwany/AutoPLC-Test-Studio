from pathlib import Path

from app.diagrams import build_mermaid_diagrams
from app.parser import parse_codesys_xml


def _load_fixture() -> str:
    fixture_path = Path(__file__).parent / "fixtures" / "sample_codesys.xml"
    return fixture_path.read_text(encoding="utf-8")


def test_build_mermaid_diagrams_returns_expected_keys() -> None:
    parsed = parse_codesys_xml(_load_fixture(), source_file="sample_codesys.xml")

    diagrams = build_mermaid_diagrams(parsed)

    assert set(diagrams.keys()) == {"system_flow", "logic_flow"}
    assert diagrams["system_flow"].startswith("graph TD")
    assert diagrams["logic_flow"].startswith("graph LR")


def test_diagrams_include_known_components() -> None:
    parsed = parse_codesys_xml(_load_fixture(), source_file="sample_codesys.xml")

    diagrams = build_mermaid_diagrams(parsed)

    assert "ConveyorControl" in diagrams["system_flow"]
    assert "FastTask" in diagrams["logic_flow"]
    assert "PumpManager" in diagrams["logic_flow"]
