from dataclasses import dataclass, field


@dataclass
class ParsedNode:
    name: str
    node_type: str
    tag: str
    path: str
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass
class ParsedProject:
    source_file: str
    project_name: str
    root_tag: str
    namespaces: list[str] = field(default_factory=list)
    nodes: list[ParsedNode] = field(default_factory=list)
    tag_frequencies: dict[str, int] = field(default_factory=dict)
    stats: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class DetailLevelConfig:
    key: str
    overview_max_nodes: int
    detailed_max_nodes: int
    min_words_overview: int
    min_words_detailed: int


DETAIL_LEVELS: dict[str, DetailLevelConfig] = {
    "basic": DetailLevelConfig(
        key="basic",
        overview_max_nodes=120,
        detailed_max_nodes=220,
        min_words_overview=400,
        min_words_detailed=700,
    ),
    "standard": DetailLevelConfig(
        key="standard",
        overview_max_nodes=220,
        detailed_max_nodes=380,
        min_words_overview=700,
        min_words_detailed=1300,
    ),
    "deep": DetailLevelConfig(
        key="deep",
        overview_max_nodes=360,
        detailed_max_nodes=640,
        min_words_overview=1200,
        min_words_detailed=2400,
    ),
    "comprehensive": DetailLevelConfig(
        key="comprehensive",
        overview_max_nodes=520,
        detailed_max_nodes=900,
        min_words_overview=1800,
        min_words_detailed=3500,
    ),
}


@dataclass
class PurposeResult:
    purpose_label: str
    slug: str
    confidence: float
    signals: list[str] = field(default_factory=list)


@dataclass
class GeneratedDocs:
    system_overview_md: str
    detailed_code_md: str
    detail_level: str = "deep"
    diagrams: dict[str, str] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


@dataclass
class Artifact:
    kind: str
    format: str
    file_name: str
    relative_path: str
    download_url: str
