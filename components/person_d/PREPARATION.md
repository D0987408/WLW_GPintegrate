# 丁（Person D）：Visual Attribute Filter 準備與交付

丁負責合併 `[E]` ROI 與 `[G]` query，產生 `[H]` matching artifact。目前 stub 不讀 WSI、不做
visual attribute 推論，只建立合法 H shell；正式交付應替換內部方法但保留所有 ROI 與稽核事件。

## 1. Input／output 規格

| Entrypoint | Input | Output |
|---|---|---|
| `components.person_d.visual_filter` | `[E] E.ROIs@2.0` + `[G] G.VisualAttributeQueries@2.0` | `[H] H.MatchedROIs@2.0` |

- E/G/H 的 `case_id` 必須相同；不得依 `--input` 順序猜測 contract。
- H 必須保留 E 的所有 ROI，不可只輸出 selected ROI。
- 每個已處理 ROI 應保留上游 `selection_history`，再追加合法的
  `visual_attributes_matching_filter` event。
- query unmapped、非 reference WSI、推論失敗與條件不符的語意須分成 skipped／rejected，不得靜默丟棄。
- 讀取 WSI 時使用 E 的 `stains[].filepath` 與 ROI geometry；不得建立另一套未記錄的 WSI root。

Canonical schemas：

- `contracts/schemas/E_rois.schema.json`
- `contracts/schemas/G_visual_attribute_queries.schema.json`
- `contracts/schemas/H_matched_rois.schema.json`
- `contracts/schemas/metadata_case_payload.schema.json`

## 2. 打包準備

```text
WLW_GPintegrate/components/person_d/       # 程式、環境與非敏感 config
reference/person_d/checkpoint/             # vision／multimodal checkpoint
reference/person_d/template_ref/           # prompt、visual vocabulary、label metadata
run/input/                                 # E、G 或 pipeline case artifacts
run/output/pipeline/cases/<case_id>/        # H artifact
run/cache/person_d/                         # 可刪除 feature/cache
```

- 模型 architecture、ROI reader 與 matching code 放 component；權重、prompt metadata 放 reference。
- target MPP、window/stride、batch size、threshold、query text 選擇與 device 只放 config。
- 不將 checkpoint、WSI、prompt 私有資料或 feature cache COPY 進 image。
- 資產 manifest 應記錄 model/prompt revision、SHA-256、license 與相容 schema/version。

## 3. Unified CLI

容器介面：

```bash
component \
  --input /input/E_rois.json \
  --input /input/G_queries.json \
  --output /output/H_matches.json \
  --config /config/visual_filter.yaml
```

目前 Python／JSON config 形式：

```bash
python -m components.person_d.visual_filter \
  --input ../run/output/work/E_rois.json \
  --input ../run/output/work/G_queries.json \
  --output ../run/output/work/H_matches.json \
  --config components/person_d/configs/example.json
```

case 不一致、ROI geometry 不合法、WSI/reference/checkpoint 缺失、CUDA 或推論錯誤時必須 non-zero exit，
且不得寫出部分 H。

## 4. Dockerfile／requirements.txt

目前 stub 使用 Python 3.12、CPU 與 standard library。正式版本必須固定 WSI reader、影像 framework、
模型 framework、模型程式 revision 與 CUDA runtime，並由 clean machine 建置：

```bash
docker build --no-cache \
  -f components/person_d/Dockerfile \
  -t wlw/person-d:<version> .
```

若 dependency 來自 Git，必須固定 commit。README 記錄目標 GPU、最低 VRAM、CPU fallback、RAM、batch
size 與 timeout；在 canonical example 上實際測量，而不是只抄開發機規格。

## 5. Canonical example

至少交付：

```text
components/person_d/examples/
├── E_rois.valid.json
├── G_queries.valid.json
├── synthetic_slide.<supported-format>
├── H_matches.expected.json
├── config.example.json
└── README.md
```

範例需覆蓋 selected、rejected、skipped、unmapped query、非 reference WSI 與空 ROI case；所有輸出 ROI
數量和 ID 必須與 E 一致。使用合成 slide，不提交 PHI。模型非決定性時定義 score 容許誤差與最終狀態
判定方式。

## 6. README 必填資訊

列出 component version、E/G/H schema version、模型與 prompt/vocabulary revision、Python/framework、
WSI library、CUDA、GPU 數量、最低 VRAM、CPU fallback、checkpoint/template logical path 與 SHA-256、
matching 規則、CLI、Docker build/run、canonical example、效能、限制與錯誤語意。

## 7. 提交檢查

- [ ] H 通過 schema，所有 E ROI 均保留且 selection history 可稽核。
- [ ] E/G case identity、query/ROI/referenceWSI linkage 有測試。
- [ ] clean-machine image 可跑 canonical example，model/prompt 版本可驗證。
- [ ] source、configs、examples、tests、Dockerfile、requirements、README、PREPARATION 已提交。
- [ ] checkpoint/template 只放 `reference/person_d/`；WSI、features、cache、run artifacts 不提交。
- [ ] 根目錄 contract、丙→丁 integration 與完整 pipeline tests 全部通過。
