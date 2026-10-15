# 実験計画の保存・操作 実装結果

base313201e0ce0476265a1c37415289ec94fa83c3e0。初回独立対象f56230b7fb0d92ce123ba43e24c31f9a084a6c33。
設計阻害解消対象60be7381d35d37718566aed3a6f9d21584364f6e。技術受入可能、未merge・未FROZEN。

## 今回作ったもの

- MacroPlanStore: 既存D0107追記専用storeを利用し、計画全field/nested contract/experiment/hashを保存復元。
- strictschema/type/重複JSONkey/重複ID/改竄/非canonical入力を拒否。同一ID同一内容も拒否。
- macro_plan.py register/show。JSON configで登録し、created_atは実現在UTC。利用者の過去時刻指定は禁止。
- showは既存記録を読むのみ、未知pathでdirectory/fileを作らない。
- 登録schema・synthetic例・利用手順は同日MACRO_PLAN_PERSISTENCE_SPEC.md。

独自予測値や観測データの作成・取得はしない。実CPI計画は架空のモデルで登録していない。
低levelstoreは正当な既存計画をその時刻のまま復元するが、歴史的登録の真正性を認証しない。
単一writer運用、同時書込の原子的transaction保証なし。原資料認証、予測性能、統計昇格は対象外。

## 独立監査と検証

初回固定SHAで新test+既存比較/demoの明示3fileを実行、90passed/exit0、前後SHA一致clean。
凍結288fileのhash一致、既存production/test/manifest変更なし。
設計監査で既存有効horizon_rule空文字/空白の保存拒否というlossless契約不一致1件を検出。
専用str|null復元に限定修正。closure固定SHAでNone/空/空白/通常文字列の4case成功/exit0。
codec/store全field/hash、異cwd CLI register/showを独立確認、設計closureも阻害解消。全面再レビューなし。
初回90とclosure4を合計して最終一括94件成功とは扱わない。
証拠: development/evidence/macro-plan/。初回commandの隔離pathは別注記、closureは実引数/TEMP/TMP/cwd/SHA/exitを記録。
H0001/Locked Testなし、ネットワーク取得なし、merge/FROZENなし。

## 残条件

実consensus/own forecast/first release/market observationsが不足。計画保存だけで実データ検証完了とはしない。
次に必要なのは出典・取得時刻付き入力とモデル/評価条件の確定。過去の観測時刻や科学的根拠を補完しない。
完成品全体率は未算定。既存未merge stack依存を維持する。
