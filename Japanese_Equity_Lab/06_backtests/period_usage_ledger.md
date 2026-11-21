# 検証期間 使用台帳

既存の `LockedTestGate` は `experiment_id` 単位でUnlockを管理する。同じIDの再解錠は
拒否されるが、**別の仮説IDで同じ期間を見直すこと**は防げない。同一データに対して
仮説を何十も当てれば、偶然成績の良いものが現れる。この台帳はその穴を埋める。

自動化しない。手で1行追記する。仕組みを作るより、使用の事実が1箇所に集まっている
ことのほうが重要で、実行されない自動チェックより実行される手書きのほうが機能する。

## ルール

1. 期間を使ったら、その日のうちにこのファイルへ1行追記する
2. 形式: `日付 | 仮説ID | 期間 | 用途 | データ | 根拠`
   - 用途: `TRAIN` / `VALIDATION` / `LOCKED`
   - データ: `REAL`(実市場データ) / `FIXTURE`(合成・固定データ)
3. **`LOCKED` かつ `REAL` の期間は、別の仮説IDで二度と使わない。** 一度見た最終検証
   期間は燃え尽きたものとして扱う
4. 新しい事前登録の前に、この表の `LOCKED` 行と期間が重ならないことを確認する
5. 既存行は書き換えない。訂正が要る場合は新しい行を追記して理由を書く

`FIXTURE` の行は実市場データを観測していないので、同じ期間を `REAL` で使うことを
妨げない。ただし同じ仮説で合成→実データと進む場合、合成側で得た知見が実データの
設計に影響している可能性は残る。その点は仮説側で申告する。

## 使用済み期間

| 日付 | 仮説ID | 期間 | 用途 | データ | 根拠 |
| --- | --- | --- | --- | --- | --- |
| 2026-08-19 | H0001 (PREREG0001) | 2026-01-05 / 2026-03-04 | TRAIN | FIXTURE | `BT_PHASE5_V1_H0001_SMOKE_V2_TRAIN` |
| 2026-08-19 | H0001 (PREREG0001) | 2026-03-05 / 2026-05-01 | VALIDATION | FIXTURE | `BT_PHASE5_V1_H0001_SMOKE_V2_VALIDATION` |
| 2026-08-19 | H0001 (PREREG0001) | 2026-05-05 / 2026-07-03 | LOCKED | FIXTURE | `locked_test_audit.jsonl`、解錠 11:28:41Z、actor "Main Claude (Phase5 v1 Round)" |
| 2026-08-19 | H0001 (PREREG0001_R1) | 2022-01-04 / 2023-12-29 | TRAIN | REAL | `BT_PHASE5_V1_1_H0001_R1_TRAIN` |
| 2026-08-19 | H0001 (PREREG0001_R1) | 2024-01-04 / 2024-12-30 | VALIDATION | REAL | `BT_PHASE5_V1_1_H0001_R1_VALIDATION` |
| 2026-08-19 | H0001 (PREREG0001_R1) | **2025-01-06 / 2025-12-30** | **LOCKED** | **REAL** | `locked_test_audit_real.jsonl`、解錠 13:26:58Z、actor "user" |

出典: `06_backtests/preregistrations.jsonl`、`locked_test_audit.jsonl`、
`locked_test_audit_real.jsonl`、`experiment_registry.jsonl`。2026-11-21に遡って記録。

`PREREG0001` が `FIXTURE` であることは
`01_data/raw/fixture/SNAP_BT_PHASE5_V1_H0001_SMOKE_V2_TEST_equity_bars.manifest.json`
の `source = fixture` / `endpoint = fixture:equity_bars` で確認した。

`PREREG0001_R1` の実データSnapshotはGit管理外で、本リポジトリからは原本を再確認
できない(W0の未解決事項と同じ制約)。使用の事実は解錠記録から確定できるが、
取得内容そのものの照合はUNKNOWNのまま。

## 現在の残余

- **2025年は実データで燃え尽きている。** 新しい仮説のLocked Testに使えない
- 2022〜2024年は実データでTRAIN/VALIDATIONに使用済み。Locked Testには適さない
- 2026年は `FIXTURE` でのみ使用。実市場データとしては未観測
- 2021年以前は未使用

## 次の仮説のLocked Test期間について

**未決。** 候補と論点のみ記録し、ここでは選ばない。

- **2026年**: 実データ未観測。ただし直近年であり、研究外の場面(市況確認、個別銘柄の
  閲覧)で目にしている可能性が高い。「見ていない」と言い切れない
- **2021年以前**: 未使用で明快。ただし現在と市場構造が異なり、結果の外挿可能性が下がる
- **将来期間(2027年以降)**: 真の前向き検証。最も強いが、待つ必要がある

選定は事前登録の一部として、理由とともに記録してから行う。結果を見てから期間を
変えることはしない。
