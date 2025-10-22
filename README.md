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

