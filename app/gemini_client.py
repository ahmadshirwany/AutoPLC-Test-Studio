from __future__ import annotations

from collections import defaultdict
import requests

from .config import Settings
from .models import GeneratedDocs, ParsedProject
from .prompts import (
    build_detailed_code_prompt,
    build_system_overview_prompt,
    detailed_required_sections,
    normalize_detail_level,
    system_required_sections,
)


class GeminiDocumentationService:
    MAX_OUTPUT_TOKENS_BY_LEVEL = {
        "basic": 3072,
        "standard": 5120,
        "deep": 8192,
        "comprehensive": 10240,
    }
    MAX_CONTINUATION_ATTEMPTS_BY_LEVEL = {
        "basic": 1,
        "standard": 2,
        "deep": 3,
        "comprehensive": 4,
    }
    REQUEST_TIMEOUT_BY_LEVEL = {
        "basic": 45,
        "standard": 60,
        "deep": 90,
        "comprehensive": 120,
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def generate_documents(self, project: ParsedProject, detail_level: str = "deep") -> GeneratedDocs:
        normalized_level = normalize_detail_level(detail_level)
        warnings: list[str] = []

        if not self.settings.gemini_api_key:
            warnings.append("GEMINI_API_KEY is not configured. Returning deterministic fallback documentation.")
            fallback = self._fallback_documents(project, warnings)
            fallback.detail_level = normalized_level
            return fallback

        system_text = self._generate_text(
            prompt=build_system_overview_prompt(project, detail_level=normalized_level),
            warnings=warnings,
            doc_name="system overview",
            required_sections=system_required_sections(normalized_level),
            detail_level=normalized_level,
        )
        detailed_text = self._generate_text(
            prompt=build_detailed_code_prompt(project, detail_level=normalized_level),
            warnings=warnings,
            doc_name="detailed code documentation",
            required_sections=detailed_required_sections(normalized_level),
            detail_level=normalized_level,
        )

        if not system_text or not detailed_text:
            fallback = self._fallback_documents(project, [])
            if not system_text:
                system_text = fallback.system_overview_md
            if not detailed_text:
                detailed_text = fallback.detailed_code_md
            warnings.append("Incomplete Gemini response. Missing sections were replaced with fallback templates.")

        return GeneratedDocs(
            system_overview_md=system_text,
            detailed_code_md=detailed_text,
            detail_level=normalized_level,
            warnings=warnings,
        )

    def _generate_text(
        self,
        prompt: str,
        warnings: list[str],
        doc_name: str,
        required_sections: tuple[str, ...],
        detail_level: str,
    ) -> str:
        text, finish_reason = self._call_gemini(
            prompt,
            warnings,
            max_output_tokens=self.MAX_OUTPUT_TOKENS_BY_LEVEL[detail_level],
            timeout_seconds=self._timeout_for_level(detail_level),
        )
        if not text:
            return ""

        text = self._extend_if_truncated(
            prompt,
            text,
            finish_reason,
            warnings,
            doc_name,
            detail_level,
        )

        missing_sections = self._missing_sections(text, required_sections)
        if missing_sections:
            retry_prompt = self._build_retry_prompt(prompt, text, required_sections, doc_name)
            retry_text, retry_finish_reason = self._call_gemini(
                retry_prompt,
                warnings,
                max_output_tokens=self.MAX_OUTPUT_TOKENS_BY_LEVEL[detail_level],
                timeout_seconds=self._timeout_for_level(detail_level),
            )
            if retry_text:
                retry_text = self._extend_if_truncated(
                    retry_prompt,
                    retry_text,
                    retry_finish_reason,
                    warnings,
                    doc_name,
                    detail_level,
                )
                if self._section_coverage_score(retry_text, required_sections) >= self._section_coverage_score(text, required_sections):
                    text = retry_text

        final_missing = self._missing_sections(text, required_sections)
        if final_missing:
            warnings.append(
                f"Gemini output for {doc_name} is missing expected sections: {', '.join(final_missing)}"
            )

        return text

    def _timeout_for_level(self, detail_level: str) -> int:
        configured = self.REQUEST_TIMEOUT_BY_LEVEL.get(detail_level, 60)
        return max(self.settings.gemini_timeout_seconds, configured)

    def _call_gemini(
        self,
        prompt: str,
        warnings: list[str],
        max_output_tokens: int,
        timeout_seconds: int,
        warn_on_empty_response: bool = True,
    ) -> tuple[str, str]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"
        payload = {
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.2,
                "maxOutputTokens": max_output_tokens,
            },
        }

        last_exception: requests.RequestException | None = None
        for attempt in range(2):
            try:
                response = requests.post(
                    url,
                    params={"key": self.settings.gemini_api_key},
                    json=payload,
                    timeout=timeout_seconds,
                )
                response.raise_for_status()
                break
            except requests.Timeout as exc:
                last_exception = exc
                if attempt == 0:
                    continue
                warnings.append(
                    f"Gemini request timed out after retry (timeout={timeout_seconds}s)."
                )
                return "", ""
            except requests.RequestException as exc:
                last_exception = exc
                warnings.append(f"Gemini request failed: {exc}")
                return "", ""
        else:
            if last_exception is not None:
                warnings.append(f"Gemini request failed: {last_exception}")
            return "", ""

        data = response.json()
        candidates = data.get("candidates", [])
        if not candidates:
            if warn_on_empty_response:
                warnings.append("Gemini returned no candidates.")
            return "", ""

        first_candidate = candidates[0]
        parts = first_candidate.get("content", {}).get("parts", [])
        finish_reason = str(first_candidate.get("finishReason", ""))
        text = "".join(part.get("text", "") for part in parts if isinstance(part, dict)).strip()
        if not text:
            if warn_on_empty_response:
                warnings.append("Gemini returned an empty response.")
            return "", finish_reason

        return text, finish_reason

    def _extend_if_truncated(
        self,
        base_prompt: str,
        current_text: str,
        finish_reason: str,
        warnings: list[str],
        doc_name: str,
        detail_level: str,
    ) -> str:
        if finish_reason != "MAX_TOKENS":
            return current_text

        combined = current_text
        latest_finish_reason = finish_reason
        max_attempts = self.MAX_CONTINUATION_ATTEMPTS_BY_LEVEL[detail_level]

        for _ in range(max_attempts):
            continuation_prompt = self._build_continuation_prompt(base_prompt, combined, doc_name)
            continuation_text, latest_finish_reason = self._call_gemini(
                continuation_prompt,
                warnings,
                max_output_tokens=self.MAX_OUTPUT_TOKENS_BY_LEVEL[detail_level],
                timeout_seconds=self._timeout_for_level(detail_level),
                warn_on_empty_response=False,
            )
            if not continuation_text:
                break

            combined = self._append_without_overlap(combined, continuation_text)
            if latest_finish_reason != "MAX_TOKENS":
                break

        if latest_finish_reason == "MAX_TOKENS":
            warnings.append(
                f"Gemini output for {doc_name} is still truncated after continuation attempts."
            )

        return combined

    @staticmethod
    def _append_without_overlap(existing_text: str, continuation_text: str) -> str:
        if not existing_text:
            return continuation_text

        max_overlap = min(len(existing_text), len(continuation_text), 600)
        for overlap in range(max_overlap, 19, -1):
            if existing_text.endswith(continuation_text[:overlap]):
                return existing_text + continuation_text[overlap:]

        return existing_text.rstrip() + "\n" + continuation_text.lstrip()

    @staticmethod
    def _build_continuation_prompt(base_prompt: str, generated_text: str, doc_name: str) -> str:
        tail = generated_text[-3000:]
        return (
            f"{base_prompt}\n\n"
            f"The previous {doc_name} response was truncated. Continue from exactly where it stopped.\n"
            "Rules:\n"
            "1. Do not restart from the beginning.\n"
            "2. Do not repeat headings or paragraphs already written.\n"
            "3. Return only the continuation in Markdown.\n\n"
            "Generated so far:\n"
            "```markdown\n"
            f"{tail}\n"
            "```"
        )

    @staticmethod
    def _build_retry_prompt(
        base_prompt: str,
        previous_text: str,
        required_sections: tuple[str, ...],
        doc_name: str,
    ) -> str:
        sections = "\n".join(f"- {section}" for section in required_sections)
        excerpt = previous_text[:1800]
        return (
            f"{base_prompt}\n\n"
            f"The previous {doc_name} output was incomplete. Regenerate the full document from scratch.\n"
            "You must include all required section headings exactly once:\n"
            f"{sections}\n\n"
            "Previous incomplete output excerpt (for context):\n"
            "```markdown\n"
            f"{excerpt}\n"
            "```"
        )

    @staticmethod
    def _missing_sections(text: str, required_sections: tuple[str, ...]) -> list[str]:
        lowered = text.lower()
        return [section for section in required_sections if section.lower() not in lowered]

    def _section_coverage_score(self, text: str, required_sections: tuple[str, ...]) -> int:
        return len(required_sections) - len(self._missing_sections(text, required_sections))

    def _fallback_documents(self, project: ParsedProject, warnings: list[str]) -> GeneratedDocs:
        grouped_nodes: dict[str, list[str]] = defaultdict(list)
        for node in project.nodes:
            grouped_nodes[node.node_type].append(node.name)

        system_lines = [
            "# System Overview",
            "",
            "## Project Purpose",
            f"Auto-generated baseline overview for **{project.project_name}**.",
            "",
            "## Architecture Summary",
            f"Root tag: `{project.root_tag}`.",
            f"Tracked structural nodes: **{project.stats.get('tracked_nodes', 0)}**.",
            "",
            "## Workflow and Control Logic",
            "The XML was parsed into modules, programs, tasks, and logic blocks where available.",
            "",
            "## Key Components",
        ]
        for node_type, names in sorted(grouped_nodes.items()):
            preview = ", ".join(sorted(set(names))[:10]) or "None"
            system_lines.append(f"- **{node_type}**: {preview}")

        system_lines.extend(
            [
                "",
                "## Operational Risks and Notes",
                "- Review generated documentation against source project before release.",
                "- If Gemini is unavailable, this report is template-based and may be less descriptive.",
            ]
        )

        detail_lines = [
            "# Detailed Code Documentation",
            "",
            "## Module and Component Inventory",
        ]
        for node_type, names in sorted(grouped_nodes.items()):
            detail_lines.append(f"### {node_type.title().replace('_', ' ')}")
            for name in sorted(set(names))[:40]:
                detail_lines.append(f"- {name}")
            detail_lines.append("")

        detail_lines.extend(
            [
                "## Logic Blocks and Responsibilities",
                "The following elements were recognized from XML tags and attributes:",
            ]
        )
        for node in project.nodes[:120]:
            detail_lines.append(
                f"- **{node.name}** (`{node.node_type}`) at `{node.path}`"
            )

        detail_lines.extend(
            [
                "",
                "## Task-Level Observations",
                f"Detected task nodes: **{project.stats.get('type_task', 0)}**.",
                "",
                "## Integration and Dependency Notes",
                "- Validate signal mapping and external I/O definitions in the original CODESYS project.",
                "",
                "## Maintenance Recommendations",
                "- Keep this document aligned with each project export version.",
                "- Add domain-specific review notes for commissioning and troubleshooting teams.",
            ]
        )

        return GeneratedDocs(
            system_overview_md="\n".join(system_lines),
            detailed_code_md="\n".join(detail_lines),
            detail_level="standard",
            warnings=warnings,
        )
