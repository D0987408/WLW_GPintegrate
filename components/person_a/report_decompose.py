"""Contract-only example for the Person A report-decomposition boundary.

This module deliberately does not parse or classify report text.  It only
turns one CaseList case into a schema-valid D.DxPairs artifact so the shared
pipeline can be exercised before a real implementation is supplied.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from contracts.runtime import (
    cli_parser,
    load_case_list_input,
    load_config,
    write_artifact,
)


def _producer(config: dict[str, Any]) -> str:
    producer = config.get("component_version")
    if config.get("mode") != "example" or not isinstance(producer, str) or not producer:
        raise ValueError("Person A example requires an example config with component_version")
    return producer


def build_example_artifact(
    source: dict[str, Any], producer: str
) -> dict[str, Any]:
    """Wrap a single source case without interpreting its clinical content."""

    case = deepcopy(source["case_list"][0])
    case_id = case["case_id"]
    records: dict[str, dict[str, Any]] = {}
    for index, name in enumerate(source["DxItem_list"]):
        records[name] = {
            "dx_pair_id": f"{case_id}-example-dx-{index + 1:03d}",
            "source_report_id": f"{case_id}-example-report",
            "DxResultCls": "Not implemented",
            "DxResultTxt": "Example stub; replace with Person A implementation.",
            "DxResultRawTxt": None,
            "referenceBlock": None,
            "referenceType": [],
            "referenceWSI": [],
            "appear_reportTypes": [],
            "optionTypes": "example",
            "has_numericalData": False,
        }

    case["structured_report"] = {
        "reportType": None,
        "reportSubTypes": [],
        "DxItems": records,
    }
    for block in case["tissue_blocks"]:
        for stain in block["stains"]:
            stain["roi_num"] = 0
            stain["roi_list"] = []

    return {
        "contract": "D.DxPairs",
        "schema_version": "2.0",
        "artifact_id": f"D-example-{case_id}",
        "case_id": case_id,
        "producer": producer,
        "payload": {
            "data_mode": "inference",
            "DxItem_list": list(source["DxItem_list"]),
            "reference_versions": {
                "example_stub": {"implemented": False, "purpose": "contract smoke test"}
            },
            "case_list": [case],
        },
    }


def main() -> None:
    args = cli_parser("Person A example: CaseList input to D.DxPairs").parse_args()
    if len(args.input) != 1:
        raise ValueError("report_decompose accepts exactly one CaseList input")
    source = load_case_list_input(args.input[0], single_case=True)
    artifact = build_example_artifact(source, _producer(load_config(args.config)))
    write_artifact(artifact, args.output, "D.DxPairs")


if __name__ == "__main__":
    main()
