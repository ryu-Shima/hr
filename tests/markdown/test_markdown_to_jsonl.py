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
    assert 'location' not in first
    assert 'constraints' not in first
    assert first['skills'] == ['SaaS営業']
    assert first['experiences'][0]['company'] == '株式会社ABC'
    first_exp = first['experiences'][0]
    assert first_exp['start'] == '2020-01'
    assert first_exp['end'] == '2022-03'
    assert '新規開拓を担当' in first_exp['summary']
    assert 'bullets' not in first_exp

    second = records[1]
    assert second['candidate_id'] == 'BU7654321'
    second_exp = second['experiences'][0]
    assert second_exp['start'] == '2023-04'
    assert 'end' not in second_exp


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

## 特記事項
希望勤務地：東京都
転居可・フルリモート可
希望年収：600〜800万円
""".strip()


def test_markdown_to_records_plain_company_lines():
    records = list(markdown_to_records(DETAIL_SAMPLE))
    assert len(records) == 1
    experiences = records[0]['experiences']
    assert len(experiences) == 2

    constraints = records[0].get('constraints')
    assert constraints
    assert constraints.get('location') == ['東京都']
    assert constraints.get('can_relocate') is True
    assert constraints.get('remote_ok') is True
    assert records[0]['desired_salary_min_jpy'] == 6000000
    assert records[0]['desired_salary_max_jpy'] == 8000000

    first = experiences[0]
    assert first['company'] == 'フリー株式会社（freee株式会社）'
    assert first['title'] == 'パートナー事業部'
    assert first['start'] == '2023-12'
    assert 'end' not in first
    assert 'リード獲得の企画立案' in first['summary']
    assert 'bullets' not in first

    second = experiences[1]
    assert second['company'] == '株式会社電通デジタル'
    assert second['title'] == 'ダイレクトアカウントプランニング部'
    assert second['start'] == '2023-01'
    assert second['end'] == '2023-11'
    assert '競合コンペ勝率80%' in second['summary']
    assert 'bullets' not in second
