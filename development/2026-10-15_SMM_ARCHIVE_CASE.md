# 住友金属鉱山：手動fact入力の保存確認

基準HEAD4f680d28881ff55b2cab92abaebf1dae8c498654（PR #5）。branch codex/smm-source-archive-case。
対象は1社1資料の入力構造・保存復元のみ。利益予測、実PIT計算、過去E2E再現は受入範囲外。

## 正確な入力由来

入力: development/cases/2026-10-15_SMM_PRETAX_ARCHIVE_REQUEST.json。
抜粋元: 基準HEADのJapanese_Equity_Lab/13_tests/fixtures/smm_pretax_sensitivity_20260810.json。
元fixture生成時bytes SHA256: 7bcf4359576204fed9c63d8877358b290503cb5d9a0659a1ee37685ceb86b5b2。
SourceArtifact.contentはこのfixture JSONの全文文字列であり、原PDF bytesではない。
出典URL: https://www.smm.co.jp/ir/event/teleconference/pdf/2026/260810_telephone.pdf 、19ページ。
本工程では原PDFを再取得・意味照合していない。fixtureの過去の手動読取履歴を現在の独立verifiedへ昇格しない。

schema request hash: 74e7c45b5e684cba30fbaaffdf8a38ca0332fd4a12d0487da84ecd71d9d8c1a2。
生成file bytes SHA256: d435aa11a3cb891674bb8d810845419d18f3fbc6ad24713f95d4b582be0b7e26。
file bytes hashは生成時記録であり、Gitの改行変換後のbytesとの一致保証ではない。typed record hashはcanonical inputを検証する。
構築日時: 2026-10-15 00:28:32 JST（UTC2026-10-14T15:28:32.733746+00:00）。
この日時は今回の構築時刻。資料公開時刻・当時のシステム利用可能時刻ではない。

## 入力と受入条件

直接constructorでCOPPER/GOLD/USDJPYの3disclosureを構築。synthetic test helperは使わない。
32/36/22はJPY_100_MILLION単位の税引前感応度の大きさ。符号・合計・絶対利益を生成しない。
scope、direction、applicability、基準値/範囲/共同適用は未知のまま。
values_verified=False。PRIMARY_OFFICIAL/PRIMARYは出典分類の申告だけで意味の独立確認を示さない。
exact_public_at、retrieved_at、system_available_atはnull、availability UNKNOWN。
normalized_created_atが今回の構築日時でも、実取得・過去PITが確認済みになるわけではない。
record_only=True、sensitivities/shocks空、baseline/coverage/compositionなし。

`python Japanese_Equity_Lab/scripts/profit_impact_preflight.py development/cases/2026-10-15_SMM_PRETAX_ARCHIVE_REQUEST.json`
期待出力はarchive STRUCTURALLY_READY、calculation NOT_EVALUATED。
未検証数値、scope/適用条件、取得時刻、方向、baseline、coverage等の不足が残ることを確認する。
原bytes/semantic truthはNOT_CHECKED、store履歴はNOT_ASSESSED。
構造適合を保存済みや計算成功と呼ばない。

独立検証では固定commitのcaseをrawdecodeし、全field/hash/UNKNOWNを隔離input/result storeへ保存・再読込して一致を確認する。
元bundle bytes不変と既存production/凍結288無変更も確認する。隔離storeでの成功を本番storeとのID/訂正lineage整合証明にはしない。
H0001/Locked Test、マージ/FROZENは実施しない。生成スクリプトとrawlogsはチャットworkspace validationに保持。

独立検証結果は固定SHA確認後に追記する。現時点は製品G1/G5未確認、G2/G3/G4未受入を維持する。

## 独立検証の結果

固定SHA4a21e80bb523df66b01dfd62118141143bb2b66aを設計監査・独立検証が別々に確認した。
独立検証はrawdecode/hash、artifact excerptと固定fixtureの一致、3感応度の値/単位、UNKNOWN/null/Falseを確認。
隔離した新規storeへrecord_onlyで入力とSOURCE_RECORDED結果を保存し、新instanceで読み直した全field/hashが一致。
元case bytes不変、exit0、開始/終了HEAD一致、status clean。指定3fileだけ、production/test/manifestと凍結288パスは無変更。
設計監査も重大findingなし。独立確認のログはチャットworkspace validation/smm-independent-verification.logへ保存。
JSON単独から生成手順や実時計を独立証明したとは主張しない。構築担当のscript/log記録と、独立担当が再検証した入力内容/保存復元を区別する。
本番store ID/訂正history、原PDF、意味の真実性、実会社利益計算、過去PIT、製品Gate受入は未確認のまま。
