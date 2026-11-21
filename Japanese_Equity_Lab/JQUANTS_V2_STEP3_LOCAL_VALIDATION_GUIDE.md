# JQUANTS_V2_STEP3_LOCAL_VALIDATION_GUIDE.md — Step 3追加Field/Endpointのローカル疎通確認

`.claude/skills/local-validation/SKILL.md` の手順に従って生成(2026-11-22)。

対象は `JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §15 の7項目。**この手順では
Normalizer・Adapterを実装しない。** 観測結果を持ち帰ることが目的。

## なぜローカルで行うか

EDINET調査と違い、今回は公式ドキュメントにはクラウドセッションから到達できた。
しかし `api.jquants.com` への実リクエストはAPIキーが必要で、キーはローカルの
`.env` にしかない。**宣言Schema(仕様書)とObserved wire schema(実際の応答)は
別概念**であり、特に以下は仕様書だけでは決着しない。

- `ShEq`/`ROE` は2026年に追加されたFieldで、**過去の行に値が入っているかは
  仕様書に書かれていない**(最優先項目)
- REITの `/equities/valuation` 応答が本当に `MktCap` 以外すべてnullか
- 一株当たり指標が株式分割をまたいで連続するか(`MktCap` のみ調整すると明記)

## 原則

- **最初から大きく取得しない。** 1銘柄ずつ。全銘柄取得へ広げるのは、この手順が
  成功した後にオーナーの明示的な指示があってから
- **APIキーの値は絶対に画面に表示しない・貼り付けない。** 有無の確認のみ
- 新規Endpointも**必ず `_get_all_pages` を経由する。** `requests` で直接叩くと
  `_throttle()`(1.05秒間隔)を迂回し、ルートCLAUDE.md §5「レート制限を守る。
  新しい呼び出し箇所を追加する際もこれを経由すること」に違反する
- PowerShellを使用する(Windows環境前提)

---

## A. 最新のブランチを同期する

```powershell
cd C:\Users\白川正威\shoui-
git pull
cd Japanese_Equity_Lab
```

## B. `JQUANTS_API_KEY` の有無確認(値は表示しない)

```powershell
if ($env:JQUANTS_API_KEY) {
    "API key is set"
} else {
    "API key is NOT set (.env から読まれるので、Pythonからの実行なら未設定でも問題ない)"
}
```

このLabのスクリプトは `load_dotenv()` でリポジトリルートの `.env` を読むため、
PowerShellの環境変数が未設定でもPythonプロセス内では解決される。**`.env` の中身を
`Get-Content` で画面に出さないこと。**

## C. 最小Smoke Test —`ShEq`/`ROE` の過去行充填(最優先)

既存の公開メソッド `fetch_financial_statements` をそのまま使う。1銘柄のみ。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from datetime import date
from lib.data_sources.jquants import JQuantsAdapter

r = JQuantsAdapter().fetch_financial_statements(
    codes=['7203'], start_date=date(2015,1,1), end_date=date(2026,11,21))
rows = r.payload
print('records:', len(rows))
print('retrieved_at:', r.retrieved_at)
for f in ('ShEq','NCShEq','ROE','NCROE','BPS','ShOutFY','TrShFY','AvgSh','Eq','DivAnn','FDivAnn'):
    present = sum(1 for x in rows if str(x.get(f,'')).strip() != '')
    print(f'{f:10s} {present:3d}/{len(rows)}')
"@
```

次に、**いつから入っているか**を見る(これが本題)。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from datetime import date
from lib.data_sources.jquants import JQuantsAdapter

rows = JQuantsAdapter().fetch_financial_statements(
    codes=['7203'], start_date=date(2015,1,1), end_date=date(2026,11,21)).payload
for x in sorted(rows, key=lambda r: (r.get('DiscDate',''), r.get('DiscTime',''))):
    print(x.get('DiscDate'), x.get('CurPerType'),
          'ShEq=' + (str(x.get('ShEq','')).strip() or '-'),
          'ROE=' + (str(x.get('ROE','')).strip() or '-'),
          'BPS=' + (str(x.get('BPS','')).strip() or '-'))
"@
```

## D. Raw Snapshotとして保存する

既存の `RawSnapshotStore` を使う(新しい保存機構を作らない)。同一 `snapshot_id`
への再保存は拒否されるので、日付を入れる。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from datetime import date
from pathlib import Path
from lib.data_sources.jquants import JQuantsAdapter
from lib.snapshot import RawSnapshotStore

r = JQuantsAdapter().fetch_financial_statements(
    codes=['7203'], start_date=date(2015,1,1), end_date=date(2026,11,21))
store = RawSnapshotStore(Path('01_data/raw'))
m = store.save(r, snapshot_id='SNAP_JQ_STEP3_FINS_7203_20261122')
print('saved:', m.snapshot_id, 'records:', m.record_count)
print('hash:', m.content_hash[:16] + '...')
"@
```

**この保存には §3 で判明した意味がある。** `/fins/summary` は同一 `DiscNo` のまま
訂正されると行が上書きされ、訂正前の値は二度と取得できない。いま保存したSnapshotは
「2026-11-22時点で見えていた値」の唯一の記録になる。

## E. 保存されたRawを直接読む

```powershell
Get-ChildItem 01_data\raw\jquants\SNAP_JQ_STEP3_FINS_7203_20261122*
python -c @"
import json
d = json.load(open('01_data/raw/jquants/SNAP_JQ_STEP3_FINS_7203_20261122.json', encoding='utf-8'))
print('records:', len(d))
print('fields in first record:', len(d[0]))
print(sorted(d[0].keys()))
"@
```

`DocType` の集合も確認する(公式一覧42種に収まるか)。

```powershell
python -c @"
import json
d = json.load(open('01_data/raw/jquants/SNAP_JQ_STEP3_FINS_7203_20261122.json', encoding='utf-8'))
print(sorted({x.get('DocType') for x in d}))
"@
```

## F. 既存の読み取り専用スクリプトで確認する

専用の診断スクリプトはまだ無い。既存の `screen.py` を読み取り専用で流し、
正規化後の挙動が変わっていないことだけ確認する。

```powershell
python scripts/screen.py --codes 7203 --position-value 1000000 > step3_before.json
python -c @"
import json
d = json.load(open('step3_before.json', encoding='utf-8'))
print('unavailable:', d['unavailable']['metrics'])
print('per_share breaks:', len(d['entries'][0]['per_share_comparability']['breaks']))
"@
```

`unavailable.metrics` に `roe`/`pbr`/`dividend_yield` が並んでいるのが現状。
実装後にここが減るのが成功条件になる。

## G. ネットワークなしで再実行できることを確認する

保存したSnapshotだけから正規化が走るか(Offline原則、D0042)。

```powershell
python -c @"
import json
from datetime import UTC, datetime
from lib.fundamentals.normalize import parse_financial_summary_payload, raw_disclosure_date_range

d = json.load(open('01_data/raw/jquants/SNAP_JQ_STEP3_FINS_7203_20261122.json', encoding='utf-8'))
print('raw coverage:', raw_disclosure_date_range(d))
env, met = parse_financial_summary_payload(d, retrieved_at=datetime.now(UTC))
print('envelopes:', len(env), 'metrics:', len(met))
std = {e.accounting_standard for e in env}
print('accounting_standard values:', std)
"@
```

**`accounting_standard` に `None` が出るはず。** これが `*_Consolidated_US` が
未登録でfail closedしている証拠で、今回の作業で解消する対象。

## H. 新規Endpointの最小確認(`_get_all_pages` 経由)

Adapterに未実装の3Endpointを**調査目的でのみ**叩く。`_get_all_pages` を使うので
認証とスロットリングは既存実装のものが効く。**ここで得た結果をAdapterに実装する
のは次の工程。**

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from lib.data_sources.jquants import JQuantsAdapter

a = JQuantsAdapter()

v = a._get_all_pages('/equities/valuation', {'code': '7203'}, error_label='valuation')
print('valuation records:', len(v))
if v:
    print('fields:', sorted(v[0].keys()))
    print('oldest:', min(x['Date'] for x in v), 'newest:', max(x['Date'] for x in v))
    print('sample:', v[-1])

e = a._get_all_pages('/fins/earnings-date', {'code': '7203'}, error_label='earnings-date')
print('earnings-date records:', len(e))
if e:
    print('fields:', sorted(e[0].keys()))
    print('sample:', e[:2])
"@
```

REITで同じことをする(`ProdCat=013`。例として8951 日本ビルファンド)。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from lib.data_sources.jquants import JQuantsAdapter

a = JQuantsAdapter()
m = a.fetch_equities_master().payload
for row in m:
    if str(row.get('Code','')).startswith('8951'):
        print('ProdCat:', row.get('ProdCat'), row.get('CoName'), 'Mkt:', row.get('Mkt'))

v = a._get_all_pages('/equities/valuation', {'code': '89510'}, error_label='valuation')
print('REIT valuation records:', len(v))
if v:
    print('latest row:', v[-1])
"@
```

分割をまたぐ連続性(7203は2021年に基準が変わっている)。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from lib.data_sources.jquants import JQuantsAdapter

v = JQuantsAdapter()._get_all_pages(
    '/equities/valuation', {'code': '7203', 'from': '2021-09-25', 'to': '2021-10-08'},
    error_label='valuation')
for x in sorted(v, key=lambda r: r['Date']):
    print(x['Date'], 'EPS=', x.get('EPS'), 'BPS=', x.get('BPS'), 'PBR=', x.get('PBR'))
"@
```

### 併せて確認したいこと(仕様書との食い違い)

公式仕様の `/fins/summary` のパラメータ表は **`code` / `date` / `cursor` の3つ**で、
`from`/`to` は載っていない。しかしAdapterは `from`/`to` を送っている
(`jquants.py` の `fetch_financial_statements`)。これが「`from`/`to` を指定しても
全履歴が返る」という既存の実観測(D0043)の説明になっている可能性がある
——**送ったパラメータが無視されている**のではないか。

```powershell
python -c @"
from dotenv import load_dotenv
load_dotenv('../.env')
from lib.data_sources.jquants import JQuantsAdapter

a = JQuantsAdapter()
n1 = len(a._get_all_pages('/fins/summary', {'code': '7203'}, error_label='no-range'))
n2 = len(a._get_all_pages('/fins/summary', {'code': '7203', 'from': '2024-01-01', 'to': '2024-12-31'}, error_label='with-range'))
print('code only:', n1, '/ code+from+to:', n2, '/ same:', n1 == n2)
"@
```

---

## I. 期待される観測結果(自己チェック用)

成功していれば次が成り立つ。**成り立たない場合は設計が変わる**ので、その項目を
持ち帰る。

| # | 確認 | 期待 | 外れた場合 |
| --- | --- | --- | --- |
| 1 | `ShEq`/`ROE` の充填 | 過去行にも値がある | **最重要。** 直近のみなら10年ROE推移は出せず、`/equities/valuation` 一本化を再検討する |
| 2 | `BPS`/`ShOutFY`/`TrShFY`/`AvgSh`/`DivAnn` の充填 | 決算短信系の行で概ね埋まっている | 配当利回りの出し方が変わる |
| 3 | `accounting_standard` | `None` が混在する | `None` が無ければ、US GAAPのマッピングは既に効いている(想定外) |
| 4 | `DocType` 集合 | 公式42種の部分集合 | 一覧外の値があれば一覧は網羅的でない。D0043へ追記 |
| 5 | `/equities/valuation` 7203 | 11 Field、日次、`Date`の最古が2008〜2010年台 | Fieldが違えば仕様書と実装の差分として記録 |
| 6 | `/equities/valuation` REIT(8951) | `MktCap` 以外ほぼnull | nullでなければREITも valuation で扱える(方針が簡単になる) |
| 7 | `ProdCat`(8951) | `013` | 値が違えばルーティング条件を見直す |
| 8 | 分割前後のEPS/BPS | **どちらでもよいが、どちらかを確定させる。** 連続していれば調整済み、2021-10-01前後で段差があれば未調整 | 未調整なら `per_share.py` の対象に valuation 由来の指標も加える |
| 9 | `/fins/earnings-date` | レコードが返り、公表日と予定日に相当するFieldがある | 0件なら検索キーの指定方法を見直す |
| 10 | `from`/`to` の有無で件数比較 | **同数なら無視されている** | 同数でなければ絞り込みは効いている。D0043の記述を訂正する |
| 11 | 全体 | tracebackが出ない | 出たら全文(**キーの値を含む行は除く**)を持ち帰る |

`DiscDate` が要求期間の外にある行が返るのは**正常**(D0043の既知挙動)。

## 貼り戻してほしいもの

- **C の2つ目**(`ShEq`/`ROE`/`BPS` の年次一覧)— これが最優先の判断材料
- **G の `accounting_standard values`** の1行
- **H の3ブロックの出力**(valuation の Field一覧とREITの挙動、earnings-date の Field一覧)
- **I の表で期待から外れた項目**
- tracebackが出た場合はその全文

**APIキーの値を含む行は貼らないこと。** 上記のコマンドはいずれもキーを出力しない
が、tracebackにURLやヘッダが含まれる場合は該当行を削って貼ること。

件数や「期待どおり」だけで済む項目(I の 1〜11 のうち期待と一致したもの)は、
一致した旨だけで構わない。

## 保存したSnapshotの扱い

`01_data/raw/` 配下はimmutableなので、**コミットするかどうかは別判断**。
`period_usage_ledger.md` の対象ではない(検証期間の消費ではなく、現時点のSchema
観測であり、仮説検証に使っていない)。ただし§3のとおり訂正前の値を保持する唯一の
手段なので、**捨てないこと。**
