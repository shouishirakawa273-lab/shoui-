# EDINET_LOCAL_VALIDATION_GUIDE.md — EDINET API V2 ローカル疎通確認手順(Phase4B-2)

`.claude/skills/local-validation/SKILL.md` の手順に従って生成。

## 検証結果(2026-08-17、追記)

この手順に従ったLocal Real Data Validationは完了した。Documents List・
Document Download(`docID=S100TD9S`、`type=1`)いずれも成功を確認、
検証中にHTTP 200 + `metadata.status`エラー表現という重要な仕様を発見し
`EdinetAdapter`のエラー処理Bugを修正した。詳細な観測結果は
`EDINET_SOURCE_ONBOARDING.md`「追記(2026-08-17)」および`DECISIONS.md`
D0046参照。以下の手順は今後同種の検証(Field追加確認・Rate Limit実測等)を
再実行する際にそのまま再利用できる。

## なぜこの手順が必要か

このセッション(クラウド環境)は `api.edinet-fsa.go.jp`・`disclosure2dl.edinet-fsa.go.jp`
を含む、FSA/EDINET関連ホストへ一切疎通できない(`curl`で`CONNECT tunnel failed, 403`
を確認済み)。`data-source-researcher`によるSource Onboarding調査
(`EDINET_SOURCE_ONBOARDING.md`参照)も、公式資料を一切読めないまま`WebSearch`の
要約スニペットのみに基づく結果となり、多くの項目が未確認、Document Downloadの
`type`パラメータについては情報源間で**矛盾する**情報しか得られなかった。

このため、`lib/disclosures/providers/edinet.py`の`EdinetAdapter`は
**Raw HTTP Fetchのみ**(Documents List 1件、Document Download 1件)を提供し、
`DisclosureDocument`への正規化(Field Mapping)は一切行っていない。この手順の目的は
以下の2つ:

1. `api.edinet-fsa.go.jp`へ実際に接続し、候補として実装した認証方式
   (`Subscription-Key`クエリパラメータ、または`Ocp-Apim-Subscription-Key`ヘッダ)の
   どちらが正しいか、レスポンスが実際にどのようなフィールドを持つかを確認する。
2. 確認できた実フィールド名・タイムスタンプ意味論・訂正関係の意味論を、次のPhaseで
   `lib/disclosures/normalize.py`と同様のEDINET専用Normalizerへ反映できるようにする
   (このGuideの手順だけではNormalizerは実装しない — 観測結果を持ち帰ることが目的)。

## 原則

- **最初から大きく取得しない。** 1日分・1書類のみ。複数日・複数銘柄への拡張は、
  この手順が成功した後にユーザーの明示的な指示があってから。
- **APIキーの値は絶対に画面に表示しない・貼り付けない。** 有無の確認のみ行う。
- PowerShellを使用する(Windows環境前提)。

## A. 最新のブランチを同期する

```powershell
cd <リポジトリのパス>
git fetch origin claude/investment-strategy-pipeline-jyfby5
git checkout claude/investment-strategy-pipeline-jyfby5
git pull origin claude/investment-strategy-pipeline-jyfby5
```

## B. `EDINET_API_KEY`の設定・有無確認(値は表示しない)

リポジトリルートの`.env`(`.gitignore`対象、コミットしない)に追記する:

```
EDINET_API_KEY=<あなたのAPIキー>
```

有無のみを確認する(値は絶対に表示しない):

```powershell
if ($env:EDINET_API_KEY) {
    "EDINET_API_KEY is set"
} else {
    "EDINET_API_KEY is NOT set (call `Get-Content .env` yourself if needed, do not paste its contents here)"
}
```

`.env`を直接読み込む場合は`python-dotenv`経由でPythonプロセス内の環境変数として
設定されるだけであり、このPowerShellコマンド自体は値を画面に出さない。

## C. Documents List 最小Smoke Test(1日分のみ)

```powershell
cd <リポジトリのパス>
python -c "
from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from datetime import date
from lib.disclosures.providers.edinet import EdinetAdapter

adapter = EdinetAdapter(auth_style='query_param')
try:
    result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    print('SUCCESS with auth_style=query_param')
except Exception as exc:
    print(f'FAILED with auth_style=query_param: {type(exc).__name__}: {exc}')
    adapter2 = EdinetAdapter(auth_style='header')
    result = adapter2.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
    print('SUCCESS with auth_style=header')

import json
print(json.dumps(result.payload, ensure_ascii=False, indent=2)[:3000])
"
```

日付は任意の過去の平日でよい(`2024-05-08`はJST基準で実在する平日。もし
「縦覧期間外で結果が空」等のエラーが返る場合は、直近の平日に変更して再試行する
— それ自体が§2「過去データ範囲」の確認材料になる)。

**エラーが出た場合**、エラーメッセージ(**APIキーの値を除いて**)を貼り付けてもらえれば
`BASE_URL`・パラメータ名・認証方式を実際の仕様に合わせて修正できる。

## D. Raw Snapshotとして保存する

**重要(2026-08-17追記)**: 同一`docID`・同一`download_type`でも、
Retrievalごとに返ってくるRaw ZIP bytesが異なりうることが実データで
確認されている(Outer ZIP自体のTimestampがRetrievalごとに変わる、
ZIP内部のMember Contentは変わらない — 詳細は`EDINET_SOURCE_
ONBOARDING.md`追記2参照)。`RawSnapshotStore`は同じ`snapshot_id`への
上書きを拒否する(`AppendOnlyViolationError`)ため、同じ`docID`を複数回
Downloadして保存したい場合は、`snapshot_id`に取得時刻や連番を含めて
別Artifactとして保存すること(例:
`f"edinet_doc_{doc_id}_{retrieved_at:%Y%m%dT%H%M%S}"`)。同じ
`snapshot_id`を使い回して「更新」しようとするのは誤り — Raw Snapshotは
常にAppend-onlyのImmutable Artifactとして扱う。

```powershell
python -c "
from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from pathlib import Path
from datetime import date
from lib.disclosures.providers.edinet import EdinetAdapter
from lib.snapshot import RawSnapshotStore

adapter = EdinetAdapter()
result = adapter.fetch_documents_list_raw(date(2024, 5, 8), list_type=2)
store = RawSnapshotStore(Path('Japanese_Equity_Lab/01_data/raw'))
manifest = store.save(result, snapshot_id='edinet_documents_2024-05-08_local_validation')
print(manifest.local_file)
print(manifest.content_hash)
"
```

## E. 保存したRawファイルを直接確認する(正規化前の生の形を見る)

```powershell
Get-Content Japanese_Equity_Lab\01_data\raw\EDINET\edinet_documents_2024-05-08_local_validation.json | python -m json.tool | Select-Object -First 80
```

**ここで実際に見えたトップレベルのキー名一覧を、そのままこの会話に貼り付けてほしい**
(値そのものは機密ではないが、貼り付ける前に念のため会社固有の非公開情報が
含まれていないか自分の目で確認すること)。`EDINET_SOURCE_ONBOARDING.md` §9の
未確認フィールドリストと突き合わせて、次のPhaseでNormalizerを実装する。

## F. 診断スクリプト

この時点では専用の診断スクリプトは存在しない(Normalizer自体が未実装のため)。
手順Eの生JSON確認がこのPhaseにおける診断に相当する。

## G. Offlineでの再実行(ネットワーク接続なし)

保存済みSnapshotの読み込みはネットワーク呼び出しを一切行わないことを確認する:

```powershell
python -c "
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from pathlib import Path
from lib.snapshot import RawSnapshotStore

store = RawSnapshotStore(Path('Japanese_Equity_Lab/01_data/raw'))
manifest, payload = store.load('EDINET', 'edinet_documents_2024-05-08_local_validation')
print('content_hash matches:', manifest.content_hash)
print('record_count:', manifest.record_count)
"
```

## H. 想定される観測結果(これが見えれば疎通成功)

- 手順Cで`SUCCESS`のログが出て、JSONペイロードが表示される(トレースバックなし)。
- 手順Dで`manifest.local_file`と`content_hash`(64文字の16進文字列)が表示される。
- 手順Eで、2024-05-08時点でEDINETに提出された何らかの書類のリストらしきJSON構造が
  見える(0件でもエラーではない — その日にたまたま提出がなかった可能性もある。
  その場合は日付を変えて再試行)。
- 手順Gで`content_hash matches: True`および`record_count`が手順Dと同じ値になる。

## I. 何を貼り付けて報告してもらいたいか

- **貼り付けてほしいもの**: 手順Cの`SUCCESS`/`FAILED`の行、手順Eで見えたJSONの
  トップレベルキー名一覧(サンプル値は1〜2件程度で十分)、手順Hと食い違う点があれば
  そのエラーメッセージ全文。
- **絶対に貼り付けないでほしいもの**: `EDINET_API_KEY`の値そのもの、`.env`ファイルの
  中身全体、リクエストURL全体(query_param認証方式の場合、APIキーがURLに含まれるため)。

## 参考: Document Download(添付ファイル)のSmoke Testは今回は含めない

手順Eで実際の`docID`(実在するdocument IDフィールドの値、フィールド名自体が
未確認なので実際に確認してから使うこと)が分かった後であれば、以下のように
`fetch_document_raw`を試すこともできる。ただし`download_type`の値は
`EDINET_SOURCE_ONBOARDING.md` §7の通り情報源間で矛盾しているため、
`0`・`1`・`2`・`5`のいずれかを一つずつ試し、返ってきた`content_type`ヘッダの値を
教えてほしい(それによって実際の値と形式の対応が初めて確定する):

```powershell
python -c "
from dotenv import load_dotenv
load_dotenv()
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from lib.disclosures.providers.edinet import EdinetAdapter

adapter = EdinetAdapter()
result = adapter.fetch_document_raw('<実際に確認したdocID>', download_type=1)
print(result.payload['content_type'])
print(len(result.payload['content_base64']))
"
```

## J. Forward Snapshot PoC Procedure(4A.5.1-7、設計・Procedureのみ、実行はまだしない)

**目的**: このLabの`RawSnapshotStore`(既存、新規Storage機構は作らない)を
使い、同一対象(例: 同一日付のDocuments List、または同一docID)を
**複数日にわたって繰り返しFetch・保存**し、Providerの実際の挙動
(Historical List Is Mutable、D0046)を将来の複数回観測で確認できる
土台とする。

**重要な区別(過剰主張しない)**: Forward Snapshot(これから先の観測を
蓄積すること)と、Historical Provider PIT Reconstruction(過去のある
時点でProviderがどう見えていたかを遡って完全再現すること)は**別の
主張である**。今から観測を始めても、2026-08-17より前の時点でEDINETが
どう見えていたかを遡って再現することはできない。観測期間中に何も変化が
無かったとしても、それは「将来も不変である」ことの証明にはならない
(観測は確率的Evidenceであり、仕様保証ではない)。

### 保存するSnapshot命名規則(案)

既存`RawSnapshotStore.save(result, snapshot_id=...)`をそのまま使う。
`snapshot_id`に日付・連番を含めることで、同一対象への繰り返しRetrieval
を別Artifactとして共存させる(Append-only設計と両立、新規コード不要):

```
edinet_historical_docs_{対象日付YYYYMMDD}_{Retrieval実施日YYYYMMDD}_v{連番}
```

例: 2026-08-17付のDocuments Listを、2026-08-17・2026-08-24・
2026-08-31の3回観測する場合:
`edinet_historical_docs_20260817_20260817_v1`、
`edinet_historical_docs_20260817_20260824_v1`、
`edinet_historical_docs_20260817_20260831_v1`。

### 記録するField(既存Manifest Fieldそのまま、新規Field追加なし)

| Field | 導出元 |
|---|---|
| request params | `RawFetchResult.request_parameters`(既存) |
| requested_at | 実際にRequestを送信した時刻(Adapter呼び出し直前にUserが記録) |
| retrieved_at | `RawFetchResult.retrieved_at`(既存) |
| response metadata(status/headers等) | 既存`RawFetchResult`の該当Field |
| raw hash | Manifest既存の`content_hash` |
| canonical hash(Document本体をDownloadした場合のみ) | `compute_canonical_zip_content_hash()`の結果Hex Digest(**Byte列自体は保存しない**、D0046追記2の運用方針を踏襲) |
| immutable snapshot path | `RawSnapshotStore`が既存の仕組みで自動決定(手動管理しない) |
| manifest / index | 既存Manifest File(JSON、`RawSnapshotStore`が自動生成) |
| source | `"EDINET"`(固定、Multi-Source化した場合のみ変数化) |
| API/status result | Adapterの戻り値の成否(既存Errorハンドリングをそのまま使う、新規例外型は作らない) |

### 実行タイミング

このRoundでは**実行しない**(Procedure設計のみ)。TDnet Add-on Local
Validation後、Userのローカル環境で複数日にわたり実施する(ユーザー
2026-08-17 Task指示 §4A.5.1-7、および前Round`PHASE4A5_1_PLAN.md`の
Deferred Items記載通り)。実施した場合の観測結果は、D0046追記2と同じ
形式(Confirmed Fact/OBSERVED_BEHAVIORの区別を保つ)でDECISIONS.mdへ
追記する。
