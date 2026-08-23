# 戊的準備與交付清單

## 你的責任邊界

戊負責將文字診斷 pair 與配對後的影像 evidence 送入 CLEE，產生整體核心框架的最終 ROI：

```text
D.DxPairs ─────────────┐
                        ├─> CLEE ──> I.CLEESelectedROIs  （核心最終產物）
H.MatchedROIs ─────────┘                  │
                                         └─> DRGVLM 等 evaluation consumers
```

DRGVLM 不是戊的 CLEE component，也不是核心 DAG 的最後一步。它只是拿 I 做實驗的方法之一；
未來換成其他 VLM、人工閱片或統計分析時，核心 A、B、D～I pipeline 不應因此改動。

## 需要準備的東西與放置位置

| 要準備的項目 | 放置位置 | 說明 |
|---|---|---|
| WLW orchestration | `components/person_e/clee.py` | 讀 D/H、做 eligibility/support join、合併 inference output、寫 I |
| Backend adapter | `components/person_e/adapter.py` | checkpoint support preflight、fixture/external backend、layered trace |
| Python dependencies | `components/person_e/requirements.txt` | 只放 CLEE 的直接依賴；DRGVLM 有自己的 evaluation environment |
| OS/CUDA dependencies | `components/person_e/Dockerfile` | 若需要 GPU/CUDA，需改 base image 並記錄相容性 |
| 預設 config | `components/person_e/configs/default.json` | backend、checkpoint/bundle paths、WLW whitelist、forward chunk limit |
| External config 範例 | `components/person_e/configs/external.example.json` | 純推論 CLI command template 與 path placeholders |
| Runtime/model manifest | `components/person_e/component.yaml` | Python、CPU/RAM/GPU、timeout、entrypoint |
| D input example | `integration/artifacts-local/cases/case-001/D_dx_pairs.json` | 由甲產生 |
| H input example | `integration/artifacts-local/cases/case-001/H_matches.json` | 由丁產生；完整保留 ROI 並標記 matching 結果 |
| 最終 expected output | `integration/artifacts-local/cases/case-001/I_selected_rois.json` | 完整 metadata case 與 CLEE selection events |
| D/H/I schemas | `contracts/schemas/` | I 是核心最終 contract |
| Model checkpoint | host `/models/person-e/<model>/<revision>/` | 唯讀 mount；不放 image |
| DRGVLM 程式與環境 | `evaluation/drgvlm/` | 與 person_e image/environment 分離 |
| Evaluation output | 建議 `/runs/<run_id>/evaluation/drgvlm/` | 不覆寫 I 或中間 D/H artifact |

## D 與 H 如何對齊

只能使用 stable ID join：

```text
D.structured_report.DxItems.*.dx_pair_id == H ROI event.dx_pair_id
D.structured_report.DxItems.*.referenceWSI contains ROI 所屬 stain_id
```

不可假設 array index 能表達對應關係。H 可能：

- 同一個 diagnosis 對應多個 ROI。
- 某個 diagnosis 沒有 ROI。
- matching 排序因模型版本改變。

I 保留 H 的完整 metadata shell，並在每個 ROI 的 `selection_history[]` 追加 CLEE 的
action/status/reason/score/query/dx linkage。只有真正送進模型的 ROI 才加入原樣 layered
`pseudo_DxPair`，讓 consumer 能重建同一 ROI 並一路追回 D/H/CLEE。

## 已確定的推論語意

- 目前 WLW policy 只允許 `Histologic_Type`，再與 checkpoint active label space 取交集。
- H 未通過的 ROI 不送 model；I 記錄 `status=skipped`、
  `reason=upstream_visual_filter_rejected`。
- H 全部未通過時不 fallback；不呼叫 backend，selected ROI 合法地為 0。
- CLEE `finalResult.assigned_as_ref=true/false` 分別映射成 I 的 selected/rejected。
- `assigned` 是七類 ROI pseudo result；不得與 evidence selection 混成同一欄位。
- 所有高於 validation-calibrated case-importance threshold 的 ROI 都 selected，不取 top-k。
- classification thresholds、case-importance threshold、active space、epoch 與 bundle ID 都記入 trace/provenance。
- `max_roi_dxitem_inputs_per_forward` 是 hierarchical chunk 上限，不是 ROI sampling limit。

`backend.mode=fixture` 只供本 repo 的 contract/E2E 測試。正式 CLEE 使用
`backend.mode=external_command`，由 `command_template` 的
`{input_metadata}`、`{output_metadata}`、`{checkpoint_dir}`、`{image_root}` 與
`{max_roi_dxitem_inputs_per_forward}` placeholders 接入純推論 CLI。CLI 必須保留 `roi_id`，並為每個
submitted ROI 寫入含 `finalResult` 的 `pseudo_DxPair`。

## I 與下游 DRGVLM 的邊界

I 對每個 ROI 的最低必要內容是：

```text
case_id + dx_pair_id + roi_id + stain.filepath + level0_info + selection_history
evaluated ROI additionally requires pseudo_DxPair
```

由 DRGVLM 按座標讀取 pixels。若 CLEE 已產生 dynamic-MPP PNG，可在 I 提供 `roi_image_uri` 作
cache；仍應保留 WSI reference/level-0 coordinate 作 authoritative provenance。DRGVLM 自己的 prompt、
model weight、config 與 metrics 放 `evaluation/drgvlm/` 及 `/runs/<run_id>/evaluation/`，不要混入 I。

## 交付前自己跑

```bash
python3 pipeline/run_pipeline.py

python3 -m components.person_e.clee \
  --input integration/artifacts-local/cases/case-001/D_dx_pairs.json \
  --input integration/artifacts-local/cases/case-001/H_matches.json \
  --output /tmp/I_selected_rois.json \
  --config components/person_e/configs/default.json

python3 -m unittest discover -s tests -v
```

## 完成定義

- canonical D/H 能執行，最終 I 通過 schema。
- join 只靠 stable IDs，不靠 array index 或檔名順序。
- H 空 matches 不觸發 CLEE forward；全部 ROI 保留 H 事實與 CLEE skipped reason。
- checkpoint config 與 threshold bundle active spaces 必須一致；有效支援再受 WLW whitelist 限制。
- evaluated ROI 有完整 `pseudo_DxPair`；skipped ROI 不偽造 model output。
- 每個 selected ROI 能 trace 到 D、G、H、E 與原 WSI。
- DRGVLM 不被 import 進 CLEE；它只透過 I contract 消費結果。
- image 不包含資料、credential 或大型 checkpoint。
