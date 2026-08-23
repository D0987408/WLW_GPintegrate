"""Load the externally maintained diagnostic and visual-attribute references."""

from __future__ import annotations

from copy import deepcopy
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
CONTAINER_REFERENCE_ROOT = Path("/references")


def resolve_reference(configured_path: str | Path) -> Path:
    """Resolve a host path, then fall back to visible project/container locations.

    Using the basename fallbacks keeps the mapping dynamically editable at the
    lab_20 root while allowing Compose to mount the same file under /references.
    """

    configured = Path(configured_path)
    basename = configured.name
    candidates = [
        configured,
        ROOT / configured,
        ROOT.parent / basename,
        ROOT / "references" / basename,
        CONTAINER_REFERENCE_ROOT / basename,
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = ", ".join(str(candidate) for candidate in candidates)
    raise FileNotFoundError(f"Reference file {configured_path!r} was not found; searched: {searched}")


def load_reference(configured_path: str | Path) -> tuple[Any, dict[str, str]]:
    path = resolve_reference(configured_path)
    raw = path.read_bytes()
    return json.loads(raw.decode("utf-8")), {
        "source_name": path.name,
        "source_path": str(path),
        "sha256": hashlib.sha256(raw).hexdigest(),
    }


def load_dx_candidates(configured_path: str | Path) -> tuple[dict[str, Any], dict[str, str]]:
    document, provenance = load_reference(configured_path)
    return document["structured_report"], provenance


def load_histologic_mapping(
    configured_path: str | Path,
) -> tuple[dict[str, str], dict[str, str]]:
    document, provenance = load_reference(configured_path)
    return document["Histologic_Type_mappingTable"], provenance


def load_visual_references(
    candidate_path: str | Path, type_level_path: str | Path
) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, dict[str, str]]]:
    candidate_document, candidate_provenance = load_reference(candidate_path)
    type_levels_document, type_level_provenance = load_reference(type_level_path)
    candidate = candidate_document["visualAttrs"]
    type_levels = deepcopy(type_levels_document)

    for type_level in type_levels:
        # The filename is canonical for this reference revision.  The embedded
        # version was confirmed to be stale, and Polarity is canonically ordinal.
        type_level["version"] = "1.2.1"
        type_level["visualAttrs"]["Cellular_and_Nuclear"]["Polarity"]["type"] = "ordinal"
        for category, features in type_level["visualAttrs"].items():
            for feature, definition in features.items():
                reference = candidate[category][feature]
                if definition["options"] != reference["options"]:
                    raise ValueError(
                        f"Type-level options differ from candidateReference at {category}.{feature}"
                    )
                if definition["type"] != reference["type"]:
                    raise ValueError(
                        f"Type-level option type differs from candidateReference at {category}.{feature}"
                    )
                if set(definition["conditions"]) != set(definition["options"]):
                    raise ValueError(
                        f"Type-level conditions do not cover every option at {category}.{feature}"
                    )

    return candidate_document, type_levels, {
        "candidate_reference": candidate_provenance,
        "type_level_visual_attrs": type_level_provenance,
    }
