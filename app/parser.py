from __future__ import annotations

from collections import Counter
from pathlib import Path
import io
import xml.etree.ElementTree as ET

from .models import ParsedNode, ParsedProject


NAME_ATTRIBUTES = (
    "Name",
    "name",
    "ObjectName",
    "objectName",
    "PouName",
    "pouName",
    "Id",
    "ID",
)


def _strip_namespace(tag: str) -> str:
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def _extract_name(element: ET.Element) -> str | None:
    for key in NAME_ATTRIBUTES:
        value = element.attrib.get(key)
        if value and value.strip():
            return value.strip()

    text = (element.text or "").strip()
    if text and len(text) <= 64:
        return text

    return None


def _classify_node(tag_lower: str) -> str | None:
    normalized = tag_lower.replace("_", "").replace("-", "")

    if "program" in normalized or normalized == "pou":
        return "program"
    if "functionblock" in normalized or normalized == "fb":
        return "function_block"
    if "method" in normalized or "action" in normalized or "transition" in normalized:
        return "logic_block"
    if "task" in normalized:
        return "task"
    if "module" in normalized or "component" in normalized:
        return "module"
    if "device" in normalized or "resource" in normalized:
        return "resource"

    return None


def _extract_namespaces(xml_text: str) -> list[str]:
    namespaces: set[str] = set()
    try:
        for _, item in ET.iterparse(io.StringIO(xml_text), events=("start-ns",)):
            _, uri = item
            if uri:
                namespaces.add(uri)
    except ET.ParseError:
        return []

    return sorted(namespaces)


def _guess_project_name(root: ET.Element, source_file: str) -> str:
    root_name = _extract_name(root)
    if root_name:
        return root_name

    for element in root.iter():
        tag_lower = _strip_namespace(element.tag).lower()
        if "project" in tag_lower:
            value = _extract_name(element)
            if value:
                return value

    return Path(source_file).stem or "codesys-project"


def _walk_tree(
    element: ET.Element,
    lineage: list[str],
    nodes: list[ParsedNode],
    tag_counter: Counter[str],
) -> None:
    tag = _strip_namespace(element.tag)
    tag_lower = tag.lower()
    tag_counter[tag_lower] += 1

    element_name = _extract_name(element)
    current_label = element_name or tag
    current_path = "/".join(lineage + [current_label])

    node_type = _classify_node(tag_lower)
    if node_type:
        attributes = {str(k): str(v)[:160] for k, v in element.attrib.items() if str(v).strip()}
        nodes.append(
            ParsedNode(
                name=current_label,
                node_type=node_type,
                tag=tag,
                path=current_path,
                attributes=attributes,
            )
        )

    for child in list(element):
        _walk_tree(child, lineage + [current_label], nodes, tag_counter)


def parse_codesys_xml(xml_text: str, source_file: str) -> ParsedProject:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise ValueError(f"Invalid XML file: {exc}") from exc

    nodes: list[ParsedNode] = []
    tag_counter: Counter[str] = Counter()
    project_name = _guess_project_name(root, source_file)
    root_tag = _strip_namespace(root.tag)

    _walk_tree(root, [project_name], nodes, tag_counter)

    node_type_counter = Counter(node.node_type for node in nodes)
    stats = {
        "total_xml_nodes": sum(tag_counter.values()),
        "tracked_nodes": len(nodes),
    }
    for node_type, count in node_type_counter.items():
        stats[f"type_{node_type}"] = count

    return ParsedProject(
        source_file=source_file,
        project_name=project_name,
        root_tag=root_tag,
        namespaces=_extract_namespaces(xml_text),
        nodes=nodes,
        tag_frequencies=dict(tag_counter.most_common(30)),
        stats=stats,
    )
