from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from typing import Any

from contracts.metadata import dx_items, ensure_same_case, iter_rois, single_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


def main() -> None:
    args = cli_parser("戊: append final CLEE decisions to the metadata-shaped ROI list").parse_args()
    inputs = load_inputs(args.input, ["D.DxPairs", "H.MatchedROIs"])
    d_artifact = inputs["D.DxPairs"]
    h_artifact = inputs["H.MatchedROIs"]
    config = load_config(args.config)
    case_id = ensure_same_case(d_artifact, h_artifact)
    single_case(d_artifact)
    single_case(h_artifact)
    payload = deepcopy(h_artifact["payload"])

    roi_entries = list(iter_rois(payload))
    candidates: dict[str, list[tuple[float, str, str]]] = defaultdict(list)
    for _, roi in roi_entries:
        for event in roi["selection_history"]:
            if (
                event["stage"] == "visual_attributes_matching_filter"
                and event["selected"]
                and event.get("score", 0) >= config["minimum_selection_score"]
            ):
                candidates[event["dx_pair_id"]].append(
                    (event["score"], roi["roi_id"], event["query_id"])
                )

    winners: dict[tuple[str, str], tuple[int, float, str]] = {}
    for dx_pair_id, items in candidates.items():
        items.sort(key=lambda item: (-item[0], item[1]))
        for rank, (score, roi_id, query_id) in enumerate(
            items[: config["top_k_per_dx"]], start=1
        ):
            winners[(dx_pair_id, roi_id)] = (rank, score, query_id)

    query_contexts = [
        (record, query)
        for record in dx_items(payload).values()
        for query in record.get("visualAttrQueries", [])
    ]
    if not query_contexts:
        for _, roi in roi_entries:
            roi["selection_history"].append(
                {
                    "stage": "clee",
                    "owner": "person_E",
                    "artifact_contract": "I.CLEESelectedROIs",
                    "selected": False,
                    "producer": config["component_version"],
                }
            )

    for record, query in query_contexts:
        for _, roi in roi_entries:
            winner = winners.get((record["dx_pair_id"], roi["roi_id"]))
            event: dict[str, Any] = {
                "stage": "clee",
                "owner": "person_E",
                "artifact_contract": "I.CLEESelectedROIs",
                "selected": winner is not None,
                "producer": config["component_version"],
                "query_id": query["query_id"],
                "dx_pair_id": record["dx_pair_id"],
                "criteria_status": query["criteria_status"],
            }
            if winner is not None:
                rank, score, _ = winner
                event.update({"rank": rank, "score": score})
            roi["selection_history"].append(event)

    artifact = {
        "contract": "I.CLEESelectedROIs",
        "schema_version": "2.0",
        "artifact_id": f"I-{case_id}",
        "case_id": case_id,
        "producer": config["component_version"],
        "payload": payload,
    }
    write_artifact(artifact, args.output, "I.CLEESelectedROIs")


if __name__ == "__main__":
    main()
