from __future__ import annotations

from copy import deepcopy
from typing import Any

from contracts.metadata import dx_items, ensure_same_case, iter_rois, single_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


def _default_visual_attrs(candidate: dict[str, Any]) -> dict[str, Any]:
    return {
        category: {
            feature: list(definition.get("normal") or ["Unable to confirm"])
            for feature, definition in features.items()
        }
        for category, features in candidate.items()
    }


def _mock_visual_attrs(
    candidate: dict[str, Any], criteria: dict[str, Any], conforming: bool
) -> dict[str, Any]:
    """Deterministic stand-in for the future visual-attribute model."""

    observed = _default_visual_attrs(candidate)
    for category, features in criteria["visualAttrs"].items():
        for feature, definition in features.items():
            conditions = definition["conditions"]
            must_true = [value for value, state in conditions.items() if state == "Must_True"]
            must_false = [value for value, state in conditions.items() if state == "Must_False"]
            high = [
                value for value, state in conditions.items() if state == "High_Possibly_True"
            ]
            low = [
                value for value, state in conditions.items() if state == "Low_Possibly_True"
            ]
            if conforming:
                values = must_true or high[:1] or low[:1]
                if not values:
                    values = [
                        value
                        for value in definition["options"]
                        if value not in must_false and value != "Unable to confirm"
                    ][:1]
            else:
                values = must_false[:1]
                if not values and must_true:
                    values = [
                        value
                        for value in definition["options"]
                        if value not in must_true and value != "Unable to confirm"
                    ][:1]
            observed[category][feature] = values or ["Unable to confirm"]
    return observed


def _evaluate(
    observed: dict[str, Any], criteria: dict[str, Any]
) -> tuple[float, bool, bool, list[str], list[str]]:
    required_true: list[tuple[str, str, str]] = []
    forbidden: list[tuple[str, str, str]] = []
    likely_by_feature: dict[tuple[str, str], set[str]] = {}
    for category, features in criteria["visualAttrs"].items():
        for feature, definition in features.items():
            for value, state in definition["conditions"].items():
                item = (category, feature, value)
                if state == "Must_True":
                    required_true.append(item)
                elif state == "Must_False":
                    forbidden.append(item)
                elif state in {"High_Possibly_True", "Low_Possibly_True"}:
                    likely_by_feature.setdefault((category, feature), set()).add(value)

    present = {
        (category, feature, value)
        for category, features in observed.items()
        for feature, values in features.items()
        for value in values
    }
    must_true_passed = all(item in present for item in required_true)
    must_false_passed = not any(item in present for item in forbidden)
    failed = [
        f"missing:{category}.{feature}={value}"
        for category, feature, value in required_true
        if (category, feature, value) not in present
    ]
    failed.extend(
        f"forbidden:{category}.{feature}={value}"
        for category, feature, value in forbidden
        if (category, feature, value) in present
    )
    matched = [
        f"{category}.{feature}={value}"
        for (category, feature), candidates in likely_by_feature.items()
        for value in observed[category][feature]
        if value in candidates
    ]
    likely_ratio = (
        len({item.rsplit("=", 1)[0] for item in matched}) / len(likely_by_feature)
        if likely_by_feature
        else 1.0
    )
    legal = must_true_passed and must_false_passed
    score = (0.6 if legal else 0.0) + 0.4 * likely_ratio
    return (
        round(score, 3),
        must_true_passed,
        must_false_passed,
        sorted(matched),
        sorted(failed),
    )


def _visual_attrs_info(observed: dict[str, Any]) -> dict[str, Any]:
    values = [values for features in observed.values() for values in features.values()]
    unable = sum("Unable to confirm" in feature_values for feature_values in values)
    return {
        "allnull": unable == len(values),
        "nullPercentage": round(unable / len(values), 6) if values else 1.0,
    }


def main() -> None:
    args = cli_parser("丁: extract E ROI visual attributes and match G criteria").parse_args()
    inputs = load_inputs(args.input, ["E.ROIs", "G.VisualAttributeQueries"])
    e_artifact = inputs["E.ROIs"]
    g_artifact = inputs["G.VisualAttributeQueries"]
    config = load_config(args.config)
    case_id = ensure_same_case(e_artifact, g_artifact)
    single_case(e_artifact)
    g_case = single_case(g_artifact)

    payload = deepcopy(e_artifact["payload"])
    payload["candidateReference"] = deepcopy(g_artifact["payload"]["candidateReference"])
    payload["reference_versions"] = deepcopy(g_artifact["payload"]["reference_versions"])
    payload["case_list"][0]["structured_report"] = deepcopy(g_case["structured_report"])
    candidate = payload["candidateReference"]["visualAttrs"]
    queries = [
        (record, query)
        for record in dx_items(payload).values()
        for query in record.get("visualAttrQueries", [])
    ]

    roi_entries = list(iter_rois(payload))
    relevant_criteria = next(
        (
            query["diagnosticCriteria"]
            for _, query in queries
            if query["criteria_status"] == "mapped"
            and query["diagnosticCriteria"] is not None
        ),
        None,
    )
    for _, roi in roi_entries:
        roi["visualAttrs"] = (
            _mock_visual_attrs(
                candidate, relevant_criteria, conforming=roi["global_idx"] % 2 == 0
            )
            if relevant_criteria is not None
            else _default_visual_attrs(candidate)
        )
        roi["visualAttrs_info"] = _visual_attrs_info(roi["visualAttrs"])

    if not queries:
        for _, roi in roi_entries:
            roi["selection_history"].append(
                {
                    "stage": "visual_attributes_matching_filter",
                    "owner": "person_D",
                    "artifact_contract": "H.MatchedROIs",
                    "action": "legality_evaluated",
                    "status": "skipped",
                    "selected": False,
                    "reason": "no_visual_attribute_query",
                    "producer": config["component_version"],
                }
            )

    for record, query in queries:
        details: dict[str, tuple[float, bool, bool, list[str], list[str]]] = {}
        references = set(record["referenceWSI"])
        if query["criteria_status"] == "mapped":
            criteria = query["diagnosticCriteria"]
            for stain, roi in roi_entries:
                if references and stain["stain_id"] not in references:
                    continue
                result = _evaluate(roi["visualAttrs"], criteria)
                details[roi["roi_id"]] = result

        for stain, roi in roi_entries:
            in_reference = not references or stain["stain_id"] in references
            event: dict[str, Any] = {
                "stage": "visual_attributes_matching_filter",
                "owner": "person_D",
                "artifact_contract": "H.MatchedROIs",
                "action": "legality_evaluated",
                "status": "skipped",
                "selected": False,
                "reason": (
                    "diagnostic_criteria_unmapped"
                    if query["criteria_status"] == "unmapped"
                    else "outside_reference_wsi"
                    if not in_reference
                    else "visual_attribute_evaluation_unavailable"
                ),
                "producer": config["component_version"],
                "query_id": query["query_id"],
                "dx_pair_id": query["dx_pair_id"],
                "criteria_status": query["criteria_status"],
            }
            if in_reference and roi["roi_id"] in details:
                score, must_true, must_false, matched, failed = details[roi["roi_id"]]
                selected = (
                    must_true
                    and must_false
                    and score >= config["minimum_score"]
                )
                if selected:
                    reason = "visual_attribute_conditions_met"
                elif not must_true:
                    reason = "required_visual_attributes_missing"
                elif not must_false:
                    reason = "forbidden_visual_attributes_present"
                else:
                    reason = "visual_attribute_score_below_threshold"
                event.update(
                    {
                        "status": "selected" if selected else "rejected",
                        "selected": selected,
                        "reason": reason,
                        "score": score,
                        "threshold": config["minimum_score"],
                        "comparison": ">=",
                        "must_true_passed": must_true,
                        "must_false_passed": must_false,
                        "matched_attributes": matched,
                        "failed_attributes": failed,
                    }
                )
            roi["selection_history"].append(event)

    artifact = {
        "contract": "H.MatchedROIs",
        "schema_version": "2.0",
        "artifact_id": f"H-{case_id}",
        "case_id": case_id,
        "producer": config["component_version"],
        "payload": payload,
    }
    write_artifact(artifact, args.output, "H.MatchedROIs")


if __name__ == "__main__":
    main()
