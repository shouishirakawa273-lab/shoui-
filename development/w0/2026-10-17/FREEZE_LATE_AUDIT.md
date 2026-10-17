# W0 late-stage frozen acceptance/blob ledger

固定調査HEAD: `5fca694e53c902bb221a05d494d3dc6724530b3d`。2026-10-17。read-only Git log/show/ls-tree/DECISIONS照合のみ。テスト/collect/データ/秘密取得/Locked/H0001実行/Git変更なし。本ノートのみ新規作成。

## 読み方と重要区別

- D0103〜D0110.1は各実装コミット内に正式Status/FROZEN記述を持つことをgit showで照合。starting_headやmanifest.expected_headを受入commitへ代用しない。下記はGit上で正式宣言と対象内容が同居するcommitであり、未取得の人間承認原文まで独立認証した意味ではない。
- D0110.2: 実装4f8e3b3bf636677d7f30aa1318fd9c8e19288921、受入対象reviewed HEAD9e9d98279a99de46b3bb162e2b5dbe905f547278、正式記録commit794da6b5d1e0b6a748b983736c83191d7a65bd06、merge071cff9c18632461c207a08c20e7c721a983221bは別。
- blob列はGit object IDでありSHA256ではない。SAMEはcommit上のbytes一致。未コミットworking tree内容の認定ではない。
- D0103〜D0110.1のStatusは指定code/testをFROZENと記述し、manifestそのものまで明示凍結していない。manifestは作業境界の証拠として別列に記録し、推測で正式freezeへ昇格しない。D0110.2はmanifest含む6filesを明示凍結。
- D0104はD0104.1で意図的変更・再FROZEN。旧受入blobとの差分はその承認更新で説明でき、現行基準はD0104.1。

## D0103

- 受入対象commit: `f82b9bda3e1a4c33a08fcef498798840e58aba34`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 17439。manifest: `Japanese_Equity_Lab/scripts/manifests/d0103_semantic_claim_evidence_integration_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_evidence_integration.py` | explicit frozen code/test | `7dd70e720076d865b81d52619bfdbcb85cffc9ba` | `7dd70e720076d865b81d52619bfdbcb85cffc9ba` | SAME |
| `Japanese_Equity_Lab/lib/disclosures/evidence_integration.py` | explicit frozen code/test | `5af1b60b6d80194d6ead78a8c3de8de16612388f` | `5af1b60b6d80194d6ead78a8c3de8de16612388f` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0103_semantic_claim_evidence_integration_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `b839539f81f1f6474f522b6ab599099bfe23a8e6` | `b839539f81f1f6474f522b6ab599099bfe23a8e6` | SAME |

## D0104

- 受入対象commit: `c159ee245e0894f8da0e9d6655b2505a349a15a3`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 17595。manifest: `Japanese_Equity_Lab/scripts/manifests/d0104_evidence_lineage_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_disclosures_evidence_lineage.py` | explicit frozen code/test | `fbe51639ef62f81194db2cd3b146cdf07c1ee731` | `90ac3c4e5453ac06c4166001bb9ece95b4324d02` | DIFFERENT |
| `Japanese_Equity_Lab/lib/disclosures/evidence_lineage.py` | explicit frozen code/test | `43d8171ea66bc9e2e8fbe87e59bf36604906b750` | `4b95c7729b985801984557f81c98c79c0e3ca5a8` | DIFFERENT |
| `Japanese_Equity_Lab/scripts/manifests/d0104_evidence_lineage_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `e4c9deab41da2eb11be763e9f9326fb70a1e38e8` | `e4c9deab41da2eb11be763e9f9326fb70a1e38e8` | SAME |

## D0104.1

- 受入対象commit: `52cac1c768730f2b1a92367edcbecc5b2c66497f`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 17750。manifest: `Japanese_Equity_Lab/scripts/manifests/d0104_evidence_lineage_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_disclosures_evidence_lineage.py` | explicit frozen code/test | `90ac3c4e5453ac06c4166001bb9ece95b4324d02` | `90ac3c4e5453ac06c4166001bb9ece95b4324d02` | SAME |
| `Japanese_Equity_Lab/lib/disclosures/evidence_lineage.py` | explicit frozen code/test | `4b95c7729b985801984557f81c98c79c0e3ca5a8` | `4b95c7729b985801984557f81c98c79c0e3ca5a8` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0104_evidence_lineage_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `e4c9deab41da2eb11be763e9f9326fb70a1e38e8` | `e4c9deab41da2eb11be763e9f9326fb70a1e38e8` | SAME |

## D0105

- 受入対象commit: `a42ad2d6f3184fe36f49ae6eae0dacfaee076111`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 17928。manifest: `Japanese_Equity_Lab/scripts/manifests/d0105_incremental_research_update_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_incremental_research_update.py` | explicit frozen code/test | `826a23b94861e55ee762eb32242ef896170e0d14` | `826a23b94861e55ee762eb32242ef896170e0d14` | SAME |
| `Japanese_Equity_Lab/lib/evidence/incremental_update.py` | explicit frozen code/test | `891ed3c7d3388f7eb9dd1bc5390a173047dddd6a` | `891ed3c7d3388f7eb9dd1bc5390a173047dddd6a` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0105_incremental_research_update_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `28b6dbdc753d5cd1e54f3eb845234b896c949948` | `28b6dbdc753d5cd1e54f3eb845234b896c949948` | SAME |

## D0106

- 受入対象commit: `0d4acc5d875518244e189592b514aa0fdeb5b244`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18097。manifest: `Japanese_Equity_Lab/scripts/manifests/d0106_thesis_break_monitor_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_thesis_impact.py` | explicit frozen code/test | `8d1f528cfe7dad87b4e6e9aa408cc6ba70a3099a` | `8d1f528cfe7dad87b4e6e9aa408cc6ba70a3099a` | SAME |
| `Japanese_Equity_Lab/lib/evidence/thesis_impact.py` | explicit frozen code/test | `2e4c951aac74bbd65182dafe89d488da08fb4f5d` | `2e4c951aac74bbd65182dafe89d488da08fb4f5d` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0106_thesis_break_monitor_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `a4b80015a4f147d7132024e46915cf5889926aa6` | `a4b80015a4f147d7132024e46915cf5889926aa6` | SAME |

## D0107

- 受入対象commit: `ded9a74ba8602ec3579b67edec1aebdbeee38330`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18240。manifest: `Japanese_Equity_Lab/scripts/manifests/d0107_immutable_evaluation_foundation_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_evaluation_foundation.py` | explicit frozen code/test | `2a15d5adb34a4af852074da03223a92e59a3010e` | `2a15d5adb34a4af852074da03223a92e59a3010e` | SAME |
| `Japanese_Equity_Lab/lib/evaluation/__init__.py` | explicit frozen code/test | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | SAME |
| `Japanese_Equity_Lab/lib/evaluation/integrity.py` | explicit frozen code/test | `f57d08c783cafd77d23ee3d84274107aa41e849c` | `f57d08c783cafd77d23ee3d84274107aa41e849c` | SAME |
| `Japanese_Equity_Lab/lib/evaluation/model.py` | explicit frozen code/test | `7da1d8c3042d34f6eacfcf05f8daa7dd87b1b134` | `7da1d8c3042d34f6eacfcf05f8daa7dd87b1b134` | SAME |
| `Japanese_Equity_Lab/lib/evaluation/store.py` | explicit frozen code/test | `9a324267408be3059973fae59ffdb209acae8881` | `9a324267408be3059973fae59ffdb209acae8881` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0107_immutable_evaluation_foundation_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `a9089ce7d92f1b4de3a6e767391d720ed2e9ba9d` | `a9089ce7d92f1b4de3a6e767391d720ed2e9ba9d` | SAME |

## D0108

- 受入対象commit: `bae44d956723c8fe291e9b11ec36d40c3e5d4103`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18405。manifest: `Japanese_Equity_Lab/scripts/manifests/d0108_market_expectations_foundation_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_expectations_foundation.py` | explicit frozen code/test | `9cf51742e6e2b3fe0e1c556e16aec12c217e8480` | `9cf51742e6e2b3fe0e1c556e16aec12c217e8480` | SAME |
| `Japanese_Equity_Lab/lib/expectations/__init__.py` | explicit frozen code/test | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | SAME |
| `Japanese_Equity_Lab/lib/expectations/comparison.py` | explicit frozen code/test | `0204287e0c764c64d4b4ea4916b15c877f3aaf54` | `0204287e0c764c64d4b4ea4916b15c877f3aaf54` | SAME |
| `Japanese_Equity_Lab/lib/expectations/model.py` | explicit frozen code/test | `e65aa2b5e0caad0c2d774617118ca914b9b1122b` | `e65aa2b5e0caad0c2d774617118ca914b9b1122b` | SAME |
| `Japanese_Equity_Lab/lib/expectations/reverse_spec.py` | explicit frozen code/test | `39d6cd0c81c85398825cc2eec25d92cfef0e309d` | `39d6cd0c81c85398825cc2eec25d92cfef0e309d` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0108_market_expectations_foundation_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `afa8b414033c9f39dfec065fc5158076fb520f41` | `afa8b414033c9f39dfec065fc5158076fb520f41` | SAME |

## D0109

- 受入対象commit: `c2421a67c151c9bfb24ba5356d1932715f5836ca`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18569。manifest: `Japanese_Equity_Lab/scripts/manifests/d0109_fundamental_forecast_engine_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_forecasting_foundation.py` | explicit frozen code/test | `ac809eabb347ab4ef943c749a36373913944210d` | `ac809eabb347ab4ef943c749a36373913944210d` | SAME |
| `Japanese_Equity_Lab/lib/forecasting/__init__.py` | explicit frozen code/test | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | SAME |
| `Japanese_Equity_Lab/lib/forecasting/engine.py` | explicit frozen code/test | `4da7e75ddef261e9e9fb74fd059612fea8c1a4e8` | `4da7e75ddef261e9e9fb74fd059612fea8c1a4e8` | SAME |
| `Japanese_Equity_Lab/lib/forecasting/model.py` | explicit frozen code/test | `eb1986817592aad67e33094fc102eea608c783af` | `eb1986817592aad67e33094fc102eea608c783af` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0109_fundamental_forecast_engine_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `145ec0f3ea8b24ec6ce6339f1af2b09a08447b21` | `145ec0f3ea8b24ec6ce6339f1af2b09a08447b21` | SAME |

## D0110

- 受入対象commit: `6b76de84b42d9a873f893be48f115d97d8c5c74a`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18736。manifest: `Japanese_Equity_Lab/scripts/manifests/d0110_forward_reverse_valuation_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_valuation_forward_reverse.py` | explicit frozen code/test | `1f80c9a47e6c6fc9aced1316852f91ded8a3d8ec` | `1f80c9a47e6c6fc9aced1316852f91ded8a3d8ec` | SAME |
| `Japanese_Equity_Lab/lib/valuation/engine.py` | explicit frozen code/test | `bd7b92ccaf973ca3ba5c835e0072862d299e591b` | `bd7b92ccaf973ca3ba5c835e0072862d299e591b` | SAME |
| `Japanese_Equity_Lab/lib/valuation/forward_reverse_model.py` | explicit frozen code/test | `0b3ac46174a572aa1418c66c1175d2a489b13941` | `0b3ac46174a572aa1418c66c1175d2a489b13941` | SAME |
| `Japanese_Equity_Lab/lib/valuation/reverse.py` | explicit frozen code/test | `02e66339af900faaa6c6dd84344048a1b712322d` | `02e66339af900faaa6c6dd84344048a1b712322d` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0110_forward_reverse_valuation_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `00ac349a400420d9c02f1d114339145137886aec` | `00ac349a400420d9c02f1d114339145137886aec` | SAME |

## D0110.1

- 受入対象commit: `1688d712095bf90b03e8cc9b38244f856a32aab2`。受入commit内該当sectionにFROZEN宣言確認。
- 現DECISIONS根拠開始行: 18867。manifest: `Japanese_Equity_Lab/scripts/manifests/d0110_1_macro_event_surprise_foundation_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_macro_event_surprise.py` | explicit frozen code/test | `1ecb59f7601a8abe04034f2011b4c6f9b471701d` | `1ecb59f7601a8abe04034f2011b4c6f9b471701d` | SAME |
| `Japanese_Equity_Lab/lib/macro_events/__init__.py` | explicit frozen code/test | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | `e69de29bb2d1d6434b8b29ae775ad8c2e48c5391` | SAME |
| `Japanese_Equity_Lab/lib/macro_events/model.py` | explicit frozen code/test | `eb6549137b7f39a7096413aa2b00f498831567f0` | `eb6549137b7f39a7096413aa2b00f498831567f0` | SAME |
| `Japanese_Equity_Lab/lib/macro_events/store.py` | explicit frozen code/test | `d35f6f8df3b633573e4cd96d22714fb3f21b1c55` | `d35f6f8df3b633573e4cd96d22714fb3f21b1c55` | SAME |
| `Japanese_Equity_Lab/lib/macro_events/surprise.py` | explicit frozen code/test | `fc1c968f80de2a9d2b9a3e8c804946a3e59ab9be` | `fc1c968f80de2a9d2b9a3e8c804946a3e59ab9be` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0110_1_macro_event_surprise_foundation_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `3a9cdfabdde464e1915c566896805b36efbfd7c1` | `3a9cdfabdde464e1915c566896805b36efbfd7c1` | SAME |

## D0110.2

- 受入対象commit: `9e9d98279a99de46b3bb162e2b5dbe905f547278`。後続794da6b5内のFormal acceptance/FROZENを確認。reviewed SHAは本文19000に明記。
- 現DECISIONS根拠開始行: 18993。manifest: `Japanese_Equity_Lab/scripts/manifests/d0110_2_event_window_response_pilot.json`。

| Path | Role | Accepted blob | Current blob | Comparison |
|---|---|---|---|---|
| `Japanese_Equity_Lab/13_tests/test_event_window_response.py` | explicit frozen code/test | `2e43ff1382d555b08e992dc4a442e4425edc8e49` | `2e43ff1382d555b08e992dc4a442e4425edc8e49` | SAME |
| `Japanese_Equity_Lab/lib/event_responses/__init__.py` | explicit frozen code/test | `96173ba5eb818bf7c4f8978480bca3dc8f681ef9` | `96173ba5eb818bf7c4f8978480bca3dc8f681ef9` | SAME |
| `Japanese_Equity_Lab/lib/event_responses/measurement.py` | explicit frozen code/test | `01e47a4512334b45362378b80b81187a931f2386` | `01e47a4512334b45362378b80b81187a931f2386` | SAME |
| `Japanese_Equity_Lab/lib/event_responses/model.py` | explicit frozen code/test | `e2d0fcaf4595223f1ee2e337871971044661b67c` | `e2d0fcaf4595223f1ee2e337871971044661b67c` | SAME |
| `Japanese_Equity_Lab/lib/event_responses/store.py` | explicit frozen code/test | `5d41d90a2981f1f0e814c20f15b57695f8a6c16e` | `5d41d90a2981f1f0e814c20f15b57695f8a6c16e` | SAME |
| `Japanese_Equity_Lab/scripts/manifests/d0110_2_event_window_response_pilot.json` | manifest evidence (explicitly frozen only D0110.2) | `7526b24113e06e75fe4ee5c1bf798b8e3f272feb` | `7526b24113e06e75fe4ee5c1bf798b8e3f272feb` | SAME |

## 集約

{'same': 47, 'different': 2, 'unknown': 0}

D0104 original→current差異以外は本比較で見つかったものをそのまま上表へ表示。宣言対象外の全repoファイルや累積288manifest全体の証明ではない。DECISIONS自体は追記記録であり全文bytes固定対象として扱わない。D0104.1専用manifest新設は当該commit変更一覧に存在せず、D0104 manifestを参照記録。

## D0110.2 explicit SHA256 byte verification

Git showのstdout bytesへSHA256を計算。Windows working-tree CRLF変換なし。正式宣言のcode/test 5件はreviewed HEADと現HEADで一致。manifestだけは宣言とGit bytes SHA256が不一致。ただしreviewedと現行blobは同一。

| Path | Declared SHA256 | Status |
|---|---|---|
| `Japanese_Equity_Lab/lib/event_responses/__init__.py` | `ac5901fba7908436bec51712767c4fffdccbf200bc76404c2e2341c9a5be8b62` | MATCH |
| `Japanese_Equity_Lab/lib/event_responses/model.py` | `3b0746eb2629fdd2c952d291840aa914db1bbc3db66a5ddc0077f514ed6b0fd1` | MATCH |
| `Japanese_Equity_Lab/lib/event_responses/measurement.py` | `f0f2f39d21e162408acd9f537e7dafba325cdac577468bb4f008312a62243797` | MATCH |
| `Japanese_Equity_Lab/lib/event_responses/store.py` | `d40c5303158bdd804a0bd4596bc8bc03594625e0c10dcb65d25504888ad70437` | MATCH |
| `Japanese_Equity_Lab/13_tests/test_event_window_response.py` | `7956aecbb0a020bad2965865b03bab1c8906fd6f9198affc65e8e0a957c8be4a` | MATCH |
| `Japanese_Equity_Lab/scripts/manifests/d0110_2_event_window_response_pilot.json` | `5702eaeeca1316886325f17a4c14903c816a6ec83d8a568a83fa9261489e8ed7` | MISMATCH |

要求されたcode基準0e915c81fafc26535001680e5fbd0b9c5fc1eb67と現調査HEAD間のJapanese_Equity_Lab以下git diff --name-onlyは空。

manifestのreviewed/current Git bytes SHA256は`62ea3cf954dc503b1c9efb1d0f810aa1cb2b13af2c8c3484b4a3502f847e6556`。Git LF bytesを計算上CRLFへ変換したSHA256は`5702eaeeca1316886325f17a4c14903c816a6ec83d8a568a83fa9261489e8ed7`で宣言値に一致。これは改行方式差で説明可能な記録ハッシュ不整合であり、宣言がどのbytesを対象にしたか当時原記録なしには断定しない。凍結ファイル内容の事後変更を示すものではない。
