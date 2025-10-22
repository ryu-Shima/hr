# HR Screening Engine

候補者レジュメの自動スクリーニングエージェントの実装リポジトリです。  
AGENTS.md の仕様に従い、サイト非依存のコアとサイト依存のアダプタを分離したアーキテクチャで構築します。

## リポジトリ構成（初期）

- `pyproject.toml` — Python パッケージ設定と依存関係
- `src/hrscreening` — コア／アダプタ実装用パッケージ
- `tests/` — pytest ベースのテストコード
- `AGENTS.md` — 仕様および更新ログ
- `candidates.jsonl` — レジュメサンプル
- `Lazuli_CS_JD.md` — 求人票サンプル

## 開発手順

1. `python -m venv .venv && .venv\Scripts\activate`
2. `pip install -e ".[dev]"`
3. `pytest -q`

テスト駆動開発（TDD）でフェーズごとに RED→GREEN→REFACTOR を徹底します。

## CLIの実行例

共通 JSONL 形式の候補者ファイルと求人 JSON を用意して、次のようにスクリプトとして実行できます。

```powershell
py -m hrscreening.cli --candidates data/candidates.jsonl --job data/job.json --output out/results.json
```

`--as-of` オプションで在籍期間計算の基準日（`YYYY-MM` など）を上書き可能です。

### 設定ファイルとログ制御

- `--config config.yaml` で YAML 設定を読み込み、`core.score_weights` や `evaluators.bm25` などを上書きできます（スキーマは Pydantic で検証されます）。
- `--log-level DEBUG` のように指定すると、`structlog` による JSON ログの冗長さを調整できます。
- `--audit-log audit.jsonl` を指定すると、実行ごとの監査情報（LLMペイロード含む）を JSONL として記録します。LLM API は呼び出さない方針です。

サンプル設定:

```yaml
core:
  score_weights:
    bm25_prox: 0.5
    embed_sim: 0.3
evaluators:
  bm25:
    k1: 1.5
    window: 6
    synonyms:
      terraform: ["IaC", "Infrastructure as Code"]
  embed:
    top_k: 5
    synonyms:
      aws: ["Amazon Web Services"]
```


### PDF から JSONL への変換

BizReach の PDF レジュメを直接 JSONL に変換する場合は次の CLI を利用します。

```powershell
py -m hrscreening.cli convert-pdf --pdf content.pdf --output out/candidates.jsonl --markdown out/content.md
```

- `--markdown` を付けると中間の Markdown を保存できます（省略可）
- BizReach 固有の注意書きやアカウント名などのボイラープレート行は自動で除外されます。
- 出力は 1 行 1 候補者の JSON Lines 形式です。

```jsonl
{"provider": "bizreach", "payload": {"candidate_id": "BU1234567", "gender": "男性", ...}}
```
