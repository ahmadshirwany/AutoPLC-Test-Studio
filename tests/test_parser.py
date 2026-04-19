from pathlib import Path

from app.parser import parse_codesys_xml


def test_parse_extracts_project_and_nodes() -> None:
    fixture_path = Path(__file__).parent / "fixtures" / "sample_codesys.xml"
    xml_text = fixture_path.read_text(encoding="utf-8")

    parsed = parse_codesys_xml(xml_text, source_file="sample_codesys.xml")

    assert parsed.project_name == "Bottle Filling Line"
    assert parsed.root_tag == "Project"
    assert parsed.stats["tracked_nodes"] >= 4
    assert any(node.node_type == "program" for node in parsed.nodes)


def test_invalid_xml_raises_value_error() -> None:
    invalid_xml = "<Project><Program></Project>"
    try:
        parse_codesys_xml(invalid_xml, source_file="broken.xml")
    except ValueError as exc:
        assert "Invalid XML file" in str(exc)
    else:
        raise AssertionError("Expected ValueError for malformed XML")
