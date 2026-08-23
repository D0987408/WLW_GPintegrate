"""Wrap the cleanSections meta list as the canonical text-only A artifact."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from contracts.runtime import load_config, write_artifact


def _stable_id(prefix: str, *parts: Any) -> str:
    canonical = json.dumps(parts, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def _validate_source_entry(entry: Any, source_idx: int) -> dict[str, Any]:
    if not isinstance(entry, dict):
        raise ValueError(f"Source entry {source_idx} must be an object")
    required = {"level", "title_list", "title", "href", "sections"}
    missing = required - set(entry)
    if missing:
        raise ValueError(f"Source entry {source_idx} is missing {sorted(missing)!r}")
    level = entry["level"]
    title_list = entry["title_list"]
    if level not in {1, 2, 3}:
        raise ValueError(f"Source entry {source_idx} has unsupported level {level!r}")
    if not isinstance(title_list, list) or len(title_list) != 4:
        raise ValueError(f"Source entry {source_idx} title_list must contain four slots")
    if any(value is not None and not isinstance(value, str) for value in title_list):
        raise ValueError(f"Source entry {source_idx} title_list values must be strings or null")
    if not isinstance(entry["title"], str) or not entry["title"]:
        raise ValueError(f"Source entry {source_idx} has no title")
    if entry["href"] is not None and not isinstance(entry["href"], str):
        raise ValueError(f"Source entry {source_idx} href must be a string or null")
    if not isinstance(entry["sections"], list):
        raise ValueError(f"Source entry {source_idx} sections must be an array")
    return entry


def build_literature_artifact(
    source_path: str | Path, config: dict[str, Any]
) -> dict[str, Any]:
    path = Path(source_path).resolve()
    raw = path.read_bytes()
    source = json.loads(raw.decode("utf-8"))
    if not isinstance(source, list) or not source:
        raise ValueError("cleanSections source must be a non-empty top-level array")

    literature_list = []
    corpus_titles: set[str] = set()
    used_literature_ids: set[str] = set()
    used_section_ids: set[str] = set()
    for source_idx, raw_entry in enumerate(source):
        entry = _validate_source_entry(raw_entry, source_idx)
        if entry["title_list"][0]:
            corpus_titles.add(entry["title_list"][0])
        literature_id = _stable_id(
            "lit", entry["level"], entry["title_list"], entry["title"], entry["href"]
        )
        if literature_id in used_literature_ids:
            raise ValueError(f"Duplicate literature identity at source index {source_idx}")
        used_literature_ids.add(literature_id)

        section_title_counts: dict[str, int] = {}
        sections = []
        for section_idx, section in enumerate(entry["sections"]):
            if not isinstance(section, dict) or set(section) != {"title", "text"}:
                raise ValueError(
                    f"Source entry {source_idx} section {section_idx} must contain title/text"
                )
            if not isinstance(section["title"], str) or not section["title"]:
                raise ValueError(
                    f"Source entry {source_idx} section {section_idx} has no title"
                )
            if not isinstance(section["text"], str):
                raise ValueError(
                    f"Source entry {source_idx} section {section_idx} text must be a string"
                )
            occurrence = section_title_counts.get(section["title"], 0)
            section_title_counts[section["title"]] = occurrence + 1
            section_id = _stable_id(
                "sec", literature_id, section["title"], occurrence
            )
            if section_id in used_section_ids:
                raise ValueError(f"Duplicate section identity at {source_idx}:{section_idx}")
            used_section_ids.add(section_id)
            sections.append(
                {
                    "section_id": section_id,
                    "section_idx": section_idx,
                    "title": section["title"],
                    # Literal "None" remains unchanged for source-level comparison.
                    "text": section["text"],
                }
            )

        literature_list.append(
            {
                "literature_id": literature_id,
                "source_idx": source_idx,
                "level": entry["level"],
                "title_list": list(entry["title_list"]),
                "title": entry["title"],
                "href": entry["href"],
                "sections": sections,
            }
        )

    if len(corpus_titles) != 1:
        raise ValueError(f"Expected one corpus title, found {sorted(corpus_titles)!r}")
    title = next(iter(corpus_titles))
    return {
        "contract": "A.Literature",
        "schema_version": "2.0",
        "artifact_id": f"A-{config['corpus_id']}",
        "producer": config["component_version"],
        "payload": {
            "corpus": {
                "corpus_id": config["corpus_id"],
                "title": title,
                "source_file": path.name,
                "source_path": str(path),
                "sha256": hashlib.sha256(raw).hexdigest(),
                "source_size_bytes": len(raw),
                "literature_count": len(literature_list),
            },
            "literature_list": literature_list,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="乙: prepare a text-only A.Literature artifact from cleanSections"
    )
    parser.add_argument("--source", required=True, help="cleanSections meta-list JSON")
    parser.add_argument("--output", required=True, help="Output A.Literature artifact")
    parser.add_argument("--config", required=True, help="Preparation config JSON")
    args = parser.parse_args()
    config = load_config(args.config)
    artifact = build_literature_artifact(args.source, config)
    write_artifact(artifact, args.output, "A.Literature")
    section_count = sum(
        len(item["sections"]) for item in artifact["payload"]["literature_list"]
    )
    print(
        f"Literature preparation preserved "
        f"{artifact['payload']['corpus']['literature_count']} nodes and {section_count} sections"
    )


if __name__ == "__main__":
    main()
