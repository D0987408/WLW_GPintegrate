"""Helpers for the shared, metadata-shaped D/E/G/H/I payload."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any


def single_case(artifact: dict[str, Any]) -> dict[str, Any]:
    """Return the sole case and verify the envelope/case linkage."""

    cases = artifact["payload"]["case_list"]
    if len(cases) != 1:
        raise ValueError(f"{artifact['contract']} must contain exactly one case")
    case = cases[0]
    if case["case_id"] != artifact["case_id"]:
        raise ValueError(
            f"{artifact['contract']} envelope case_id does not match payload case_id"
        )
    return case


def ensure_same_case(*artifacts: dict[str, Any]) -> str:
    case_ids = {artifact["case_id"] for artifact in artifacts}
    if len(case_ids) != 1:
        raise ValueError(
            "Input artifacts do not describe the same case: " + ", ".join(sorted(case_ids))
        )
    for artifact in artifacts:
        if "case_list" in artifact.get("payload", {}):
            single_case(artifact)
    return next(iter(case_ids))


def iter_stains(payload: dict[str, Any]) -> Iterator[dict[str, Any]]:
    for case in payload["case_list"]:
        for block in case["tissue_blocks"]:
            yield from block["stains"]


def iter_rois(payload: dict[str, Any]) -> Iterator[tuple[dict[str, Any], dict[str, Any]]]:
    for stain in iter_stains(payload):
        for roi in stain["roi_list"]:
            yield stain, roi


def dx_items(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return payload["case_list"][0]["structured_report"]["DxItems"]
