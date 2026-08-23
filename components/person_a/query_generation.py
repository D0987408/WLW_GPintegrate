from __future__ import annotations

from collections import defaultdict
from copy import deepcopy

from components.person_a.reference_data import (
    load_histologic_mapping,
    load_visual_references,
)
from contracts.metadata import dx_items, ensure_same_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


def main() -> None:
    args = cli_parser("甲: generate G visual attribute queries from F chunks").parse_args()
    inputs = load_inputs(args.input, ["D.DxPairs", "F.Chunks"])
    dx_artifact = inputs["D.DxPairs"]
    chunks_artifact = inputs["F.Chunks"]
    config = load_config(args.config)
    case_id = ensure_same_case(dx_artifact, chunks_artifact)
    payload = deepcopy(dx_artifact["payload"])

    mapping, mapping_provenance = load_histologic_mapping(
        config["histologic_mapping_path"]
    )
    candidate_document, type_levels, visual_provenance = load_visual_references(
        config["candidate_reference_path"], config["type_level_path"]
    )
    type_levels_by_result = {item["DxResult"]: item for item in type_levels}
    payload["candidateReference"] = candidate_document
    payload.setdefault("reference_versions", {}).update(visual_provenance)
    payload["reference_versions"]["histologic_type_mapping"] = mapping_provenance

    by_dx: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks_artifact["payload"]["chunks"]:
        by_dx[chunk["dx_pair_id"]].append(chunk)

    query_index = 1
    for dx_item, record in dx_items(payload).items():
        record["visualAttrQueries"] = []
        if dx_item != "Histologic_Type":
            continue
        dx_result = record["DxResultCls"]
        if not isinstance(dx_result, str):
            raise ValueError("Histologic_Type DxResultCls must be a single string")
        mapped_result = mapping.get(dx_result)
        criteria = type_levels_by_result.get(mapped_result) if mapped_result else None
        if mapped_result is not None and criteria is None:
            raise ValueError(
                f"Histologic mapping target {mapped_result!r} has no type-level criteria"
            )
        chunks = by_dx[record["dx_pair_id"]]
        evidence = " ".join(chunk["text"] for chunk in chunks)
        status = "mapped" if criteria is not None else "unmapped"
        record["visualAttrQueries"].append(
            {
                "query_id": f"{case_id}-query-{query_index:03d}",
                "dx_pair_id": record["dx_pair_id"],
                "text": evidence or f"Evaluate visual criteria for {dx_result}.",
                "criteria_status": status,
                "diagnosticCriteria": deepcopy(criteria),
                "mapping_source": (
                    f"{mapping_provenance['source_name']}#sha256="
                    f"{mapping_provenance['sha256']}"
                ),
                "chunk_ids": [chunk["chunk_id"] for chunk in chunks],
            }
        )
        query_index += 1

    artifact = {
        "contract": "G.VisualAttributeQueries",
        "schema_version": "2.0",
        "artifact_id": f"G-{case_id}",
        "case_id": case_id,
        "producer": config["component_version"],
        "payload": payload,
    }
    write_artifact(artifact, args.output, "G.VisualAttributeQueries")


if __name__ == "__main__":
    main()
