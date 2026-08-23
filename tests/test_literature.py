from __future__ import annotations

import unittest
from pathlib import Path

from components.person_b.knowledge_retrieval import _rank_sections, _section_candidates
from components.person_b.prepare_literature import build_literature_artifact
from contracts.runtime import validate_artifact


LAB20 = Path(__file__).resolve().parents[2]
SOURCE = LAB20 / "cleanSections_metaList_2603201640.json"


class LiteraturePreparationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.artifact = build_literature_artifact(
            SOURCE,
            {
                "component_version": "person-b/literature-preparation:test",
                "corpus_id": "who-breast-tumours-5e-test",
            },
        )

    def test_full_source_preserves_text_hierarchy_without_images(self) -> None:
        validate_artifact(self.artifact, "A.Literature")
        literature_list = self.artifact["payload"]["literature_list"]
        self.assertEqual(122, len(literature_list))
        self.assertEqual(1400, sum(len(item["sections"]) for item in literature_list))
        self.assertTrue(all(len(item["title_list"]) == 4 for item in literature_list))
        self.assertTrue(all("images" not in item for item in literature_list))

        literature_ids = [item["literature_id"] for item in literature_list]
        section_ids = [
            section["section_id"]
            for item in literature_list
            for section in item["sections"]
        ]
        self.assertEqual(len(literature_ids), len(set(literature_ids)))
        self.assertEqual(len(section_ids), len(set(section_ids)))

    def test_literal_none_is_preserved_but_not_retrieved(self) -> None:
        literature_list = self.artifact["payload"]["literature_list"]
        literal_none = sum(
            section["text"] == "None"
            for item in literature_list
            for section in item["sections"]
        )
        self.assertEqual(93, literal_none)
        normalized_none = sum(
            section["text"].strip().casefold() == "none"
            for item in literature_list
            for section in item["sections"]
        )
        candidates = _section_candidates(self.artifact)
        self.assertEqual(1400 - normalized_none, len(candidates))
        self.assertTrue(
            all(candidate["text"].strip().casefold() != "none" for candidate in candidates)
        )

    def test_full_diagnostic_title_and_histopathology_are_ranked_first(self) -> None:
        candidates = _section_candidates(self.artifact)
        config = {
            "base_score": 0.2,
            "score_per_keyword": 0.1,
            "title_hit_weight": 3,
            "exact_title_bonus": 4,
            "preferred_section_titles": [
                "Histopathology",
                "Essential and desirable diagnostic criteria",
                "Definition",
            ],
        }
        for diagnosis in [
            "Invasive breast carcinoma of no special type",
            "Invasive lobular carcinoma",
        ]:
            _, best = _rank_sections(
                candidates, "Histologic_Type", diagnosis, config
            )[0]
            self.assertEqual(diagnosis, best["literature_title"])
            self.assertEqual("Histopathology", best["section_title"])


if __name__ == "__main__":
    unittest.main()
