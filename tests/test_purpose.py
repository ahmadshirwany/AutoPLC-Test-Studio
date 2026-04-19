from app.parser import parse_codesys_xml
from app.purpose import detect_project_purpose


def test_purpose_detection_prefers_material_handling() -> None:
    xml_text = """
    <Project Name="Conveyor Sorting Line">
      <Program Name="ConveyorControl" />
      <Module Name="SortingStation" />
    </Project>
    """

    parsed = parse_codesys_xml(xml_text, source_file="line.xml")
    purpose = detect_project_purpose(parsed)

    assert purpose.purpose_label == "material-handling"
    assert purpose.slug == "material-handling"
    assert purpose.confidence > 0.0


def test_purpose_detection_falls_back_to_project_name() -> None:
    xml_text = """
    <Project Name="Custom Utility Project">
      <Node Name="MiscA" />
    </Project>
    """

    parsed = parse_codesys_xml(xml_text, source_file="custom.xml")
    purpose = detect_project_purpose(parsed)

    assert purpose.purpose_label == "general-automation"
    assert purpose.slug == "custom-utility-project"
