# 手動資料の入力確認仕様

基準HEAD fba60cbc42b76021000a24663dce34fd51b13aea。実装branch codex/profit-impact-preflight。
ユーザーの自律開発許可に基づく小工程。既存凍結288ファイルは変更しない。マージ/FROZENなし。

## 目的と入力

単一のProfitImpactRequest保存payload JSONを読み、archive入力契約の適合と計算上の検出済み不足条件を分けて示す。
原資料の取得・parse・自動正規化・利益計算・予測接続は行わない。入力不足を補完しない。
既存store._decodeをwrapperから再利用し、strict fields、raw record hashをconstructor前に検証、validate_treeを実施。
JSON duplicate keyとNaN/Infinityはparse時に拒否。日付/時刻/Decimalは保存形式どおり文字列、tupleは配列。
既存private decoderへの依存は基準SHAで固定し、既存store自体を改変しない。

## 出力契約

入力integrity、source_archive_readiness、calculation_readiness、未検証claimを分離する。
archiveはSTRUCTURALLY_READY/BLOCKED。source/artifactの存在・正確な参照・会社/期/版一致・record_onlyへの計算入力混在を確認。
calculationはNOT_EVALUATED固定。見つかった不足条件をARCHIVE/CALCULATION/SIGNED_DELTA/TARGET/HISTORICAL_REPLAY等のscopeとfield/record IDに結び付け、決定的順序で表示。
全不足検出やcalculator同等性を保証しない。検査項目が空でも計算受入済みとしない。
方向未知は符号付き結果の不足であり、影響額の大きさの可否とは区別する。baseline欠落はtarget条件。
正確な公開時刻が未知であることはhistorical claimの限界とし、実取得時刻が揃うSYSTEM_OBSERVEDと混同しない。
original_source_bytes_verified=NOT_CHECKED。caller excerptのhash整合はPDF原bytesの証明ではない。
authority/values_verifiedはcaller申告として扱い、意味の独立確認済みとしない。未知値とlimitationsを保持。
単一payloadでは過去store内ID衝突・訂正parent存在をNOT_ASSESSEDとし、archive全体の検証完了を主張しない。
利益数値、forecast/valuation/return、SOURCE_RECORDED結果、総合supported boolを出さない。

## CLIと副作用

入力は明示した1JSONファイル。正常reportはstdout、schema/parse等のerrorはstderr＋非zero exit。
structure validだがblockedの場合はreportを返し、schema failureと区別する。
ストアや元ファイルを書き込まない。出力ファイルを作らない。ネットワークも使わない。
不明時刻の埋め戻し、shock生成、record_onlyの切替、元payload修正をしない。

## 変更範囲と確認

新規production preflight.py、CLI script、専用test、本仕様、DECISIONS末尾の追記のみ。
書込担当は実装Agent1人。主担当は仕様/履歴文書のみ。設計監査は事前に完了、検証は固定commitで独立実施。
意味ある確認対象はrawhash改ざん/空hash、重複JSONkey、nonfinite JSON、未知時刻/方向区分、record_only混在、archive参照不整合、target/joint不足、決定的出力、CLI無書込。
ruff/format/mypyと専用pytest。新規変更に関連する既存profit_impact/evaluationテストだけ必要に応じ確認。
H0001/Locked Test実行なし。レビュー1回、阻害解消確認1回。

## 受入の限界

この機能の完成は全体Gate G1〜G5の合格ではない。完成品進捗は別の証拠棚卸しで更新する。
マクロから営業利益への接続や期待return契約をこの小工程へ追加しない。
