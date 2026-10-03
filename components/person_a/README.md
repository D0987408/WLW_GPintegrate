# Person A implementation slot

This directory contains contract-only examples, not the Person A research implementation.

- `report_decompose`: `CaseListInput@1.0` → `D.DxPairs@2.0`
- `query_generation`: `D.DxPairs@2.0` + `F.Chunks@2.0` → `G.VisualAttributeQueries@2.0`

The examples preserve the CLI and emit schema-valid placeholders. They do not interpret reports,
load reference data, or generate diagnostic criteria.

```bash
python -m components.person_a.report_decompose \
  --input ../run/input/pipeline/case-001.json \
  --output ../run/output/work/D_dx_pairs.json \
  --config components/person_a/configs/example.json
```
