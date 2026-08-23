# WLW integration mini demo

這是一個 **contract-first、containerized batch DAG**。它把
`WLW_arch.png` 的甲～戊、`[A]`～`[H]` 與最終 `[I]` ROI 做成可執行範例；模型、WSI 演算法與 CLEE
邏輯都是 deterministic mock。

## 圖與程式的對應

<div align="center">
  <img src="https://github.com/yasaisen/WLW_GPintegrate/blob/main/doc/WLW_arch_v3.png" alt="inference" width="700">
</div>

| 人員 | 此 demo 的 executable | 輸入 | 輸出 |
|---|---|---|---|
| 甲 | `report_decompose` | B report-table manifest | D case index + per-case D |
| 乙 | `knowledge_retrieval` | A、D | F |
| 甲 | `query_generation` | D、F | G |
| 丙 | `interest_pattern` | D | E |
| 丁 | `visual_filter` | E、G | H |
| 戊 | `clee` | D、H | I：CLEE selected ROIs（核心最終產物） |

執行關係如下：

```text
B Excel/table manifests ─> 甲/report_decompose ─> D case index
                                                   ├─> case-001 D (metadata-shaped case)
                                                   ├─> case-002 D (metadata-shaped case)
                                                   └─> ...

每個 case：
A literature + D ─> 乙/retrieval ─> F；D + F ─> 甲/query_generation ─> G
D ─> 丙/interest_pattern ─> E；E + G ─> 丁/visual_filter ─> H；D + H ─> 戊/CLEE ─> I
```

DRGVLM 不在核心 DAG 內；它只是讀取 I 做下游實驗的其中一個 evaluation consumer。

D/E/G/H/I schema version 2.0 共用 metadata-shaped payload。每份 artifact 仍只包含一個 case，
batch 的多 case fan-out 由 `D.DxPairsIndex` 與 pipeline controller 管理：

```text
payload.DxItem_list
payload.case_list[0]
├── report_raw_content
├── structured_report.DxItems
└── tissue_blocks[].stains[]
    ├── filepath                         # report table 帶入的 wsi_path
    └── roi_list[]
        ├── level0_info / main_info      # E 起加入
        ├── visualAttrs / visualAttrs_info # H 起填入
        └── selection_history[]          # 丙、丁、戊逐階段追加
```

注意 artifact 中沒有 base64 image；WSI 由 `stains[].filepath` 指向，ROI crop 可由
`level0_info`/`main_info` 重建，因此大型 WSI 不必在元件間複製。inference 模式的 ROI
`DxPair` 固定為 `null`，ROI-level GT 只應在 `ground_truth` 或 `evaluation` 資料中出現。

## 1. 不用 Docker，先看一次完整流程

本 demo 只有 Python standard library dependency：

```bash
cd WLW_integrate
python3 pipeline/run_pipeline.py
```

每一步都由 orchestrator 以相同 execution contract 呼叫：

```text
python3 -m <component> \
  --input <artifact.json> [--input <another-artifact.json>] \
  --output <artifact.json> \
  --config <config.json>
```

輸出會寫到 `integration/artifacts-local/`：

```text
D_dx_pairs_index.json
run_manifest.json
cases/
├── case-001/
│   ├── D_dx_pairs.json
│   ├── F_chunks.json
│   ├── G_queries.json
│   ├── E_rois.json
│   ├── H_matches.json
│   └── I_selected_rois.json
└── case-002/...
```

這些中間檔就是圖上的箭頭；直接打開它們會比只看架構文字更有感。

## 2. 單獨把一個元件當 black box 執行

例如甲的 Report Decompose：

```bash
python3 -m components.person_a.report_decompose \
  --input integration/fixtures/input/B_report_tables.json \
  --output /tmp/D_dx_pairs_index.json \
  --config integration/configs/report_decompose.json
```

甲會依 `table_type` 選擇 VGHTC/CGMH parser，在內部完成 table → reports/WSIs → DxPairs，
並輸出 D index 與 per-case D。integration layer 只依賴 CLI、contracts 與 exit code。

B 是整批執行的來源 manifest，結構如下；`table_path` 可指向單一標準化 CSV/XLSX，也可直接指向
該院 raw-data directory：

```json
{
  "contract": "B.ReportTables",
  "schema_version": "1.0",
  "artifact_id": "report-tables-run-001",
  "payload": {
    "tables": [
      {"table_idx": 0, "table_type": "VGHTC2024", "table_path": "/data/raw/VGHTC"},
      {"table_idx": 1, "table_type": "CGMH2019", "table_path": "/data/raw/CGMH"}
    ]
  }
}
```

目前 VGHTC adapter 會合併兩份病理報告 Excel、`VGHTC_list_total_2.xlsx` 與 `data_path`；
CGMH adapter 會合併 `Pathology_Report_v1.xlsx`、`Pathology_image_path_v1.csv`、
`CGMH_list_total.xlsx` 與 `data_path`。標準化 CSV/XLSX 可提供 `dx_item`、`dx_result` 與
`reference_wsi_ids`；原始院端表則先正規化 report、case、block、stain 與 WSI 路徑，實際
structured-report 模型可在甲的 extraction boundary 接入。

DxItem 合法值與欄位預設值在執行時讀取 lab_19 的
`DxStructuredCandidates_integrated.json`。若來源沒有明示 WSI：`referenceType` 有指定時選該染色
（例如 `HE` 會選該 case 全部 HE WSI），`referenceType` 也沒有指定時才選該 case 全部 WSI；
明示 `reference_wsi_ids` 時以明示內容為準。

G 的 Histologic Type 條件不是硬編碼。`query_generation` 每次執行都讀取專案根目錄的
`Histologic_Type_mappingTable.json`，再連到 `[typeLevel]visualAttrs_v1.2.1_2603241656.json` 的
單一亞型條件。mapping 找不到時保留 query，輸出 `criteria_status: "unmapped"` 與
`diagnosticCriteria: null`，讓後續元件明確拒絕而不是猜測。`Polarity.type` 以 `ordinal` 為準，
type-level reference 版本以檔名 `1.2.1` 為準。

有兩種上游資料的元件只是重複 `--input`。例如丁：

```bash
python3 -m components.person_d.visual_filter \
  --input integration/artifacts-local/cases/case-001/E_rois.json \
  --input integration/artifacts-local/cases/case-001/G_queries.json \
  --output /tmp/H_matches.json \
  --config integration/configs/visual_filter.json
```

## 3. Contract test

`contracts/schemas/` 是 A、B、D～I 的 canonical JSON Schema；D/E/G/H/I 共用
`metadata_case_payload.schema.json`。runtime 會在讀取輸入及寫出輸出時
各驗一次，fail fast；測試再驗證 canonical fixtures、整條 pipeline 與一個刻意破壞的 artifact：

```bash
python3 -m unittest discover -s tests -v
```

本 demo 為了零 dependency，`contracts/runtime.py` 實作了本專案 schema 所需的 JSON Schema
子集合。正式專案建議直接用 `jsonschema`、Pydantic，並把 `contracts` 發布成有版本的 package。

## 4. Docker Compose 整合測試

每位成員有自己的 Dockerfile；不是共用同一個 Python environment：

```bash
cd integration
LOCAL_UID=$(id -u) LOCAL_GID=$(id -g) \
  docker compose up --build --abort-on-container-failure
```

Compose 用 `service_completed_successfully` 表達 DAG 依賴，產物會留在
`integration/artifacts/`。傳入 host UID/GID 是為了避免 bind mount 的產物變成 root-owned。
這裡把 Compose 當 E2E integration test，而
`pipeline/run_pipeline.py` 才是清楚、可讀的 scientific pipeline controller。
由於 Compose 是靜態 DAG，此 demo 會完整產生多 case D，但只用 `case-001` 驗證一條
containerized case-level DAG；動態多 case fan-out 由 `run_pipeline.py` 負責。

若在 HPC 執行，可將相同 image 推到 registry，再由 Apptainer 拉 OCI image；資料與模型應
以唯讀 mount 提供，不要 `COPY` 進 image。

## 5. 每位成員要交什麼

這個資料夾示範了以下交付邊界：

1. `contracts/schemas/*.schema.json`：A、B、D～I 資料 contract 與 schema version。
2. `integration/fixtures/input/`：canonical input example。
3. `components/person_*/`：統一 CLI 的 independent executable。
4. `components/person_*/requirements.txt` 與 `Dockerfile`：各自的 Python 與系統 runtime。
5. `tests/`：contract test 與 E2E smoke test。
6. `component.yaml`：owner、I/O、資源與 entrypoint manifest。

每位成員的詳細準備清單：

- [甲：Report Decompose / Query Generation](components/person_a/PREPARATION.md)
- [乙：Knowledge Base / Retrieval](components/person_b/PREPARATION.md)
- [丙：WSI Interest Pattern Extraction](components/person_c/PREPARATION.md)
- [丁：Visual Attribute Extraction / Matching](components/person_d/PREPARATION.md)
- [戊：CLEE / Downstream Handoff](components/person_e/PREPARATION.md)

實際接入時，每個 mock 函式可被真正方法逐一替換；只要 CLI 和 A、B、D～I contracts 不變，其他
成員與 pipeline 不需跟著重寫。

