"""Readable orchestration of the diagram's multi-case batch DAG."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "integration" / "fixtures" / "input"
CONFIGS = ROOT / "integration" / "configs"


def run_component(module: str, inputs: list[Path], output: Path, config: Path) -> None:
    command = [sys.executable, "-m", module]
    for input_path in inputs:
        command.extend(["--input", str(input_path)])
    command.extend(["--output", str(output), "--config", str(config)])
    print(f"\n=== {module} ===", flush=True)
    subprocess.run(command, cwd=ROOT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the WLW contract-first multi-case DAG")
    parser.add_argument(
        "--report-tables",
        type=Path,
        default=FIXTURES / "B_report_tables.json",
        help="B.ReportTables manifest; one run may contain multiple tables and cases",
    )
    parser.add_argument(
        "--literature",
        type=Path,
        default=FIXTURES / "A_literature.json",
        help="Shared A.Literature artifact used for every case",
    )
    parser.add_argument(
        "--artifacts",
        type=Path,
        default=ROOT / "integration" / "artifacts-local",
        help="Run directory containing the D index and per-case D-I artifacts",
    )
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    artifacts.mkdir(parents=True, exist_ok=True)

    d_index_path = artifacts / "D_dx_pairs_index.json"
    run_component(
        "components.person_a.report_decompose",
        [args.report_tables.resolve()],
        d_index_path,
        CONFIGS / "report_decompose.json",
    )

    d_index = json.loads(d_index_path.read_text(encoding="utf-8"))
    completed_cases = []
    for entry in d_index["payload"]["cases"]:
        case_id = entry["case_id"]
        d = (d_index_path.parent / entry["artifact_path"]).resolve()
        case_artifacts = d.parent
        e = case_artifacts / "E_rois.json"
        f = case_artifacts / "F_chunks.json"
        g = case_artifacts / "G_queries.json"
        h = case_artifacts / "H_matches.json"
        selected_rois = case_artifacts / "I_selected_rois.json"

        print(f"\n##### case {case_id} #####", flush=True)
        run_component(
            "components.person_b.knowledge_retrieval",
            [args.literature.resolve(), d],
            f,
            CONFIGS / "knowledge_retrieval.json",
        )
        run_component(
            "components.person_a.query_generation",
            [d, f],
            g,
            CONFIGS / "query_generation.json",
        )
        run_component(
            "components.person_c.interest_pattern",
            [d],
            e,
            CONFIGS / "interest_pattern.json",
        )
        run_component(
            "components.person_d.visual_filter",
            [e, g],
            h,
            CONFIGS / "visual_filter.json",
        )
        run_component(
            "components.person_e.clee",
            [d, h],
            selected_rois,
            CONFIGS / "clee.json",
        )
        completed_cases.append(
            {
                "case_id": case_id,
                "selected_rois_path": str(selected_rois.relative_to(artifacts)),
            }
        )

    run_manifest = {
        "report_tables_artifact": str(args.report_tables.resolve()),
        "literature_artifact": str(args.literature.resolve()),
        "d_index": str(d_index_path.relative_to(artifacts)),
        "completed_cases": completed_cases,
        "skipped_cases": d_index["payload"].get("skipped_cases", []),
    }
    run_manifest_path = artifacts / "run_manifest.json"
    run_manifest_path.write_text(
        json.dumps(run_manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"\nPipeline complete: {len(completed_cases)} cases. "
        f"Run manifest: {run_manifest_path}"
    )


if __name__ == "__main__":
    main()
