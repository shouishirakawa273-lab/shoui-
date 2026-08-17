# TDNET_LOCAL_VALIDATION_GUIDE.md — J-Quants TDnet Add-on ローカル疎通確認手順(Phase4B-3)

## この手順の性質(EDINET版との違いを先に明記する)

`EDINET_LOCAL_VALIDATION_GUIDE.md`(Phase4B-2)は「実装済みのRaw Fetch
Adapterを、ユーザーのローカル環境から実際に呼んで観測結果を持ち帰る」ための
手順だった。

**このGuideはそれとは性質が異なる。** `TDNET_SOURCE_ONBOARDING.md`の調査が
以下の複合的なBlockに直面したため、`lib/disclosures/providers/tdnet.py`
(Adapter/Normalizer)はこのPhaseでは一切実装していない:

1. 本セッションから`jpx-jquants.com`・`jpx.gitbook.io`いずれへも接続できず
   (`curl`で独立に確認、`CONNECT tunnel failed, 403`)。
2. `data-source-researcher`が得た情報は`WebSearch`合成Snippetのみに基づく
   `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`で、タスク上最重要の2項目
   (`DiscStatus`/`RevNo`の訂正・削除意味論、`DiscDate`/`DiscTime`のPIT意味論)
   いずれも裏付けゼロだった。
3. 検索結果が「J-Quants API」(個人向け、対象)と「J-Quants Pro」(法人向け、
   無関係な別契約)を混同していた可能性があり、候補Endpoint名自体の
   製品帰属すら確認できていない。

したがってこのGuideは「実装済みコードを検証する」手順ではなく、**「公式資料へ
実際にアクセスできる環境(ユーザーのローカル環境)で、まず仕様そのものを
確認し、その後、既存Adapterコードを一切経由しない最小限のRaw Probeで
実際のResponse形状を観測する」**ための手順である。ここで得られた結果を
持ち帰ってもらって初めて、次のRoundで`tdnet.py`の実装に着手できる。

## 目的(優先順位順)

1. **製品の切り分け**: `jpx-jquants.com`(または実際の正しいDocument Host)で、
   TDnet Add-onの仕様書が実際にどのURLにあるか、それが「J-Quants API」
   (個人向け)の一部であることを確認する。「J-Quants Pro」の資料と混同しない。
2. **タスク上最重要2項目の確認**: `DiscStatus`/`RevNo`が実際に何を表すか
   (訂正・削除がどう反映されるか)、`DiscDate`/`DiscTime`が実際に何の時刻を
   表すか(開示時刻なのか、取得時刻なのか、その他か)。
3. **Add-on契約状況の確認**: 現在のJ-Quantsプランに実際にTDnet Add-onが
   含まれているか(月額課金の要否含む)。**このGuideはAdd-on契約を要求する
   ものではない** — 契約していない場合はその旨をそのまま報告してもらえば良い
   (`TDNET_ARCHITECTURE.md` §7、`CODE_COMPLETE_AWAITING_ADDON_LOCAL_
   VALIDATION`として正常に停止する)。
4. **最小限のRaw Probe**(Add-on契約済みの場合のみ): 既存Adapterコードを
   一切経由しない、素の`requests`呼び出し1本で`/v2/td/list`相当の
   Endpointへ1回だけ問い合わせ、実際のResponse JSONのトップレベル構造を
   確認する。

## 原則(EDINET版から継続)

- **最初から大きく取得しない。** 1日分のみ。複数日・Bulk Downloadへの拡張は、
  この手順が成功し、ユーザーの明示的な指示があってから。
- **APIキーの値は絶対に画面に表示しない・貼り付けない。** 有無の確認のみ行う
  (既存の`JQUANTS_API_KEY`を再利用する想定 — TDnet Add-on専用の別キーが
  必要かどうか自体も未確認の項目の一つ)。
- PowerShellを使用する(Windows環境前提)。
- **このGuideの手順はいかなるAdapterコードも呼び出さない。**
  `lib/disclosures/providers/tdnet.py`は存在しないため、呼び出しようがない
  (誤って存在しない前提のコードを書かないこと自体がこの手順の設計目的)。

## A. 最新のブランチを同期する

```powershell
cd <リポジトリのパス>
git fetch origin claude/investment-strategy-pipeline-jyfby5
git checkout claude/investment-strategy-pipeline-jyfby5
git pull origin claude/investment-strategy-pipeline-jyfby5
```

## B. 製品の切り分け(まずコードを一切書かず、仕様書を人間の目で確認する)

以下を実際にブラウザで開いて確認してもらいたい(本セッションからは接続
できないため、この確認はユーザーのローカル環境でのみ可能):

1. J-Quants公式サイト(個人向けAPIの契約ページ)から、料金プラン一覧を開く。
   「TDnet」または「適時開示情報」という名前のAdd-onまたは含有Planが
   実在するか確認する。
2. そのAdd-on/Planの説明ページに実際にリンクされているAPI Referenceの
   URLをそのままコピーする(検索結果ではなく、公式サイトから実際に
   たどり着いたURLであることが重要)。
3. そのURLのDomain・Path構造が「J-Quants API」(個人向け)のDocument Tree
   に属することを、周辺のNavigation(メニュー・パンくずリスト)から確認する。
   「J-Quants Pro」という文言がどこかに出てきた場合は、それが個人向けとは
   別の資料である可能性が高いため、そのページのURLと文言をそのまま
   報告してほしい(このLabでは対象外と判断する材料になる)。

**ここで報告してほしいもの**: 実際にたどり着いたAPI Reference PageのURL、
そのPageに書かれているEndpoint Path(例のような形式の文字列、実際の値)、
「TDnet」という語がそのPage内でどう定義されているかの引用(1〜2文で
十分)。

## C. タスク上最重要2項目を仕様書で直接確認する

手順Bで見つけた実際のAPI Reference Pageの中から、以下を探して報告して
ほしい:

1. **`DiscStatus`(またはそれに相当するField)の説明文**: 「訂正」
   「削除」「取消」に類する語が定義に含まれているか。含まれている場合、
   そのFieldがTake得る値の一覧(公式に列挙されていれば)。
2. **`RevNo`(またはそれに相当するField)の説明文**: 何かの回数・番号を
   表すという説明があるか、それが「訂正回数」を意味すると明記されているか。
3. **`DiscDate`/`DiscTime`(またはそれに相当するField)の説明文**: これが
   「開示が行われた日時」なのか、「このLabがProviderから取得した日時」
   なのか、その他の意味なのか、公式な定義文をそのまま引用してほしい。
4. **認証方式**: リクエストヘッダの形式(例: `x-api-key: <key>`のような
   ヘッダ名か、`Authorization: Bearer <key>`のような形式か)。既存の
   J-Quants V2 Core API(`lib/data_sources/jquants.py`)は`x-api-key`
   ヘッダを使うことが確認済みだが、TDnet Add-onが同じ認証方式を再利用
   するかは**未確認**(推測にすぎない) — 仕様書に明記されていれば、
   それをそのまま引用してほしい。この項目を確認せずに手順Eを実行すると、
   ヘッダ形式の誤りによる401/403を「Add-on未契約」と誤解する可能性が
   ある(手順F参照)。

**この手順はRaw Probeより先に行うこと** — 実際にAPIを叩く前に、仕様書の
定義文そのものを確認できれば、それだけで`TDNET_SOURCE_ONBOARDING.md`の
最重要Unknownの一部が解消できる可能性がある。

## D. `JQUANTS_API_KEY`の有無確認(値は表示しない)

既存の`.env`に既に設定されている想定(EDINET Phase以前から使用している
既存Key)。念のため有無のみ再確認する:

```powershell
if ($env:JQUANTS_API_KEY) {
    "JQUANTS_API_KEY is set"
} else {
    "JQUANTS_API_KEY is NOT set"
}
```

TDnet Add-on専用の別Key・別Tokenが必要かどうかは、手順B/Cの仕様書確認で
分かる可能性がある(未確認)。もし別Keyが必要と分かった場合、その値も
この会話には絶対に貼り付けないこと。

## E. 最小限のRaw Probe(手順B/Cが完了し、Add-on契約が確認できた場合のみ)

**既存Adapterコードを一切経由しない。** 素の`requests`のみを使う理由は、
`lib/disclosures/providers/tdnet.py`が存在しないため(誤って存在しない
モジュールをimportしようとしない)。手順Bで確認した実際のURL・Path名に
書き換えてから実行すること — 以下はあくまで骨格であり、Endpoint Path・
Query Parameter名は**未確認のプレースホルダ**である:

```powershell
python -c "
from dotenv import load_dotenv
load_dotenv()
import os
import requests

api_key = os.environ.get('JQUANTS_API_KEY')
if not api_key:
    raise SystemExit('JQUANTS_API_KEY not set')

# 以下のURL・パラメータ名は手順B/Cで確認した実際の値に置き換えること。
# ここに書かれているものは未確認のプレースホルダであり、そのまま実行しても
# 失敗する可能性が高い。
url = '<手順Bで確認した実際のURL、例: https://api.jquants.com/v2/td/list>'
headers = {'Authorization': f'Bearer {api_key}'}
params = {'date': '2024-05-08'}  # 手順Bで確認した実際のParameter名に置き換える

resp = requests.get(url, headers=headers, params=params, timeout=30)
print('status_code:', resp.status_code)
print('content-type:', resp.headers.get('content-type'))
body_preview = resp.text[:2000]
print(body_preview)
"
```

**この手順の目的は1回だけの疎通確認であり、Raw Snapshotとしての保存や
Normalizeは行わない**(それは`tdnet.py`実装後の別Roundの仕事)。

## F. Add-on未契約時に想定される挙動(これが見えた場合の対応)

- HTTP 402/403のような明示的な課金関連のStatus Codeが返る可能性がある
  (未確認)。
- あるいはHTTP 200のままEmpty ResponseまたはError Bodyが返る可能性もある
  (EDINET Phase4B-2で発見した「HTTP 200がApplication Errorを隠す」
  パターンが、TDnet Add-onでも同様に起こりうることを念頭に置く — ただし
  これも現時点では未確認の懸念であり、確認された事実ではない)。
- いずれの場合も、これは**失敗ではなく想定される結果の一つ**である。
  この場合は「Add-on未契約と判断される挙動が確認された」とそのまま
  報告してもらえばよい。このLabはPhase4B-3を
  `CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`として正常に停止する
  (`TDNET_ARCHITECTURE.md` §7、`DECISIONS.md` D0047参照)。

## G. 何を貼り付けて報告してもらいたいか

- **貼り付けてほしいもの**:
  - 手順Bで実際にたどり着いたAPI Reference PageのURLとEndpoint Path。
  - 手順Cで確認した`DiscStatus`/`RevNo`/`DiscDate`/`DiscTime`の公式定義文
    (引用、1〜2文程度)。
  - 手順Eを実行した場合、`status_code`・`content-type`・Response本文の
    先頭2000文字程度(**Response内にAPIキーやToken文字列が含まれていない
    ことを目視確認してから**貼り付けること)。
  - Add-on契約状況(契約済み/未契約/確認できず、のいずれか)。
- **絶対に貼り付けないでほしいもの**: `JQUANTS_API_KEY`の値そのもの、
  `.env`ファイルの中身全体、Authorizationヘッダを含むRequest全体、
  Response内にAPIキー・Token・個人情報らしき値が含まれる場合はその部分を
  伏せ字にしてから貼り付けること。

## H. このGuideの手順が完了した後にできるようになること

このGuideの結果(特に手順B/Cで得られる公式定義文の引用)を持ち帰って
もらえれば、次のRoundで以下が可能になる:

1. `TDNET_SOURCE_ONBOARDING.md`の該当Unknown項目を`CONFIRMED-BY-OFFICIAL-
   SPEC`へ更新する。
2. 製品帰属(J-Quants API vs J-Quants Pro)の懸念が解消されていれば、
   EDINET Phase4B-2 Round 1と同水準の「Raw Fetchのみ・Normalizeなし」の
   `tdnet.py` Adapterを新規に実装できる。
3. Add-on契約状況が確認できていれば(契約済みの場合)、手順Eの実Response
   構造を踏まえて、`TDnetDocumentMetadata`のような Provider固有Metadata
   Classの設計に着手できる(このGuide自体はそこまでは行わない)。

Add-on未契約、または仕様書アクセスが依然として確認できない場合は、
その結果自体が有効な報告であり、Phase4B-3は
`CODE_COMPLETE_AWAITING_ADDON_LOCAL_VALIDATION`のまま次の指示を待つ。
