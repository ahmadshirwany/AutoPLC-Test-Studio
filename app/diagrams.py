from __future__ import annotations

import hashlib
import re

from .models import ParsedNode, ParsedProject


MAX_SYSTEM_DIAGRAM_NODES = 120
MAX_TASKS_IN_LOGIC_DIAGRAM = 16
MAX_LOGIC_NODES_PER_TASK = 24
MAX_MODULE_NODES = 20

NODE_TYPE_RANK = {
    "resource": 0,
    "task": 1,
    "program": 2,
    "function_block": 3,
    "logic_block": 4,
    "module": 5,
}


def _escape_label(value: str) -> str:
    sanitized = value.replace('"', "'").strip()
    return sanitized or "Unnamed"


def _id_for_path(prefix: str, path: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "_", path).strip("_").lower()
    slug = slug or "node"
    # Keep IDs readable but collision-safe even for deeply nested long paths.
    suffix = hashlib.sha1(path.encode("utf-8")).hexdigest()[:10]
    return f"{prefix}_{slug[:36]}_{suffix}"


def _with_type_suffix(label: str, node_type: str) -> str:
    if node_type in {"group", "project"}:
        return _escape_label(label)
    return f"{_escape_label(label)}\\n({node_type})"


def _class_for_type(node_type: str) -> str:
    if node_type in {
        "project",
        "group",
        "resource",
        "task",
        "program",
        "function_block",
        "logic_block",
        "module",
    }:
        return node_type
    return "group"


def _sorted_typed_nodes(nodes: list[ParsedNode]) -> list[ParsedNode]:
    return sorted(
        nodes,
        key=lambda node: (
            node.path.count("/"),
            NODE_TYPE_RANK.get(node.node_type, 9),
            node.name.lower(),
            node.path.lower(),
        ),
    )


def _select_system_nodes(project: ParsedProject) -> tuple[list[ParsedNode], int]:
    typed_nodes = _sorted_typed_nodes(project.nodes)
    if len(typed_nodes) <= MAX_SYSTEM_DIAGRAM_NODES:
        return typed_nodes, 0
    selected = typed_nodes[:MAX_SYSTEM_DIAGRAM_NODES]
    omitted = len(typed_nodes) - len(selected)
    return selected, omitted


def _nearest_parent_path(node: ParsedNode, selected_paths: set[str]) -> str | None:
    parts = [segment for segment in node.path.split("/") if segment]
    for index in range(len(parts) - 1, 0, -1):
        candidate = "/".join(parts[:index])
        if candidate in selected_paths:
            return candidate
    return None


def build_system_flow_diagram(project: ParsedProject) -> str:
    if not project.nodes:
        return "graph TD\n  A[\"No tracked nodes\"]"

    selected_nodes, omitted_count = _select_system_nodes(project)
    if not selected_nodes:
        return "graph TD\n  A[\"No typed control nodes found\"]"

    selected_paths = {node.path for node in selected_nodes}
    root_key = f"{project.project_name}::root"
    id_map = {root_key: _id_for_path("sys", root_key)}

    for node in selected_nodes:
        id_map[node.path] = _id_for_path("sys", node.path)

    edges: set[tuple[str, str]] = set()

    lines = ["graph TD"]
    lines.append(f"  {id_map[root_key]}[\"{_with_type_suffix(project.project_name, 'project')}\"]")

    for node in selected_nodes:
        lines.append(
            f"  {id_map[node.path]}[\"{_with_type_suffix(node.name, node.node_type)}\"]"
        )

    for node in selected_nodes:
        parent_path = _nearest_parent_path(node, selected_paths)
        parent_key = parent_path if parent_path else root_key
        edges.add((parent_key, node.path))

    if omitted_count:
        omitted_key = f"{project.project_name}::omitted"
        id_map[omitted_key] = _id_for_path("sys", omitted_key)
        lines.append(
            f"  {id_map[omitted_key]}[\"{omitted_count} additional nodes omitted\"]"
        )
        edges.add((root_key, omitted_key))

    for parent_key, child_key in sorted(edges, key=lambda edge: (edge[0], edge[1])):
        if parent_key in id_map and child_key in id_map:
            lines.append(f"  {id_map[parent_key]} --> {id_map[child_key]}")

    lines.extend(
        [
            "",
            "  classDef project fill:#0f766e,color:#ffffff,stroke:#134e4a,stroke-width:1px;",
            "  classDef group fill:#f8fafc,color:#111827,stroke:#94a3b8,stroke-width:1px;",
            "  classDef resource fill:#1d4ed8,color:#ffffff,stroke:#1e3a8a,stroke-width:1px;",
            "  classDef task fill:#7c3aed,color:#ffffff,stroke:#5b21b6,stroke-width:1px;",
            "  classDef program fill:#0284c7,color:#ffffff,stroke:#075985,stroke-width:1px;",
            "  classDef function_block fill:#be185d,color:#ffffff,stroke:#831843,stroke-width:1px;",
            "  classDef logic_block fill:#b45309,color:#ffffff,stroke:#78350f,stroke-width:1px;",
            "  classDef module fill:#0369a1,color:#ffffff,stroke:#0c4a6e,stroke-width:1px;",
        ]
    )

    lines.append(f"  class {id_map[root_key]} project;")

    for node in selected_nodes:
        lines.append(f"  class {id_map[node.path]} {_class_for_type(node.node_type)};")

    if omitted_count:
        omitted_key = f"{project.project_name}::omitted"
        lines.append(f"  class {id_map[omitted_key]} group;")

    return "\n".join(lines)


def _logic_candidates_for_task(task: ParsedNode, nodes: list[ParsedNode]) -> list[ParsedNode]:
    task_prefix = task.path + "/"
    candidates = [
        node
        for node in nodes
        if node.path.startswith(task_prefix)
        and node.path != task.path
        and node.node_type in {"program", "function_block", "logic_block"}
    ]

    rank = {"program": 0, "function_block": 1, "logic_block": 2}
    return sorted(candidates, key=lambda item: (rank.get(item.node_type, 9), item.name.lower()))


def build_logic_flow_diagram(project: ParsedProject) -> str:
    tasks = sorted(
        [node for node in project.nodes if node.node_type == "task"],
        key=lambda item: item.path,
    )[:MAX_TASKS_IN_LOGIC_DIAGRAM]

    if not tasks:
        return "graph LR\n  A[\"No task-level logic detected\"]"

    lines = ["graph LR"]
    declared_ids: set[str] = set()
    task_ids: dict[str, str] = {}
    logic_ids: dict[str, str] = {}

    for task in tasks:
        task_id = _id_for_path("logic", task.path)
        task_ids[task.path] = task_id
        if task_id not in declared_ids:
            lines.append(f"  {task_id}[\"{_with_type_suffix(task.name, task.node_type)}\"]")
            declared_ids.add(task_id)

        candidates = _logic_candidates_for_task(task, project.nodes)
        omitted_for_task = 0
        if len(candidates) > MAX_LOGIC_NODES_PER_TASK:
            omitted_for_task = len(candidates) - MAX_LOGIC_NODES_PER_TASK
            candidates = candidates[:MAX_LOGIC_NODES_PER_TASK]

        previous_id = ""

        for candidate in candidates:
            candidate_id = _id_for_path("logic", candidate.path)
            logic_ids[candidate.path] = candidate_id
            if candidate_id not in declared_ids:
                lines.append(
                    f"  {candidate_id}[\"{_with_type_suffix(candidate.name, candidate.node_type)}\"]"
                )
                declared_ids.add(candidate_id)

            lines.append(f"  {task_id} --> {candidate_id}")
            if previous_id and previous_id != candidate_id:
                lines.append(f"  {previous_id} -. inferred order .-> {candidate_id}")
            previous_id = candidate_id

        if omitted_for_task:
            omitted_id = _id_for_path("logic", f"{task.path}::omitted")
            lines.append(f"  {omitted_id}[\"{omitted_for_task} additional logic nodes omitted\"]")
            lines.append(f"  {task_id} -. additional scope .-> {omitted_id}")
            declared_ids.add(omitted_id)

    # Connect independent modules to the nearest task as monitoring elements.
    modules = [node for node in project.nodes if node.node_type == "module"][:MAX_MODULE_NODES]
    for module in modules:
        module_id = _id_for_path("logic", module.path)
        if module_id not in declared_ids:
            lines.append(f"  {module_id}[\"{_with_type_suffix(module.name, module.node_type)}\"]")
            declared_ids.add(module_id)

        closest_task = next((task for task in tasks if module.path.startswith(task.path.rsplit("/", 1)[0])), tasks[0])
        lines.append(
            f"  {task_ids[closest_task.path]} -. alarm and status .-> {module_id}"
        )

    lines.extend(
        [
            "",
            "  classDef task fill:#7c3aed,color:#ffffff,stroke:#5b21b6,stroke-width:1px;",
            "  classDef program fill:#0284c7,color:#ffffff,stroke:#075985,stroke-width:1px;",
            "  classDef function_block fill:#be185d,color:#ffffff,stroke:#831843,stroke-width:1px;",
            "  classDef logic_block fill:#b45309,color:#ffffff,stroke:#78350f,stroke-width:1px;",
            "  classDef module fill:#0369a1,color:#ffffff,stroke:#0c4a6e,stroke-width:1px;",
        ]
    )

    for task in tasks:
        lines.append(f"  class {task_ids[task.path]} task;")

    for node in project.nodes:
        node_id = logic_ids.get(node.path) or _id_for_path("logic", node.path)
        if node_id in declared_ids and node.node_type in {
            "program",
            "function_block",
            "logic_block",
            "module",
        }:
            lines.append(f"  class {node_id} {_class_for_type(node.node_type)};")

    if len([node for node in project.nodes if node.node_type == "task"]) > len(tasks):
        hidden_tasks = len([node for node in project.nodes if node.node_type == "task"]) - len(tasks)
        summary_id = _id_for_path("logic", f"{project.project_name}::hidden_tasks")
        lines.append(f"  {summary_id}[\"{hidden_tasks} additional tasks omitted\"]")
        lines.append(f"  class {summary_id} group;")

    return "\n".join(lines)


def build_mermaid_diagrams(project: ParsedProject) -> dict[str, str]:
    return {
        "system_flow": build_system_flow_diagram(project),
        "logic_flow": build_logic_flow_diagram(project),
    }
