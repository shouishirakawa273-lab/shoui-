# BLS単一系列 capture-only 取込仕様

開始ba4155405b1d92ed30d0bfef7974826e6422e582。取得接続gate成功: 公式v1 GET、HTTP200、
REQUEST_SUCCEEDED、CUUR0000SA0、35rows。実証拠はworkspace validation/bls-source-gate/。
出典 https://www.bls.gov/developers/api_signature.htm と https://www.bls.gov/cpi/factsheets/cpi-series-ids.htm 。
同一資料論点の探索2回を終了。既知HTML403は再試行していない。

## 受入条件

- 新規lib/macro_capture/、scripts/bls_capture.py、専用testのみ。既存凍結/既存tests変更禁止。
- source固定https://api.bls.gov/publicAPI/v1/timeseries/data/CUUR0000SA0、1系列/1取得元。
  米CPI-U総合・米都市平均・NSA月次・指数水準1982-84=100。前年比/初報/consensusへ変換しない。
- capture単位のimmutable bundle: 応答entity bytes、実現在UTCの開始/受信時刻、URL/HTTP状態/content hash、
  解釈版、結果/失敗理由、正規化MacroRecordを保存。wire圧縮bytesの保存と混同しない。
- exact必要field型/series/年月/月コード/有限Decimal/重複JSONkey・期間を検査。空・失敗status・不正schemaは隔離。
  M13は年平均なので月次recordから明示除外。将来対象月の値を受理しない。
- 既存MacroRecordとD0107 AppendOnlyRecordStoreを再利用。series identityにsource/series/NSA/MONTHLY/年月を含める。
  market_public_at=None/UNKNOWN、vintage_label=None、retrieved_atは実受信UTC。as-ofはSYSTEM_OBSERVEDのみ。
  MacroEvent/FirstRelease/実験/予測recordを自動生成しない。
- 単一writer排他。1runをstagingで構築しatomic directory renameで完成公開。不完全runを完成扱いしない。
  run-id再実行は既存bundle/hashを検証して再利用、通信/書換なし。改訂・新規取得は別runとし上書きなし。
- 接続timeout/応答上限1MiB、401/403/redirect停止、有界retryのみ。ネット失敗もreceiptへ残しstderr/nonzero。
  ロックはprocess異常終了で解放可能にする。不完全stagingを自動で削除/完成扱いしない。
- CLI fetch/show、stdout JSONとstderrエラーを分離。任意cwd。showは未知pathを作成せず、bundlehash/record照合。
- 固定fixtureで成功/重複run/改訂/不正schema/HTTP失敗/途中停止/排他/read-onlyを検証。
  独立担当は同一完全SHAを確認。初回レビュー1回＋必要阻害closure1回まで。

## 運用完了との区別

今回まず実装/独立検証/実1取得を完了させる。その後、実予定実行2回と失敗可視化、永続運転場所を確認する。
2回は運用policyであり統計保証ではない。実定期運転前に自動収集稼働済みと表示しない。
原資料収集は前向き予測実験と別。モデル/consensus/事前登録は未定義のまま架空値を作らない。
禁止H0001/Locked Test、sources変更、merge/FROZEN。完成品全体率未算定。
BLS取得日と由来を出力し、取得後の分析品質をBLSが保証しない旨を表示する。

## 操作と実装上の限定

任意cwdから絶対pathのPythonとscripts/bls_capture.pyを指定し、`fetch --root <保存先> --run-id <一意ID>`。
確認は`show --root <保存先> --run-id <ID>`。run-idを省略したfetchはUUIDを生成する。
stdoutはreceipt JSON、FAILEDはstderrと終了code1。未知showは保存先を作成しない。
同じIDは完成bundleを検証して返すだけ。失敗も再取得しない。不完全.staging-IDは保持して拒否し、別IDで取得する。
通信は1attempt/retryなし、redirect不許可、socket timeout15秒。1MiB超は最大1MiB+1byteのprefixのみを保存し、
errorに完全応答hashではない旨を明示。通常成功はHTTP entity bytes全体を保存する。
OS lockはprocess終了で解放される。bundle renameは同volumeで行い、既存bundleは上書きしない。
bundle内のSHA256は変更検出であり電子署名・原資料の独立真正性証明ではない。
再表示時はhashだけでなくrawから再正規化し、全recordの内容・受信時刻との一致を検査する。
SYSTEM_OBSERVEDは意味label。既存as-of resolverのenumはAvailabilityBasis.OBSERVEDであり、
MacroRecord.market_public_at_basisはUNKNOWNのまま。過去の市場公開時刻や初報を推測しない。
