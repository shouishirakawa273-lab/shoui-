# ブランチ・凍結境界

コード基準 `0e915c81fafc26535001680e5fbd0b9c5fc1eb67`。2026-10-17のGitHub API照合。状態は観測時点の記録。

| 区分 | ブランチ・SHA | 確認結果 |
|---|---|---|
| GitHub既定 | claude/repo-creation-setup-ejmkje / 4a931eb12b9567a6d78593decc69053ff37d38e0 | treeにJapanese_Equity_Labなし。スクリーニング側 |
| Lab履歴上の受入先 | claude/investment-strategy-pipeline-jyfby5 / 071cff9c18632461c207a08c20e7c721a983221b | PR2のマージ先。PR1は既定向けにopen・非Draft・未マージ |
| 今回の調査元 | codex/integrated-research-portfolio / 0e915c81fafc26535001680e5fbd0b9c5fc1eb67 | PR18 open Draft。製品安定版ではない |

PR2は2026-10-14T09:44:53Zにマージ済み。DECISIONSの「Draft/unmerged」は当時の記録として読み、現在状態へ流用しない。PR3〜18は全16件open Draft・未マージ。

主候補の依存系列は3→7→8→9→10→11→12→13→14→15→16→17→18。4→5→6は別系列。各headとbaseは `remote_state.json` に保存。既定ブランチ変更・PR統合・マージ順の決定はW0では行わない。

## 凍結の根拠

`Japanese_Equity_Lab/DECISIONS.md` のD0107（18101以降）、D0108（18245以降）、D0109（18410以降）、D0110（18574以降）、D0110.1（18741以降）、D0110.2正式受入（18993以降）を参照。D0110.3以降の候補を自動的にFROZENとはしない。

D0110.2の正式受入対象コードは `9e9d98279a99de46b3bb162e2b5dbe905f547278`、当時baseは `1688d712095bf90b03e8cc9b38244f856a32aab2`。同エントリには対象6ファイルのSHA256がある。DECISIONS自体は追記履歴であり丸ごと凍結扱いしない。

`scripts/manifests/d0110_3_company_exposure_pilot.json` は071cff9を基準とする288ファイルの保護リスト。`freeze_inventory.json` に全path・基準/調査SHAのGit blobと差分を保存。これはそのタスクの保護範囲であり、全時代の正式FROZEN対象を完全網羅する証明ではない。古いmanifestのexpected_head=CURRENTも歴史的SHAの代替にならない。歴史manifestからWriterを再実行しない。

未確定: 古い全FROZEN宣言からの完全な統合台帳、将来の安定版としてどのブランチを採用するか、GitHub上の文書を正式採用する手順。既存ファイルは今回変更しない。

追加: [対応確認結果](FREEZE_RECONCILIATION_RESULT.md)とhistorical_freeze_inventory.jsonへ、後期11記録と早期5境界を追記。D0103〜D0110.2の欠落索引は補完済み。早期は内容版候補と引用行初出まで追跡したが、正式scope/承認不明を解消済みとはしない。
