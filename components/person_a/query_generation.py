"""Contract-only example for the Person A query-generation boundary."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from contracts.metadata import ensure_same_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


def _producer(config: dict[str, Any]) -> str:
    producer = config.get("component_version")
    if config.get("mode") != "example" or not isinstance(producer, str) or not producer:
        raise ValueError("Person A example requires an example config with component_version")
    return producer


def build_example_artifact(
    d_artifact: dict[str, Any], f_artifact: dict[str, Any], producer: str
) -> dict[str, Any]:
    """Emit empty query lists without performing mapping or generation."""

    case_id = ensure_same_case(d_artifact, f_artifact)
    payload = deepcopy(d_artifact["payload"])
    for record in payload["case_list"][0]["structured_report"]["DxItems"].values():
        record["visualAttrQueries"] = []
    payload.setdefault("reference_versions", {})["example_query_stub"] = {
        "implemented": False,
        "purpose": "contract smoke test",
    }
    return {
        "contract": "G.VisualAttributeQueries",
        "schema_version": "2.0",
        "artifact_id": f"G-example-{case_id}",
        "case_id": case_id,
        "producer": producer,
        "payload": payload,
    }


def main() -> None:
    args = cli_parser("Person A example: D.DxPairs and F.Chunks to G").parse_args()
    inputs = load_inputs(args.input, ["D.DxPairs", "F.Chunks"])
    artifact = build_example_artifact(
        inputs["D.DxPairs"],
        inputs["F.Chunks"],
        _producer(load_config(args.config)),
    )
    write_artifact(artifact, args.output, "G.VisualAttributeQueries")


if __name__ == "__main__":
    main()
