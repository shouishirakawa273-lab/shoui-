# W0 D0103以前の凍結境界監査

比較HEAD: `5fca694e53c902bb221a05d494d3dc6724530b3d`。workspace-relative `Japanese_Equity_Lab/DECISIONS.md`の行番号を引用。git history/tree/blob比較のみ。tests/collect/API/credential/return計算なし。

## 結論

古い正式凍結参照は存在する。ただし初期Stageはowner承認の完全path/hash manifestを回収できず、git実装commitとの対応は**内容版候補**として記録する。後続文書が明示する受入SHAとstarting/expected HEADは別物。`frozen=True` dataclass、一般的変更禁止、過去のFrozen参照だけから新たな受入境界を作らない。

| 境界 | 宣言・scope根拠 | 内容commit候補と現blob比較 |
|---|---|---|
| Stage 3.15（D0089〜D0093） | :11083–11088はD0092 production freeze維持、:11092はD0093 acceptance harness変更、:11097–11099はStage3.15 Frozen。 | D0093 `983e32ef5566047237140d0213c792d35389c191`。当時存在したvaluation/evidence/registry全22fileとhistorical-context test1file、計23/23不変。harness含む。これは範囲候補の広め照合で完全な正式全scope確定ではない。 |
| Stage 3.17（D0095〜D0097） | :12066–12085は変更scope peer builder/provenance/tests、:12088–12092は3.15/3.17 freeze維持。 | D0097 `3e17f7e67466deb8a0c9de2b13e683d94bd4f8c1`。peer全7production+全7test=14/14不変。共有sources catalog等の完全境界は別途UNKNOWN。 |
| D0098.1 hook guard | :12351–12361で2file scope、:12797でD0098.1 FROZEN参照。 | `1626bdbaa55db53acc65ed520ce798494b2da670`。test不変、hook変更。変更は`18258f6eb86ddf48444f260a37dd4adf96961996` DEV-HOOK-01、:15063以降にtoolchain調査/修正記録あり。したがって即freeze違反としない。owner解除/再凍結SHAはUNKNOWN。 |
| D0102.4設計/実装系列 | :13921設計のみ、:14608設計closure。実装:14872以下、:15537–15538でdeterministic旧版ACCEPTED/FROZEN、:15935–15938で系列全体cb5baaa ACCEPTED/FROZEN。 | 最終`cb5baaafb8d5de6052b70a00abc2e52eea37d293`、faithfulness.py/test_faithfulness.py 2/2不変。途中deterministic凍結はsymbol/behavior境界として同fileのmodel layer追加を許す形（:15538–15540、:15925–15931）。旧file全体blob不変を要求しない。 |
| DEV-AUTO各版 | :16113/16285/16488/16646/16794/16872/16963で先行版ACCEPTED/FROZENを明示。後続closureでは同一file意図的修正あり。 | 02.4内容`0f92e97f38268b4a5c59e8b11db1b00e89c8f801`のcode/test候補17file中14不変、gates.pyと2tests変更。後続`fb55fd96a29b714da44545753abb09585f2924ee` INCIDENT-01.1のstaged scope guard拡張で説明される（:17340–17373）。02.4自体の後続正式ACCEPTED/FROZEN宣言は今回未発見。 |

## 履歴pin（すべて内容版、後続明示受入参照と照合）

- D0102.4.1 `4edb2603bc7bc8afe23135553ebb37bf408aa07e` → closure `ac7d4511f33f31fc8b72e42086747ec128433c77` → final deterministic `0f049e39834617ceb34bc90923d15d797ed18d1f` → model `6dfd38a1d63cfa12971cd0d6e023b856b2c791ec` → final `cb5baaafb8d5de6052b70a00abc2e52eea37d293`。
- DEV-AUTO-01 `1802a49e8742c4d7db08705ed2af2d8a7f0f6500`、02 `a81d9794b5d263ff7dbd89c6e5a9e7551cd70d4c`、02.1 `f36c3e6f55e4d1abbe43f13653cb548483595d9e`、02.1.1 `7af19f22c261b0bc5720ed089702d967fecf1a51`。
- 02.2 `9f214ec7258c0fbcda443ea0c4afe565c7b98d5e`、02.2.1 `b962721dd8fca33ddb0c322e8e7961e3434cd786`、02.2.2 `0556d05210fa22b6531ada6c90cedc9ca2415e55`、02.3 `e9faf36f085f3ae3bad6be798a1fe29c3b0800e2`。
- `cf89b6e0a3b0abb4e99e7468231f809601934701`はmessageだけ02.4で、実装変更ではなく16fileのbulk-addだったと:17301–17316に記録。正式02.4内容版と取り違えない。

## 機械可読比較

`historical_freeze_inventory.json (early.entries)`に各scope候補のpath、旧/現git blob OID、UNCHANGED/CHANGEDを保存。hashはGit blob OIDでありraw SHA256ではない。

record_commit欄は該当実装entryを含む内容commit候補であり、後続の凍結宣言が最初に記録されたcommitを別途確定したものではない。統合台帳ではこの制約を維持すること。formal acceptanceを推定でYESにしない。

## 追加の行由来追跡

統括担当がgit blameで、引用行の初出commitをhistorical_freeze_inventory.jsonのreference_line_provenanceへ追記。これは文言の初出証拠であり、実装内容SHAやowner承認の代替ではない。元ノートの初出commit未確定という制約は、引用行についてのみ補完された。scopeの完全性と承認証拠の不足は継続。
