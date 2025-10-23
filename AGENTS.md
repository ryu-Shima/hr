# AGENTS.md

## 1. 概要

本システムは、**候補者レジュメの自動スクリーニングエージェント**を実装する。
目的は一次選考の自動化により工数を削減し、**定量的かつ再現性の高い評価**を実現すること。

重要設計方針:

* **サイト非依存（コア）** と **サイト依存（アダプタ）** を厳密に分離する。
* 各サイト（BizReach, Green, LinkedIn, Wantedly, Doda, リクナビNEXT 等）は共通I/Fを持つ独立モジュールとして追加可能。
* **SOLID原則**に従い、変更容易性・拡張性を担保する。


## 【あなた（ChatGPT）の回答方針／出力ルール】


- ローカル開発環境は **Windows**。
- コミット・プッシュはあなたの判断で自由に行ってください。
- コミットを行うごとに修正や更新された仕様や機能を、最新の仕様としてAgents.md に反映してください。
- コミットメッセージは**日本語**で。

## MCPサーバー

このリポジトリでは以下の MCP サーバーが利用可能です。用途に応じて積極的に活用してください。

- **Serena (`serena`)** — `uvx --from git+https://github.com/oraios/serena serena-mcp-server --context ide-assistant`
  - リポジトリ内のファイル/シンボル探索、TODO 管理、構造化された情報取得に使用。
  - 大規模な検索やシンボル解析が必要なときは shell の `rg` より先に利用する。
- **GitHub (`github`)** — `https://api.githubcopilot.com/mcp/`
  - 通知確認、Issue/Pull Request 操作、Actions 状況の取得など GitHub 連携に使用。
  - デプロイ前後の確認やレビューフィードバックの収集にも活用する。
- **Vercel (`Vercel`)** — `https://mcp.vercel.com`
  - Cloudflare Pages とは別に Vercel 連携が必要な検証時に利用（デプロイ設定やログ確認など）。
- **Playwright (`Playwright`)** — `npx -y @playwright/mcp@latest`
  - ブラウザ E2E 動作確認やスクリーンショット取得が必要なときに使用。
- **Chrome DevTools (`Chrome DevTools`)** — `npx chrome-devtools-mcp@latest`
  - `npm run dev` 実行後は `http://localhost:<ポート>` (初期値 3000) にアクセスして初回コンパイルを発火させ、DevTools でコンソール/ネットワークログを確認する。
  - ローカル検証は必ず `npm run dev --workspace apps/frontend -- --turbo` でサーバーを起動し、ターミナルに表示されたポート（既定3000、競合時は3001以降）を参照する。
  - サーバー起動後は`✓ Starting... ✓ Ready` のログが表示されたら、必ず別ターミナルで `npx chrome-devtools-mcp@latest --headless --isolated --browserUrl http://localhost:<ポート>` で Chrome DevTools MCP へ接続し、コンソール/ネットワークログや UI を確認する。
  - 上記手順（devサーバー起動→ポート確認→Chrome DevTools MCP接続）以外でのローカル動作検証は禁止。作業終了時は dev サーバーと MCP を必ず停止し、残存ログを整理する。
  - ポートが競合した場合は Next.js が自動的に 3001 以降へ切り替えるため、ターミナルに表示されたポート番号で DevTools の接続先を更新する。作業終了時は `Ctrl+C` で dev サーバーを停止してポートを解放する。

各 MCP サーバーは 自動接続される。タスクに応じて必要なサーバーを呼び出すこと。

## Serena MCP使用ガイドライン
- **複雑なコード解析**や**アーキテクチャ理解**が必要な場面では積極的にSerenaを使用する
- **Serena推奨場面**：
  - コードベース全体の構造理解
  - シンボル間の参照関係調査
  - クラス・関数・変数の使用箇所特定
  - ファイル間の依存関係分析
  - 大規模リファクタリングの影響範囲調査
  - 設計パターンの実装箇所探索
  - バグの原因となる関連コード特定
- **通常ツール推奨場面**：
  - 単純なファイル読み込み・編集
  - 既知のファイル・関数への直接的な変更
  - シンプルな文字列検索・置換
- Serena MCPの機能を活用して効率的で正確なコード分析を心がける

---



---

## 2. スコープ

**対象**: 求人サイト（BizReach等）から取得した候補者レジュメ（PDF/CSV/JSON）。
**出力**: 候補者ごとの **サイト非依存JSON** ＋ **スクリーニング結果（CSV/JSON）**。
**候補者のレジュメサンプル**:hr\candidates.jsonlに記載。
**求人の募集要項**: hr\Lazuli_CS_JD.mdに記載。




---

## 3. アーキテクチャ設計

### 3.1 構造概要

```
入力 (PDF/CSV/JSON)
 ├─ CLIヘルパー …… `convert-pdf`（pymupdf4llm で Markdown 抽出→JSONL 変換、BizReach 固有ヘッダー除去）
 ├─ Adapter 層（サイト依存）…… BizReachAdapter（JSONL を CandidateProfile に正規化）
 ├─ Core 層（サイト非依存）…… ScreeningCore（Evaluator、ハードゲート、LLM ペイロード生成）
 ├─ Pipeline 層 …… Candidate/Job Loader、AuditLogger、structlog による監査ログ
 └─ Config 層 …… Pydantic 設定（YAML 検証）と dependency-injector で動的注入
```

---

## 4. SOLID 原則適用

### 4.1 SRP（単一責任の原則）

各クラス／モジュールは明確な責務を持つ。

| クラス                   | 責務                                    |
| --------------------- | ------------------------------------- |
| `BizReachAdapter`     | BizReach JSON(L) を CandidateProfile に変換 |
| `CandidateLoader`     | JSONL 読み込みと検証（部分成功・エラー記録） |
| `JobLoader`           | JD JSON の読み込み・検証                     |
| `TenureEvaluator`     | 在籍期間計算・リスク評価（high/medium/low）   |
| `SalaryEvaluator`     | 希望年収と求人年収のマッチング評価（ギャップ算出） |
| `JDMatcher`           | BM25 / TF-IDF 類似のキーワード評価            |
| `ScreeningCore`       | Evaluator 統合・ハードゲート・LLMペイロード生成 |
| `AuditLogger`         | structlog 形式で監査ログ（JSONL）を出力        |
| `CLI (run/convert-pdf)` | パイプライン実行・PDF変換のエントリポイント         |

---

### 4.2 OCP（オープン／クローズド原則）

* 新しいサイト（例: Wantedly）を追加する場合は、新しい `WantedlyAdapter` クラスを作成するだけで済む。
* スクリーニング基準の追加は、新しい `Evaluator` クラスを追加することで対応可能。
  → 既存コードの修正は不要。

---

### 4.3 LSP（リスコフ置換原則）

* すべてのアダプタは `ResumeAdapter` インターフェースを実装。
  Core は Adapter 実装の違いを意識せず処理できる。

```python
class ResumeAdapter(Protocol):
    provider: str
    def can_handle(self, blob: bytes | str, metadata: dict) -> bool: ...
    def split_candidates(self, text: str) -> list[str]: ...
    def parse_candidate(self, section: str) -> dict: ...
```

---

### 4.4 ISP（インターフェース分離の原則）

* 各評価器（Evaluator）は小さな独立I/Fを持つ。

```python
class Evaluator(Protocol):
    def evaluate(self, candidate: dict, context: dict) -> dict: ...
```

→ 例えば `TenureEvaluator` と `SalaryEvaluator` は別実装。
`ScreeningCore` は複数Evaluatorを順に実行し、スコアを集約。

---

### 4.5 DIP（依存性逆転の原則）

* `ScreeningCore` は具象クラスではなく抽象インターフェース (`Evaluator`, `Adapter`) に依存。
* 依存関係は `ConfigManager` によって動的に注入される。

---

## 5. データスキーマ（サイト非依存）
### 5.1 BizReach PDF 抽出項目

- ビズリーチのレジュメ PDF を `convert-pdf` コマンドで Markdown→JSONL に変換する際は、以下の見出しのみを抽出対象とする。
  - 職務経歴概要内: `所属企業一覧`、`直近の年収`、`経験職種`、`経験業種`、`マネジメント経験`、`海外勤務経験`
  - 学歴/語学 内: `学歴`、`語学力`、`海外留学経験`
  - `職務要約` のテキスト全文
  - `コアスキル（活かせる経験・知識・能力）`
  - 職務経歴内の各社について `企業名`、`期間`、`経験職種`、`業務内容のテキスト全文`
  - `学歴`、`表彰`、`語学・資格`、`特記事項`、`フリーテキスト`
- 上記以外の項目はキーとして作成せず、必要なら `notes` もしくは `provider_raw` に保持する。
- これらは BizReach 固有の取り扱いであり、他媒体への転用や共通ロジック化は禁止。


```json
{
  "provider": "string",
  "provider_ids": {"primary": null, "others": {}},
  "name": null,
  "gender": null,
  "age": null,
  "location": null,
  "contact": {"email": null, "phone": null},
  "education": [{"school": "", "major": "", "degree": null, "start": null, "end": "YYYY-MM"}],
  "experiences": [{"company": "", "title": "", "start": "YYYY-MM", "end": null, "employment_type": null, "summary": ""}],
  "skills": [],
  "languages": [{"language": "日本語", "level": "ネイティブ"}],
  "current_salary_min_jpy": null,
  "current_salary_max_jpy": null,
  "desired_salary_min_jpy": null,
  "desired_salary_max_jpy": null,
  "management_experience": {"has_experience": false, "team_size_range": null},
  "awards": [],
  "certifications": [],
  "notes": null,
  "provider_raw": {"text": null, "fields": {}}
}
```

※ 上記スキーマは Pydantic v2 で `CandidateProfile` / `JobDescription` として実装し、CLI・パイプライン経由で常にバリデーションされる。

---

## 6. アダプタ実装例

### BizReachAdapter

* 候補者区切り: `BU[0-9]{7}`
* 固有ID: 最初の `BU[0-9]{7}`
* 年収表記: `([0-9]{2,4})[–〜-]([0-9]{2,4})万円` → ×10,000 JPY
* 語学レベル正規化: `{ビジネス→Business, 日常会話→Conversational}`
* `provider_raw` に原文保持

```python
class BizReachAdapter(ResumeAdapter):
    provider = "bizreach"
    def can_handle(...): ...
    def split_candidates(...): ...
    def parse_candidate(...): ...
```

---

## 7. スクリーニング基準（Evaluatorクラス）

### TenureEvaluator

* 各社在籍期間（月）を算出。
* 平均 < 18ヶ月 かつ直近3社中2社 < 12ヶ月 → 除外。
* 契約/フリーランスは平均 >= 12ヶ月で通過。

### SalaryEvaluator

* 希望年収と求人想定年収が ±10%内で重なる場合に通過。

### JDMatcher

* `must_keywords`: 全一致必須。
* `nice_keywords`: ヒットごとに


## 8. 実装手順（TDD対応版）

方針: テスト駆動開発（TDD） に基づき、最小限の失敗テスト→実装→リファクタを小刻みに回す。全フェーズで「RED→GREEN→REFACTOR」を徹底する。

---

### フェーズ0: 初期セットアップ

---

### フェーズ1: スキーマ定義（RED→GREEN）

---

### フェーズ2: ScreeningCore（DIP適用）

---

### フェーズ3: Evaluator群（ISP遵守）

- TenureEvaluator  
- SalaryEvaluator  
- JDMatcher  

---

### フェーズ4: Adapter実装（OCP/LSP）

- BizReachAdapter  

---

### フェーズ5: I/O + CLI（SRP）

---

### フェーズ6: 統合テスト & E2E検証

---

### 定義済みコミット規約（TDD版）

- `test`: テスト作成（RED）  
- `feat`: 実装（GREEN）  
- `refactor`: 構造改善（REFACTOR）  

---

### DoD（Doneの定義）

- 全テスト緑 (`pytest -q`)  
- カバレッジ > 85%  
- 主要Evaluator/Adapterがモックで独立テスト可  
- `AGENTS.md` に常に最新仕様が反映  
- 監査ログに実行トレースIDが出力


## 9. 使用ライブラリ方針

本プロジェクトでは、**TDD対応・Windows環境・SOLID原則順守・サイト非依存アーキテクチャ**を前提に、以下のライブラリを採用する。

### 9.1 採用方針

- **コア層（サイト非依存）** と **アダプタ層（サイト依存）** を厳密に分離。
- **テスト駆動開発（TDD）** と **依存性逆転（DIP）** を実現するため、依存注入・プラグイン設計を採用。
- **日本語PDF解析** および **JDマッチング** に強い形態素解析・ファジーマッチライブラリを使用。
- **速度・型安全性・再現性** を重視し、全ライブラリは Windows で安定動作確認済み。

---

### 9.2 使用ライブラリ一覧

| 区分 | ライブラリ | 主な用途 |
|------|-------------|-----------|
| **スキーマ / 検証** | `pydantic v2` | サイト非依存スキーマ定義と検証 |
| **JSON/CSV I/O** | `orjson`, `pandas` | 結果出力・レジュメ入出力 |
| **日付・期間処理** | `python-dateutil`, `pendulum` | 在籍期間算出・時系列正規化 |
| **日本語処理** | `SudachiPy`, `sudachidict-core` | JDマッチングの形態素解析 |
| **キーワードマッチ** | `rapidfuzz` | ファジー一致によるスコア算出 |
| **監査ログ** | `structlog` | トレースID付きJSON構造ログ |
| **依存性注入** | `dependency-injector` | ScreeningCoreへのEvaluator注入 |
| **プラグイン管理** | `pluggy` | Adapter/Evaluator拡張（OCP/LSP） |
| **CLI/UX** | `typer`, `rich` | CLI実装・色付き出力 |
| **PDF抽出（BizReach等）** | `pymupdf`, `pdfplumber`, `pypdf` | PDFからテキスト/表抽出 |
| **CSV/Excel処理** | `pandas`, `openpyxl` | サイト提供データの読み込み |
| **正規表現解析** | `regex` | 年収・ID等の高度な文字列抽出 |
| **テスト/TDD** | `pytest`, `pytest-cov`, `hypothesis` | RED→GREEN→REFACTOR駆動 |
| **静的解析/品質** | `ruff`, `black`, `mypy`, `pre-commit` | コード品質維持とCI前検証 |
| **ML/Embedding拡張**（任意） | `scikit-learn`, `sentence-transformers` | 将来的なJD類似度評価 |
| **E2E/UI検証**（任意） | `playwright` | MCP連携ブラウザE2E検証 |



##  JDとのマッチング実装要件: 手法1 ルール/BM25近接 + 手法2 埋め込み類似度 → LLM再ランク（サイト非依存コア）

> 本要件は **サイト非依存（コア）** の実装仕様。BizReach/Green/LinkedIn 等の**アダプタ**は、ここで定義する共通 JSON を出力すること。

---

## 0. 用語と範囲

* JD: Job Description（求人票）
* 候補者プロフィール: 解析済みレジュメ（アダプタが共通スキーマで出力）
* 手法1: ルール & BM25 近接スコア
* 手法2: 埋め込み類似度（コサイン）
* LLM再ランク: 手法1/手法2のスコアと根拠を **WEB版ChatGPT** に渡し、最終判断（pass/borderline/reject）を返す

---

## 1. アーキテクチャ（コア/アダプタ分離）

* アダプタ層（サイト依存）

  * レジュメ PDF/HTML 等を解析し、共通スキーマ `CandidateProfile` を生成
  * サイト固有の項目名・構造をコア用に正規化（職歴箇条書き、期間、スキル、タイトル）
* コア層（サイト非依存）

  * 前処理（正規化/辞書/オントロジ/期間推定）
  * 手法1: ルール & BM25 近接
  * 手法2: 埋め込み類似度
  * スコア融合・閾値適用・ゲート判定
  * LLM再ランク入出力のパッケージング

---

## 2. 入力スキーマ（アダプタ → コア）

### 2.1 JD（サイト非依存）

```json
{
  "job_id": "JD-123",
  "locale": "ja-JP",
  "role_titles": ["SRE", "Site Reliability Engineer"],
  "requirements_text": [
    "Terraformを用いたIaC構築経験",
    "AWS上での運用・監視経験",
    "オンコール対応"
  ],
  "key_phrases": ["Terraform", "AWS", "IaC", "EKS", "監視", "オンコール"],
  "constraints": {
    "language": ["ja"],
    "location": ["Tokyo"],
    "visa": "required",
    "salary_range": { "min_jpy": 7000000, "max_jpy": 12000000 }
  }
}
```

### 2.2 CandidateProfile（サイト非依存）

```json
{
  "candidate_id": "C-456",
  "locale": "ja-JP",
  "titles": ["Site Reliability Engineer", "Infra Engineer"],
  "experiences": [
    {
      "company": "ACME",
      "title": "SRE",
      "start": "2023-01",
      "end": "2025-09",
      "bullets": [
        "TerraformでAWS基盤をIaC化し、EKSを構築",
        "Prometheus/Grafanaで監視を設計・運用"
      ]
    }
  ],
  "skills_agg": {
    "Terraform": { "years": 2.5, "last_used": "2025-06" },
    "AWS": { "years": 3.0, "last_used": "2025-09" },
    "Monitoring": { "years": 3.0, "last_used": "2025-09" },
    "Python": { "years": 1.0, "last_used": "2024-12" }
  },
  "constraints": { "language": ["ja"], "location": ["Tokyo"], "visa": "ok" }
}
```

---

## 3. 前処理・正規化（コア）

* テキスト正規化: 記号・全半角・表記ゆれ統一、活用形吸収、スペルバリアント（TS⇔TypeScript 等）
* 形態素解析: 日本語は分かち書き、英語はステミング/レmmatize
* 同義語辞書/オントロジ: カノニカルスキル化と近縁関係（例: React ↔ Next.js、Terraform ↔ IaC）
* 期間推定: スキルごとに `years` と `last_used(YYYY-MM)` を保持
* セクション重み: bullets > titles > summary（例: 1.0, 0.6, 0.4）
* 最近性重み: `w_recency = exp(-λ * months_since_last_used)` を各ヒットに乗算

---

## 4. 手法1: ルール & BM25 近接スコア

### 4.1 入力

* JD の `requirements_text[]` と `key_phrases[]`
* 候補者の `experiences[].bullets[]` と `titles[]`

### 4.2 クエリ構築

* 重要語句をブースト: 必須級 `^2.0`、推奨 `^1.2`（設定可能）
* フレーズ一致と語近接: 窓幅 `window = 8` 語以内の共起にボーナス
* 同義語展開: 辞書/オントロジでクエリ拡張（例: IaC→Terraform/CloudFormation）

### 4.3 スコアリング

* 本体: BM25（`k1`, `b` は設定値。例: `k1=1.2`, `b=0.75`）
* 近接補正: `proximity_bonus = α / (1 + distance)`（距離は語間隔、αは例 0.2）
* セクション重み: bullets=1.0, titles=0.6, summary=0.4 を乗算
* 最近性重み: ヒット単位で `w_recency` を乗算
* タイトル一致加点: 職種タイトルの編集距離/埋め込み類似で `title_bonus` を付与
* 集計: 要件文ごとの上位ヒットを集約し、候補者全体の `bm25_prox` を算出

### 4.4 出力（手法1ステージ）

```json
{
  "candidate_id": "C-456",
  "job_id": "JD-123",
  "method": "bm25_proximity",
  "scores": {
    "bm25_prox": 1.35,
    "title_bonus": 0.10
  },
  "hits": [
    {
      "jd_text": "Terraformを用いたIaC構築経験",
      "resume_text": "TerraformでAWS基盤をIaC化し、EKSを構築",
      "bm25": 8.2,
      "proximity_bonus": 0.18,
      "section": "bullets",
      "recency_weight": 0.88
    }
  ],
  "metadata": { "k1": 1.2, "b": 0.75, "alpha_proximity": 0.2, "window": 8 }
}
```

---

## 5. 手法2: 埋め込み類似度（行列集計）

### 5.1 入力

* JD の `requirements_text[]`
* 候補者の `experiences[].bullets[]`（必要に応じて `titles[]` も含める）

### 5.2 埋め込み

* EmbeddingProvider インターフェース（プラガブル）

  * `embed_texts(texts: string[], lang_hint?: string) -> float[][]`
  * モデル名・バージョンをメタデータとして必ずログ化

### 5.3 類似度計算と集計

* 類似度: コサイン類似度
* 行列 `M`: `[len(JD文)] x [len(候補者文)]`
* 近接重み: 直近月数 `m` による `w_recency`
* セクション重み: bullets=1.0, titles=0.6, summary=0.4
* 集計: JD文ごと Top-k（例 k=3）の最大/平均プール → 文スコア平均で `embed_sim ∈ [0,1]`
* タイトル補正: タイトル埋め込みの類似 `sim_title` を加点

### 5.4 出力（手法2ステージ）

```json
{
  "candidate_id": "C-456",
  "job_id": "JD-123",
  "method": "embed_similarity",
  "scores": { "embed_sim": 0.78, "sim_title": 0.65 },
  "evidence_pairs": [
    {
      "jd_text": "Terraformを用いたIaC構築経験",
      "resume_text": "TerraformでAWS基盤をIaC化し、EKSを構築",
      "similarity": 0.92,
      "recency_weight": 0.88,
      "section": "bullets"
    }
  ],
  "metadata": { "model": "embedding-model-name@vX.Y", "k": 3, "lambda_recency": 0.05 }
}
```

---

## 6. スコア融合とゲート

* ハードゲート: 言語/勤務地/ビザ/給与のミスマッチは事前に除外または減点
* 推奨合成例:

  * `pre_llm_score = w1*bm25_prox + w2*embed_sim + w3*sim_title + w4*title_bonus`
  * 既定: `w1=0.45, w2=0.40, w3=0.10, w4=0.05`（運用で調整）
* 合否境界:

  * `τ_pass = 0.80` 以上 → 一次通過候補
  * `τ_borderline = 0.65` 以上 `τ_pass` 未満 → LLM判断を重視

---

## 7. LLM再ランク仕様（WEB版ChatGPTに貼り付け）

### 7.1 System（固定）

```
You are a hiring JD–resume reranker. Return output in STRICT JSON only.
Decide: pass | borderline | reject.
Short, code-style reasons (UPPER_SNAKE_CASE). Include 2–4 evidence quotes (<=160 chars each).
No commentary, no markdown, no extra keys.
Temperature = 0.
```

### 7.2 User（入力ペイロード）

* 次の JSON をそのまま貼り付ける（例）

```json
{
  "job_id": "JD-123",
  "candidate_id": "C-456",
  "jd": {
    "role_titles": ["SRE", "Site Reliability Engineer"],
    "requirements_top": [
      "Terraformを用いたIaC構築経験",
      "AWS上での運用・監視経験",
      "オンコール対応"
    ],
    "constraints": { "language": ["ja"], "location": ["Tokyo"], "visa": "required" }
  },
  "candidate_summary": {
    "titles": ["Site Reliability Engineer"],
    "skills_agg_top": [
      { "name": "Terraform", "years": 2.5, "last_used": "2025-06" },
      { "name": "AWS", "years": 3.0, "last_used": "2025-09" }
    ]
  },
  "method1_bm25": {
    "bm25_prox": 1.35,
    "title_bonus": 0.10,
    "hits_top": [
      { "jd_text": "Terraformを用いたIaC構築経験", "resume_text": "TerraformでAWS基盤をIaC化し、EKSを構築", "bm25": 8.2 }
    ]
  },
  "method2_embed": {
    "embed_sim": 0.78,
    "sim_title": 0.65,
    "evidence_pairs_top": [
      { "jd_text": "Terraformを用いたIaC構築経験", "resume_text": "TerraformでAWS基盤をIaC化し、EKSを構築", "similarity": 0.92 }
    ]
  },
  "pre_llm_score": 0.82,
  "penalties": { "location_ok": true, "visa_ok": true, "language_ok": true }
}
```

### 7.3 期待する LLM 出力 JSON スキーマ

```json
{
  "decision": "pass|borderline|reject",
  "final_score_hint": 0.0,
  "reasons": ["KEY_PHRASE_HIT", "TOKEN_NEAR_MATCH", "TITLE_MATCH"],
  "evidence": [
    "TerraformでAWS基盤をIaC化し、EKSを構築",
    "Prometheus/Grafanaで監視を設計・運用"
  ]
}
```

* `final_score_hint`: 任意の補正（0–1）。未使用なら 0 でもよい

---

## 8. 設定・閾値（デフォルト案/可変）

* λ（最近性減衰）: 0.05
* α（近接ボーナス）: 0.2
* window（語近接）: 8
* セクション重み: bullets=1.0 / titles=0.6 / summary=0.4
* k（Top-k）: 3
* 合格境界: `τ_pass = 0.80`, `τ_borderline = 0.65`
* BM25: `k1=1.2`, `b=0.75`
* ScreeningCore 合成重み（例）: `bm25_prox=0.40`, `embed_sim=0.35`, `sim_title=0.08`, `title_bonus=0.07`, `tenure_pass=0.04`, `salary_pass=0.04`, `jd_pass=0.02`

---

## 9. ログ・監査・再現性

* structlog で JSON 監査ログを出力し、必要に応じて `--audit-log` で永続化
* すべての実行で以下を記録

  * 入力 JSON ハッシュ、前処理辞書/オントロジのバージョン
  * 埋め込みモデル名/バージョン、BM25 パラメータ、Top-k、λ/α/重み/閾値
  * 手法1の上位ヒット（JD文 ↔ レジュメ文、スコア、セクション、最近性）
  * 手法2の上位ペア（類似度、引用テキスト）
* 乱数はシード固定（再現性）

---

## 10. 品質評価（オフライン）

* 指標: Precision/Recall/F1、PR-AUC、NDCG@k、Top-k 採択率
* 校正: `τ_pass`/`τ_borderline` と重み `w1..w4` のグリッド探索


---

## 11. エッジケース

* JD が抽象的: キーフレーズ抽出で代表語を補完、オントロジでクエリ拡張を強める
* 長期ブランク: 最近性重みの floor を設定（例 0.5）
* マルチロール履歴: 直近ロールを優先、古いロールは減衰
* 同義語過多でノイズ: 展開深さを制限、IDF 閾値で低情報語を除外

---

## 12. 実装状況（2025-02-15）

- Python パッケージ構成を `pyproject.toml`（`src/` 配下モジュール、`tests/`）で整備。`pdf` / `nlp` / `ml` オプション依存を分離。
- Pydantic v2 ベースの `CandidateProfile` / `JobDescription` スキーマと付随サブモデルを実装（`src/hrscreening/schemas/`）。
- スキーマ挙動を検証する pytest を追加（`tests/schemas/test_candidate_profile.py`）。デフォルト値とバリデーションの RED→GREEN を確認済み。
- `ScreeningCore` を実装し、Evaluator 結果の集約・重み付け・ハードゲート判定（言語/勤務地/ビザ/給与）と意思決定ロジックを整備（`src/hrscreening/core/screening.py`）。
- コアの TDD テストを追加（`tests/core/test_screening_core.py`）し、重み付け計算とハードゲート動作を確認。
- TenureEvaluator / SalaryEvaluator / JDMatcher を実装し、安定勤務・給与マッチ・キーワード網羅率の評価ロジックを追加（`src/hrscreening/core/evaluators/`）。
- 各 Evaluator の単体テストを整備（`tests/core/test_tenure_evaluator.py`、`test_salary_evaluator.py`、`test_jd_matcher.py`）。
- ScreeningCore のデフォルト重みを拡張し、`tenure_pass` / `salary_pass` / `jd_pass` を事前スコアに寄与させるよう更新。
- BizReach 向け JSON アダプタを仮実装（`src/hrscreening/adapters/bizreach.py`）し、JSONL 入力から `CandidateProfile` へ正規化。
- 依存性コンテナとパイプライン（`src/hrscreening/container.py`、`src/hrscreening/pipeline.py`）を整備し、CLI からエンドツーエンド実行可能にした。
- Typer ベースの CLI を追加（`src/hrscreening/cli.py`）し、`tests/integration/test_cli_pipeline.py` で I/O を含む統合テストを作成。
- 現状の対応サイトは BizReach のみとし、出力フォーマットも JSON のみをサポート（将来的に拡張予定）。
- 手法1（BM25＋近接）/手法2（TF-IDFコサイン近似）の Evaluator を実装し、ヒット証跡とタイトルボーナスを含むスコアリングを追加（`src/hrscreening/core/evaluators/bm25_proximity.py`, `embedding_similarity.py`）。
- LLM再ランク用ペイロード生成と structlog ベースの監査ログをパイプラインに組み込み、CLI から `--config` / `--log-level` / `--audit-log` を指定できるように拡張（`src/hrscreening/pipeline.py`, `src/hrscreening/cli.py`, `src/hrscreening/logging.py`, `src/hrscreening/llm.py`）。
- LLM API は有償のため **実際には呼び出さない** 方針とし、生成したペイロードは監査ログやオフライン評価でのみ活用する。
- 候補者/求人入力のバリデーションと部分成功ハンドリングを実装、出力 JSON にメタ情報（処理エラー・タイムスタンプ・バージョン）を付与。
- YAML 設定は Pydantic スキーマで検証し、BM25/Embedding Evaluator にシノニム拡張やパラメータ調整を設定化。
- PDF レジュメを `convert-pdf` コマンドで Markdown 抽出→JSONL 変換できるよう整備。余計な注意書きは除去し、最低限の候補者スキーマに整形。
- BizReach PDF 変換で `職務経歴` セクションから会社名・在籍期間（start/end）・所属部署（title）・業務内容全文（summary）を正規化し、複数行に分割された箇条書きも連結したうえで `CandidateProfile.experiences` を常に充足するよう改修（`src/hrscreening/markdown_to_jsonl.py`、`tests/markdown/test_markdown_to_jsonl.py`）。
- 日本語・ビザのハードゲートを撤廃し、勤務地条件を緩和して給与ゲート詳細を結果 JSON と監査ログに記録、JD キーワード評価をヒット数に応じた加点方式へ移行（`src/hrscreening/markdown_to_jsonl.py`、`src/hrscreening/core/screening.py`、`src/hrscreening/core/evaluators/jd_matcher.py`、`src/hrscreening/pipeline.py`）。

