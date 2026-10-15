# 実データ検証: 前向きCPI日程記録

対象は米国2026年10月CPI。BLS公式日程とCPIホームのNext Releaseを照合し、2026-11-10 08:30 America/New_Yorkを確認。
UTC 13:30、日本時間22:30。予定は改訂され得るためactual_public_atへ流用しない。
出典: https://www.bls.gov/schedule/news_release/cpi.htm と https://www.bls.gov/cpi/home.htm。

既存D0110.1 MacroEvent/storeだけを利用しdevelopment/evidence/cpi-forward/event.jsonlへ保存。
schedule_available_at/created_atは今回保存時刻2026-10-15T15:18:30.338404Z（日本時間10月16日00:18:30）。
過去に利用可能だった時刻やBLS初回掲載時刻は不明で補完しない。今回のWeb閲覧確認に対する保守的なローカル記録時刻。
source-excerpt.jsonは閲覧ツールから構造化転記した抜粋であり原HTTP bytesではない。
raw取得はsandboxでDNS失敗、許可済み直接通信でHTTP403。拒否を迂回せず追加取得を止めた。
receipt.jsonのSHA256は抜粋のbytesを対象とする。原HTMLのhashだと表示しない。

## 現在の受入状態

SCHEDULE_ONLY。実イベント日程の保存のみ。独立予測/consensus/first release/market observationsは未収集、予測精度/PIT実証は未受入。
source_idのWEB_READERを保持し、原bytes未検証の制約を落とさない。
この新たなmacro資料論点の調査は公式日程とtimezone確認2ページで終了。同一SMM再調査なし。

## 次の実証条件

発表前のconsensus値にはprovider・dimension・unit・snapshot/取得時刻・出典が必要。
own forecastはモデル版と入力根拠を固定し、D0110.4計画とともに予測作成前に記録する。今回のevent登録は実験事前登録ではない。
発表後は真正性を確認したfirst releaseと実際の取得時刻を別保存。予定時刻をactual時刻と推定しない。
現在それらの値はなく、計算や比較を合成値で埋めない。予測器・履歴の不足は実装完了率に隠さない。
H0001/Locked Test、既存production変更、merge/FROZENなし。
