from __future__ import annotations

import re
from typing import Any

from contracts.metadata import dx_items, single_case
from contracts.runtime import cli_parser, load_config, load_inputs, write_artifact


STOPWORDS = {
    "a",
    "an",
    "and",
    "for",
    "histologic",
    "in",
    "no",
    "not",
    "of",
    "or",
    "status",
    "the",
    "to",
    "type",
    "with",
    "without",
}


def _query_terms(dx_item: str, result: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", f"{dx_item} {result}".lower().replace("_", " "))
    return {word for word in words if len(word) > 1 and word not in STOPWORDS}


def _section_candidates(literature: dict[str, Any]) -> list[dict[str, Any]]:
    candidates = []
    for item in literature["payload"]["literature_list"]:
        title_path = " ".join(value for value in item["title_list"] if value)
        for section in item["sections"]:
            # Source-level literal "None" is preserved in A but is not evidence.
            if not section["text"].strip() or section["text"].strip().casefold() == "none":
                continue
            candidates.append(
                {
                    "literature_id": item["literature_id"],
                    "section_id": section["section_id"],
                    "source_idx": item["source_idx"],
                    "section_idx": section["section_idx"],
                    "title_list": item["title_list"],
                    "literature_title": item["title"],
                    "section_title": section["title"],
                    "source_href": item["href"],
                    "text": section["text"],
                    "title_haystack": f"{title_path} {item['title']} {section['title']}".lower(),
                }
            )
    return candidates


def _rank_sections(
    candidates: list[dict[str, Any]],
    dx_item: str,
    result: str,
    config: dict[str, Any],
) -> list[tuple[float, dict[str, Any]]]:
    terms = _query_terms(dx_item, result)
    result_phrase = " ".join(result.lower().split())
    section_priorities = {
        title.casefold(): len(config["preferred_section_titles"]) - index
        for index, title in enumerate(config["preferred_section_titles"])
    }
    ranked = []
    for candidate in candidates:
        title_haystack = " ".join(candidate["title_haystack"].split())
        text_haystack = candidate["text"].lower()
        exact_title_match = bool(result_phrase and result_phrase in title_haystack)
        title_hits = sum(term in title_haystack for term in terms)
        text_hits = sum(term in text_haystack for term in terms)
        section_priority = section_priorities.get(
            candidate["section_title"].casefold(), 0
        )
        raw_score = (
            title_hits * config["title_hit_weight"]
            + text_hits
            + (config["exact_title_bonus"] if exact_title_match else 0)
        )
        score = min(
            1.0,
            config["base_score"] + raw_score * config["score_per_keyword"],
        )
        rank_key = (
            int(exact_title_match),
            title_hits,
            section_priority,
            text_hits,
            -candidate["source_idx"],
            -candidate["section_idx"],
        )
        ranked.append((rank_key, round(score, 3), candidate))
    ranked.sort(key=lambda item: item[0], reverse=True)
    return [(score, candidate) for _, score, candidate in ranked]


def main() -> None:
    args = cli_parser("乙: retrieve F literature chunks for D diagnostic pairs").parse_args()
    inputs = load_inputs(args.input, ["A.Literature", "D.DxPairs"])
    literature = inputs["A.Literature"]
    dx_pairs = inputs["D.DxPairs"]
    config = load_config(args.config)
    case_id = dx_pairs["case_id"]
    single_case(dx_pairs)
    candidates = _section_candidates(literature)

    chunks = []
    chunk_index = 1
    for dx_item, pair in dx_items(dx_pairs["payload"]).items():
        ranked = _rank_sections(
            candidates, dx_item, pair["DxResultTxt"], config
        )
        for score, candidate in ranked[: config["top_k"]]:
            chunks.append(
                {
                    "chunk_id": f"{case_id}-chunk-{chunk_index:03d}",
                    "dx_pair_id": pair["dx_pair_id"],
                    "literature_id": candidate["literature_id"],
                    "section_id": candidate["section_id"],
                    "source_idx": candidate["source_idx"],
                    "section_idx": candidate["section_idx"],
                    "title_list": candidate["title_list"],
                    "literature_title": candidate["literature_title"],
                    "section_title": candidate["section_title"],
                    "source_href": candidate["source_href"],
                    "text": candidate["text"],
                    "relevance_score": round(score, 3),
                }
            )
            chunk_index += 1

    artifact = {
        "contract": "F.Chunks",
        "schema_version": "2.0",
        "artifact_id": f"F-{case_id}",
        "case_id": case_id,
        "producer": config["component_version"],
        "payload": {
            "corpus_id": literature["payload"]["corpus"]["corpus_id"],
            "chunks": chunks,
        },
    }
    write_artifact(artifact, args.output, "F.Chunks")


if __name__ == "__main__":
    main()
