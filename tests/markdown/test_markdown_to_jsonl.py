from __future__ import annotations

import json

from hrscreening.markdown_to_jsonl import markdown_to_records

SAMPLE = """
BU1234567

男性 / 30歳 / 東京都 出力日時 : 2025/01/01

## ~~コアスキル（活かせる経験・知識・能力）~~
・ SaaS営業

【株式会社ABC】
2020年1月 〜 2022年3月 営業部
・ 新規開拓を担当
・ 成約率向上

BU7654321

女性 / 28歳 / 大阪府 出力日時 : 2025/01/01

【株式会社XYZ】
2023年4月 〜 現在 CS
・ 顧客オンボーディング
""".strip()


def test_markdown_to_records_basic():
    records = list(markdown_to_records(SAMPLE))
    assert len(records) == 2

    first = records[0]
    assert first['candidate_id'] == 'BU1234567'
    assert first['gender'] == '男性'
    assert first['age'] == 30
    assert first['location'].startswith('東京都')
    assert first['skills'] == ['SaaS営業']
    assert first['experiences'][0]['company'] == '株式会社ABC'
    assert first['experiences'][0]['start'] == '2020-01'
    assert first['experiences'][0]['end'] == '2022-03'
    assert '新規開拓を担当' in first['experiences'][0]['bullets'][0]

    second = records[1]
    assert second['candidate_id'] == 'BU7654321'
    assert second['experiences'][0]['end'] is None


DETAIL_SAMPLE = """
BU0000001

男性 / 31歳 / 大阪府 出力日時 : 2025/01/01

## 職務経歴
フリー株式会社（freee株式会社）
パートナー事業部

導入伴走支援 (2023年12月 〜 現在)

・ リード獲得の企画立案
・ 税理士事務所への導入支援

株式会社電通デジタル
ダイレクトアカウントプランニング部
ダイレクトアカウントプランナー (2023年01月 〜 2023年11月)

・ 競合コンペ勝率80%
""".strip()


def test_markdown_to_records_plain_company_lines():
    records = list(markdown_to_records(DETAIL_SAMPLE))
    assert len(records) == 1
    experiences = records[0]['experiences']
    assert len(experiences) == 2

    first = experiences[0]
    assert first['company'] == 'フリー株式会社（freee株式会社）'
    assert first['title'] == 'パートナー事業部'
    assert first['start'] == '2023-12'
    assert first['end'] is None
    assert 'リード獲得の企画立案' in first['bullets']

    second = experiences[1]
    assert second['company'] == '株式会社電通デジタル'
    assert second['title'] == 'ダイレクトアカウントプランニング部'
    assert second['start'] == '2023-01'
    assert second['end'] == '2023-11'
    assert second['bullets'] == ['競合コンペ勝率80%']
