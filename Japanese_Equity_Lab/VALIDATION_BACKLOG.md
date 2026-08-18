# Validation Backlog

「Code Complete」(実装済み)と「Real-world Validated」(実際のSourceに接続し
確認済み)は別軸である(Phase4C要件§24/§25)。このDocumentは、実装済みだが
まだReal-world Validationが完了していない項目を一覧化する。**詳細は各項目の
Authoritative Docへのリンクのみを持ち、内容を重複して書き直さない**(重複
管理を避けるため)。

新しいBacklog項目が発生した場合は、この表へ追加するのみで良い(既存項目の
詳細説明を移動・複製しない)。

## 現在のBacklog

| # | 項目 | 現在Status | 阻害要因 | Authoritative Doc |
|---|---|---|---|---|
| 1 | TDnet Add-on Local Validation | `CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION` | Userのローカル環境でのAdd-on契約確認・実接続確認が必要 | `TDNET_LOCAL_VALIDATION_GUIDE.md`、DECISIONS.md D0048 |
| 2 | Company IR Live Validation #1 | `CODE_COMPLETE_AWAITING_LOCAL_LIVE_VALIDATION` | このSession自身のNetwork Egressが組織Policyにより一貫してBlocked(`EGRESS_BLOCKED`、2026-08-18確認)。Compliance確認込みでUserのローカル環境が必要 | `COMPANY_IR_LOCAL_VALIDATION_GUIDE.md`、DECISIONS.md D0053追記 |
| 3 | Company IR Live Validation #2(if needed) | 未着手 | #1と同じ | 同上 |
| 4 | EDINET Forward Snapshot Observation | 未着手(PoC設計のみ) | 継続的な観測実行そのものが未実施 | `EDINET_LOCAL_VALIDATION_GUIDE.md` §J |
| 5 | J-Quants `weekly_margin_interest`(信用取引週末残高) | `NOT_IMPLEMENTED`(Adapter未着手) | Endpoint仕様が全てSEARCH-SNIPPET-DERIVED(UNVERIFIED)。Standard Plan以上が必要という情報あり(未検証)、Publication Lag不明 | `POSITIONING_ARCHITECTURE.md`、`lib/positioning/catalog.py`、DECISIONS.md D0054 |
| 6 | J-Quants `short-ratio`(業種別空売り比率) | `NOT_IMPLEMENTED`(Adapter未着手) | 同上 | 同上 |
| 7 | J-Quants `short-sale-report`(個別銘柄空売り残高報告) | `NOT_IMPLEMENTED`(Adapter未着手) | Endpoint Path自体が未解決の矛盾(2検索結果が不一致) | 同上 |
| 8 | J-Quants `trades_spec`(投資部門別売買状況) | `NOT_IMPLEMENTED`(Adapter未着手) | 唯一Light Plan利用可能の可能性(単一の未検証情報源)、認証済みDashboard確認またはLocal接続確認が最優先候補 | 同上 |
| 9 | JPX直接公開の需給統計(信用取引残高・空売り集計・投資部門別売買状況) | 未着手(候補として記録のみ) | URL Pattern・Format(PDF/Excel)がScript化に適しているか未確認、Index Page Scrapeが必要な可能性 | `POSITIONING_ARCHITECTURE.md`、DECISIONS.md D0054 |
| 10 | Positioning Price-derived Metric(price_derived_liquidity) Local Real Data Validation | `CONNECTED`(Code)/`FIXTURE_VALIDATED`(Validation) | 合成Bar Dataでの検証のみ実施、実J-Quants Priceに対するEnd-to-End確認は未実施(上流のRawOHLCVBar自体は別Phaseで既にReal Data確認済み) | `POSITIONING_ARCHITECTURE.md`、DECISIONS.md D0054 |

## 運用ルール

- 新規Sourceを追加する際、Real-world Validationが完了しない場合は必ずこの
  表へ追加する(黙って`NOT_IMPLEMENTED`/`SKELETON`のまま放置しない)。
- 項目がValidated完了した場合、その項目の行を削除し、対応する
  `ImplementationStatus`/Validation Statusを更新した理由をDECISIONS.mdへ
  記録する(このFile自体には完了履歴を残さない、単なる進行中Backlogとして
  維持する)。
- どの項目も、未検証のままStatusを`LIVE_VALIDATED`/`CONNECTED`(実データ
  確認済みの意味で)へ変更しない。
