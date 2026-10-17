# 過去のFROZEN対応確認・追加調査結果

基準コード: `0e915c81fafc26535001680e5fbd0b9c5fc1eb67`。文書調査開始: `5fca694e53c902bb221a05d494d3dc6724530b3d`。既存W0文書の保留条件を補完する新規記録であり、過去の凍結宣言や実装を変更しない。

## 今回確認した範囲

| 境界 | 対応確認 | 判断 |
|---|---|---|
| D0103〜D0110.2 | 11記録・49比較行。正式宣言とcode/test、文脈manifestを区別 | 47行同一。旧D0104の2行はD0104.1で変更・再凍結され、現行の同基準とは同一 |
| Stage 3.15 | D0093内容版の候補23path | 全件同一。ただし正式凍結の完全scope/hash manifestは未回収 |
| Stage 3.17 | D0097内容版のpeer候補14path | 全件同一。共有catalog等を含む完全境界は未確定 |
| D0102 faithfulness | 後続のACCEPTED/FROZEN記録が指すcb5baaaの2path | 全件同一。途中の関数/動作の凍結とファイル丸ごとの凍結を区別 |
| D0098.1 / DEV-AUTO | 後続のhook修正・staged scope guard拡張を追跡 | 変更箇所に後続記録あり。ownerの解除/再凍結の完全な原証拠は未確認。違反とも正式承認済みとも断定しない |

D0103〜D0110.2は [詳細表](FREEZE_LATE_AUDIT.md)、古い境界は [詳細表](FREEZE_EARLY_AUDIT.md)、全path/blob/引用行由来は [機械可読台帳](historical_freeze_inventory.json)。既存288task保護リストとは別物。

`record_commit` / `content_commit` / reviewed SHA / starting HEAD / merge SHAを分離した。earlyのrecord_commitは内容版候補であり、引用文言の初出は別のreference_line_provenanceに保存。Git履歴で文言を追えることは、人間の承認原文の回収を意味しない。

## D0110.2のハッシュ表の注意

6path中5pathのSHA256はGit bytesと宣言値が一致。manifestだけはGit LF bytesのSHA256が `62ea3cf954dc503b1c9efb1d0f810aa1cb2b13af2c8c3484b4a3502f847e6556`、宣言値は `5702eaeeca1316886325f17a4c14903c816a6ec83d8a568a83fa9261489e8ed7`。

同じGit bytesをCRLFへ変換すると宣言値を再現し、現在working treeの値とも一致した。reviewed SHAと現在のGit blobは同一で、内容改変の証拠はない。当時の計算方式は記録されていないため「当時CRLFで計算した」と認証したことにはしない。元のDECISIONS表は書き換えない。

## 判定・停止条件

後期の索引欠落は補完できた。早期の境界は、所在・内容版候補・差分・後続記録・未確定事項まで追跡可能になった。ただし、完全な正式scopeとowner承認が不足する境界は残る。**W0の全面受入を自動宣言せず、W1実装には進まない。**

同じ資料の反復探索はここで止める。次の独立確認で不足が原証拠に由来すると判断された場合、既存のチャット承認記録/受入manifest等の所在確認、または過去承認を捏造しない新しい管理基準の採用案をユーザーへ提示する。新基準の採用を新規FROZEN宣言や過去の変更の事後承認に置き換えない。

テスト・collect・H0001/Locked実行、データ取得、資格情報読取、コード/CI/実験記録変更、マージ・FROZEN化はなし。今回の調査で新たな致命的コード欠陥を実証したものではない。

## 独立確認結果

[独立確認記録](FREEZE_INDEPENDENT_REVIEW.md): `3af58366bd3626a83bcff2a356247ac7e6ff80a8` を対象に107比較行・17Git treeを照合し不一致ゼロ。SHA256とCRLF変換も独立再計算。Stage3.15の内訳表記のみ修正（lib21＋test1＋script1＝23）。新たなコード検証や実験の実行は不要との判断。

W0全面受入は引き続き保留。原証拠不足はStage3.15の正式全scope/hash、Stage3.17の共有catalog等を含む完全scope、D0098.1/DEV-AUTO後続変更のowner解除・再受入証拠。今回の比較で安全側の保護範囲を縮小したり、新たなFROZENを作ったりしない。反復探索を止め、既存承認記録の所在確認、または歴史受入とは別の将来向け管理基準の採用判断へ引き継ぐ。
