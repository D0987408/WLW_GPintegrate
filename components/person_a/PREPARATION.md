# 甲（Person A）：Report Decompose／Query Generation 準備與交付

甲負責兩個獨立 executable。目前目錄內只有 contract stub；交付正式版本時應替換內部邏輯，但保留
module 名稱、Unified CLI、單案行為與 schema version。共通規則見專案根目錄 `README.md`。

## 1. Input／output 規格

| Entrypoint | Input | Output |
|---|---|---|
| `components.person_a.report_decompose` | `CaseListInput@1.0`，且每次只含一個 case | `[D] D.DxPairs@2.0` |
| `components.person_a.query_generation` | `[D] D.DxPairs@2.0` + `[F] F.Chunks@2.0` | `[G] G.VisualAttributeQueries@2.0` |

要求：

- D 必須保留 CaseList 的 case/block/stain 身分與 `stains[].filepath`，並產生 schema 合法的
  `structured_report.DxItems`。
- G 必須保留 D 的診斷結構，將 query 寫入各 DxItem 的 `visualAttrQueries`。
- D/F/G 的 `case_id` 必須一致；不得依 `--input` 出現順序判斷 contract。
- `[B] B.ReportTables` 是上游 ingestion manifest；目前甲的 runtime 邊界從已正規化 CaseList 開始。
  若要改回直接讀表格，必須先調整中央 contract 與 pipeline，不可私下擴充 CLI。
- 不得自行建立 `[C]` artifact；目前沒有 canonical `[C]` schema。

Canonical schemas：

- `contracts/schemas/case_list_input.schema.json`
- `contracts/schemas/D_dx_pairs.schema.json`
- `contracts/schemas/F_chunks.schema.json`
- `contracts/schemas/G_visual_attribute_queries.schema.json`

## 2. 打包準備

```text
WLW_GPintegrate/components/person_a/       # 程式、Dockerfile、requirements、文件、非敏感 config
reference/person_a/checkpoint/             # 模型或權重；若沒有模型則可不建立
reference/person_a/template_ref/           # 診斷候選、mapping、vocabulary 等外部參考
run/input/                                 # CaseList、D、F
run/output/                                # D、G、暫存與測試產物
```

- 執行環境只由 `Dockerfile` 與 `requirements.txt` 宣告。
- 超參數、feature flag 與 logical path 放在 `configs/`，不得散落於 Python 常數。
- 模型、reference table、院端資料與 credential 不得進 Git 或 image。
- 外部資產須在 `external-assets.yaml` 列出名稱、revision、SHA-256、授權與預期 mount path。
- runtime 只寫入 sibling `run/`；不得在 component 或 `reference/` 下產生 cache。

## 3. Unified CLI

容器介面：

```bash
component \
  --input /input/case.json \
  --output /output/D_dx_pairs.json \
  --config /config/report_decompose.yaml

component \
  --input /input/D_dx_pairs.json \
  --input /input/F_chunks.json \
  --output /output/G_queries.json \
  --config /config/query_generation.yaml
```

目前專案的 Python／JSON config 等價命令：

```bash
python -m components.person_a.report_decompose \
  --input ../run/input/pipeline/case-001.json \
  --output ../run/output/work/D_dx_pairs.json \
  --config components/person_a/configs/example.json

python -m components.person_a.query_generation \
  --input ../run/output/work/D_dx_pairs.json \
  --input ../run/output/work/F_chunks.json \
  --output ../run/output/work/G_queries.json \
  --config components/person_a/configs/example.json
```

錯誤 input、未知 schema version、case 不一致、reference 缺失或模型錯誤必須非零結束，且不可寫出
部分 D/G。

## 4. Dockerfile／requirements.txt

目前 stub 使用 Python 3.12、CPU 與 standard library。正式交付必須更新 `component.yaml`、Dockerfile、
requirements 與 README，使其共同描述實際 Python、NLP/LLM framework、CPU/GPU 與 RAM/VRAM 需求。

```bash
docker build --no-cache \
  -f components/person_a/Dockerfile \
  -t wlw/person-a:<version> .
```

在 clean machine 執行 D 與 G 兩個 entrypoint；不得因工作站已安裝套件或存在未宣告的 reference file
而成功。若使用 GPU，必須另驗證 CUDA image、driver、framework 與最低 VRAM。

## 5. Canonical examples

至少交付兩組：

```text
components/person_a/examples/
├── report_decompose/
│   ├── case_list.valid.json
│   ├── D_dx_pairs.expected.json
│   ├── config.example.json
│   └── README.md
└── query_generation/
    ├── D_dx_pairs.valid.json
    ├── F_chunks.valid.json
    ├── G_queries.expected.json
    ├── config.example.json
    └── README.md
```

範例不得包含 PHI、院端原始報告或私有 mapping；使用合成內容並確保 expected output 可重現且通過
canonical schema。另至少加入一個 invalid input，驗證元件會 non-zero fail。

## 6. README 必填資訊

甲的 `README.md` 必須列出 component version、D/G contract version、報告／query 模型名稱與 revision、
Python/framework 版本、GPU/VRAM 或 CPU/RAM、checkpoint/reference logical path 與 SHA-256、完整 CLI、
Docker build/run、canonical example、限制與已知失敗條件。若完全不使用模型，需明確寫「無模型」。

## 7. 提交檢查

- [ ] D、G 皆通過 schema，且 D/F/G case identity 一致。
- [ ] `component.yaml`、image tag、artifact `producer` 與 README version 一致。
- [ ] clean-machine build/run 成功，沒有隱含 Conda 或本機路徑依賴。
- [ ] source、configs、examples、tests、Dockerfile、requirements、README、PREPARATION 已提交。
- [ ] 外部資產只放 `reference/person_a/`，並附 manifest；`run/` 產物不提交。
- [ ] 根目錄 contract 與 pipeline tests 全部通過。
