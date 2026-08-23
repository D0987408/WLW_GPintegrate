from __future__ import annotations

from copy import deepcopy

from contracts.metadata import iter_stains, single_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


def main() -> None:
    args = cli_parser("丙: find E ROI references from the WSI path in D.DxPairs").parse_args()
    dx_pairs = load_inputs(args.input, ["D.DxPairs"])["D.DxPairs"]
    config = load_config(args.config)
    case_id = dx_pairs["case_id"]
    single_case(dx_pairs)
    payload = deepcopy(dx_pairs["payload"])

    global_idx = 0
    for wsi_index, stain in enumerate(iter_stains(payload), start=1):
        rois = []
        for region_index, region in enumerate(config["demo_regions"], start=1):
            xywh = [region["x"], region["y"], region["width"], region["height"]]
            cxcywh = [
                region["x"] + region["width"] / 2,
                region["y"] + region["height"] / 2,
                region["width"],
                region["height"],
            ]
            info = {
                "area": region["width"] * region["height"],
                "coords_seg": None,
                "cxcywh": cxcywh,
                "mpp": [config["demo_mpp"]["x"], config["demo_mpp"]["y"]],
                "roi_path": None,
                "roi_wh": [region["width"], region["height"]],
                "xywh": xywh,
            }
            rois.append(
                {
                    "roi_id": f"{case_id}-{stain['stain_id']}-roi-{region_index:03d}",
                    "global_idx": global_idx,
                    "local_idx": region_index - 1,
                    "level0_info": deepcopy(info),
                    "main_info": {**deepcopy(info), "mpp": config["demo_mpp"]["x"]},
                    "DxPair": None,
                    "visualAttrs": None,
                    "visualAttrs_info": None,
                    "selection_history": [
                        {
                            "stage": "interest_pattern_extraction",
                            "owner": "person_C",
                            "artifact_contract": "E.ROIs",
                            "selected": True,
                            "producer": config["component_version"],
                        }
                    ],
                }
            )
            global_idx += 1
        stain["roi_list"] = rois
        stain["roi_num"] = len(rois)

    artifact = {
        "contract": "E.ROIs",
        "schema_version": "2.0",
        "artifact_id": f"E-{case_id}",
        "case_id": case_id,
        "producer": config["component_version"],
        "payload": payload,
    }
    write_artifact(artifact, args.output, "E.ROIs")


if __name__ == "__main__":
    main()
