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
                        "F.Chunks": "F_chunks.json",
                        "G.VisualAttributeQueries": "G_queries.json",
                        "H.MatchedROIs": "H_matches.json",
                        "I.CLEESelectedROIs": "I_selected_rois.json",
                    }.items()
                }
                for contract, artifact in files.items():
                    validate_artifact(artifact, contract)
                    self.assertEqual("2.0", artifact["schema_version"])
                    self.assertEqual(case_id, artifact["case_id"])
                    if "case_list" in artifact["payload"]:
                        self.assertEqual(
                            case_id, artifact["payload"]["case_list"][0]["case_id"]
                        )

                d, e, f, g, h, result = (
                    files["D.DxPairs"],
                    files["E.ROIs"],
                    files["F.Chunks"],
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
                for chunk in f["payload"]["chunks"]:
                    self.assertTrue(chunk["section_id"])
                    self.assertEqual(4, len(chunk["title_list"]))
                    self.assertNotEqual("none", chunk["text"].strip().casefold())

                for _, roi in iter_rois(e["payload"]):
                    self.assertIsNone(roi["DxPair"])
                    self.assertIsNone(roi["visualAttrs"])
                    self.assertEqual(
                        ["interest_pattern_extraction"],
                        [event["stage"] for event in roi["selection_history"]],
                    )
                    event = roi["selection_history"][0]
                    self.assertEqual("candidate_generated", event["action"])
                    self.assertEqual("selected", event["status"])
                    self.assertEqual(
                        "interest_pattern_candidate_generated", event["reason"]
                    )
                for _, roi in iter_rois(h["payload"]):
                    self.assertIsNone(roi["DxPair"])
                    self.assertIsInstance(roi["visualAttrs"], dict)
                    self.assertIsInstance(roi["visualAttrs_info"], dict)
                    self.assertIn(
                        "visual_attributes_matching_filter",
                        [event["stage"] for event in roi["selection_history"]],
                    )
                    for event in roi["selection_history"]:
                        self.assertEqual(
                            event["selected"], event["status"] == "selected"
                        )
                        self.assertTrue(event["action"])
                        self.assertTrue(event["reason"])
                        if event["stage"] == "visual_attributes_matching_filter":
                            self.assertNotIn("rank", event)

                h_rois = {roi["roi_id"]: roi for _, roi in iter_rois(h["payload"])}
                for _, roi in iter_rois(result["payload"]):
                    stages = [event["stage"] for event in roi["selection_history"]]
                    self.assertIn("interest_pattern_extraction", stages)
                    self.assertIn("visual_attributes_matching_filter", stages)
                    self.assertIn("clee", stages)
                    h_history = h_rois[roi["roi_id"]]["selection_history"]
                    self.assertEqual(
                        h_history,
                        roi["selection_history"][: len(h_history)],
                    )
                    clee_events = [
                        event
                        for event in roi["selection_history"]
                        if event["stage"] == "clee"
                    ]
                    self.assertEqual(1, len(clee_events))
                    clee_event = clee_events[0]
                    self.assertEqual(
                        clee_event["selected"],
                        clee_event["status"] == "selected",
                    )
                    if clee_event["action"] == "evidence_evaluated":
                        self.assertIn("pseudo_DxPair", roi)
                        prediction = roi["pseudo_DxPair"]["finalResult"][
                            "Histologic_Type"
                        ]
                        self.assertEqual(
                            clee_event["selected"], prediction["assigned_as_ref"]
                        )
                        self.assertEqual(clee_event["score"], prediction["importance"])
                        self.assertEqual(">=", clee_event["comparison"])
                    else:
                        self.assertEqual("skipped", clee_event["status"])
                        self.assertNotIn("pseudo_DxPair", roi)

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

                provenance = result["payload"]["reference_versions"]["clee_inference"]
                clee_events = [
                    event
                    for _, roi in iter_rois(result["payload"])
                    for event in roi["selection_history"]
                    if event["stage"] == "clee"
                ]
                self.assertEqual("fixture", provenance["backend"])
                self.assertEqual(["Histologic_Type"], provenance["effective_dx_items"])
                self.assertIn("Microcalcification", provenance["checkpoint_active_dx_items"])
                self.assertEqual(
                    len([e for e in clee_events if e["action"] == "evidence_evaluated"]),
                    provenance["evaluated_roi_count"],
                )
                self.assertEqual(
                    len([e for e in clee_events if e["status"] == "skipped"]),
                    provenance["skipped_roi_count"],
                )

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
            for _, roi in iter_rois(case_two_i["payload"]):
                clee_event = next(
                    event
                    for event in roi["selection_history"]
                    if event["stage"] == "clee"
                )
                self.assertEqual("skipped", clee_event["status"])
                self.assertEqual("unsupported_dx_result", clee_event["reason"])
                self.assertNotIn("pseudo_DxPair", roi)

            visual_config = json.loads(
                (ROOT / "integration" / "configs" / "visual_filter.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertNotIn("top_k_per_query", visual_config)

            case_one_h = json.loads(
                (case_one_dir / "H_matches.json").read_text(encoding="utf-8")
            )
            for _, roi in iter_rois(case_one_h["payload"]):
                for event in roi["selection_history"]:
                    if (
                        event["stage"] == "visual_attributes_matching_filter"
                        and event["status"] == "selected"
                    ):
                        event["status"] = "rejected"
                        event["selected"] = False
                        event["reason"] = "visual_attribute_score_below_threshold"
                        event["score"] = 0.0
            empty_h_path = artifacts / "case-001-H-none-selected.json"
            empty_i_path = artifacts / "case-001-I-none-selected.json"
            empty_h_path.write_text(
                json.dumps(case_one_h, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "components.person_e.clee",
                    "--input",
                    str(case_one_dir / "D_dx_pairs.json"),
                    "--input",
                    str(empty_h_path),
                    "--output",
                    str(empty_i_path),
                    "--config",
                    str(ROOT / "integration" / "configs" / "clee.json"),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )
            empty_i = json.loads(empty_i_path.read_text(encoding="utf-8"))
            validate_artifact(empty_i, "I.CLEESelectedROIs")
            self.assertEqual(
                ["skipped_no_eligible_rois"],
                empty_i["payload"]["reference_versions"]["clee_inference"][
                    "execution_statuses"
                ],
            )
            for _, roi in iter_rois(empty_i["payload"]):
                clee_event = next(
                    event
                    for event in roi["selection_history"]
                    if event["stage"] == "clee"
                )
                self.assertEqual("skipped", clee_event["status"])
                self.assertEqual(
                    "upstream_visual_filter_rejected", clee_event["reason"]
                )
                self.assertNotIn("pseudo_DxPair", roi)


if __name__ == "__main__":
    unittest.main()
