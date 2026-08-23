from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from contracts.metadata import dx_items, iter_rois, iter_stains
from contracts.runtime import validate_artifact


ROOT = Path(__file__).resolve().parents[1]


class PipelineSmokeTest(unittest.TestCase):
    def test_multi_case_metadata_shaped_pipeline(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            artifacts = Path(temp_dir)
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "pipeline" / "run_pipeline.py"),
                    "--artifacts",
                    temp_dir,
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            d_index = json.loads(
                (artifacts / "D_dx_pairs_index.json").read_text(encoding="utf-8")
            )
            validate_artifact(d_index, "D.DxPairsIndex")
            self.assertEqual(
                ["case-001", "case-002", "case-003"],
                [entry["case_id"] for entry in d_index["payload"]["cases"]],
            )

            run_manifest = json.loads(
                (artifacts / "run_manifest.json").read_text(encoding="utf-8")
            )
            self.assertEqual(3, len(run_manifest["completed_cases"]))
            self.assertEqual([], run_manifest["skipped_cases"])

            for entry in d_index["payload"]["cases"]:
                case_id = entry["case_id"]
                case_dir = artifacts / "cases" / case_id
                files = {
                    contract: json.loads((case_dir / filename).read_text(encoding="utf-8"))
                    for contract, filename in {
                        "D.DxPairs": "D_dx_pairs.json",
                        "E.ROIs": "E_rois.json",
                        "G.VisualAttributeQueries": "G_queries.json",
                        "H.MatchedROIs": "H_matches.json",
                        "I.CLEESelectedROIs": "I_selected_rois.json",
                    }.items()
                }
                for contract, artifact in files.items():
                    validate_artifact(artifact, contract)
                    self.assertEqual("2.0", artifact["schema_version"])
                    self.assertEqual(case_id, artifact["case_id"])
                    self.assertEqual(case_id, artifact["payload"]["case_list"][0]["case_id"])

                d, e, g, h, result = (
                    files["D.DxPairs"],
                    files["E.ROIs"],
                    files["G.VisualAttributeQueries"],
                    files["H.MatchedROIs"],
                    files["I.CLEESelectedROIs"],
                )
                self.assertTrue(d["payload"]["case_list"][0]["report_raw_content"])
                expected_paths = {stain["filepath"] for stain in iter_stains(d["payload"])}
                self.assertEqual(
                    expected_paths,
                    {stain["filepath"] for stain in iter_stains(e["payload"])},
                )
                self.assertEqual(len(expected_paths) * 2, len(list(iter_rois(e["payload"]))))

                for _, roi in iter_rois(e["payload"]):
                    self.assertIsNone(roi["DxPair"])
                    self.assertIsNone(roi["visualAttrs"])
                    self.assertEqual(
                        ["interest_pattern_extraction"],
                        [event["stage"] for event in roi["selection_history"]],
                    )
                for _, roi in iter_rois(h["payload"]):
                    self.assertIsNone(roi["DxPair"])
                    self.assertIsInstance(roi["visualAttrs"], dict)
                    self.assertIsInstance(roi["visualAttrs_info"], dict)
                    self.assertIn(
                        "visual_attributes_matching_filter",
                        [event["stage"] for event in roi["selection_history"]],
                    )
                for _, roi in iter_rois(result["payload"]):
                    stages = [event["stage"] for event in roi["selection_history"]]
                    self.assertIn("interest_pattern_extraction", stages)
                    self.assertIn("visual_attributes_matching_filter", stages)
                    self.assertIn("clee", stages)

                result_items = dx_items(result["payload"])
                for stain, roi in iter_rois(result["payload"]):
                    for event in roi["selection_history"]:
                        if event["stage"] == "clee" and event["selected"]:
                            record = next(
                                item
                                for item in result_items.values()
                                if item["dx_pair_id"] == event["dx_pair_id"]
                            )
                            self.assertIn(stain["stain_id"], record["referenceWSI"])

            case_one_dir = artifacts / "cases" / "case-001"
            case_one_d = json.loads(
                (case_one_dir / "D_dx_pairs.json").read_text(encoding="utf-8")
            )
            case_one_g = json.loads(
                (case_one_dir / "G_queries.json").read_text(encoding="utf-8")
            )
            histologic = dx_items(case_one_d["payload"])["Histologic_Type"]
            self.assertEqual(["HE"], histologic["referenceType"])
            self.assertEqual(["case-001-he"], histologic["referenceWSI"])
            query = dx_items(case_one_g["payload"])["Histologic_Type"][
                "visualAttrQueries"
            ][0]
            self.assertEqual("mapped", query["criteria_status"])
            self.assertEqual("1.2.1", query["diagnosticCriteria"]["version"])
            self.assertEqual(
                "ordinal",
                query["diagnosticCriteria"]["visualAttrs"]["Cellular_and_Nuclear"][
                    "Polarity"
                ]["type"],
            )

            case_two_dir = artifacts / "cases" / "case-002"
            case_two_g = json.loads(
                (case_two_dir / "G_queries.json").read_text(encoding="utf-8")
            )
            case_two_i = json.loads(
                (case_two_dir / "I_selected_rois.json").read_text(encoding="utf-8")
            )
            unmapped_query = dx_items(case_two_g["payload"])["Histologic_Type"][
                "visualAttrQueries"
            ][0]
            self.assertEqual("unmapped", unmapped_query["criteria_status"])
            self.assertIsNone(unmapped_query["diagnosticCriteria"])
            self.assertFalse(
                any(
                    event["selected"]
                    for _, roi in iter_rois(case_two_i["payload"])
                    for event in roi["selection_history"]
                    if event["stage"] in {"visual_attributes_matching_filter", "clee"}
                )
            )


if __name__ == "__main__":
    unittest.main()
