# Company IR ローカル疎通確認手順(Phase4B-4)

## 0. なぜこのRoundでLive Fetchを一度も試みなかったか(重要、EDINET/TDnetとの違い)

EDINET(D0046)・TDnet(D0047)のRoundでは、Main Claude自身がこのSession内で
`curl`を使い、公式API(`api.edinet-fsa.go.jp`・`jpx-jquants.com`)への
疎通可否を直接確認した(結果は`EGRESS_BLOCKED`)。今回のPhase4B-4では
**同様のLive接続確認を意図的に一度も行っていない**。理由:

EDINET/TDnetは金融庁・JPXが運営する制度的な公開APIであり、確認すべき対象は
「このSession自身のNetwork Egressが到達できるか」という単一の技術的事実
だった。一方Company IRは**個別企業ごとに異なるWebsite**であり、Fetchの
可否は接続性だけでなくCompliance(robots.txt・利用規約)に依存する
(Section 6「Compliance First」)。特定の実在企業のURLを1つでも選んで
`curl`することは、その企業のrobots.txt/利用規約を確認しないままの
Automated Retrievalに他ならず、このRound自身が課した原則
(`ComplianceCheckResult`が`ALLOWED`でなければFetchしない)に反する。

したがって、このGuideは**Fixture-based Validation(このRepository内で
完結)**のみをこのRound自身では実施し、実在するCompany IR URLに対する
Live Validationは、Userが個別に対象企業のrobots.txt/利用規約を確認した
上で、ローカル環境で行うことを前提とする(下記手順)。

## A. 最新のブランチを同期する

```powershell
git fetch origin claude/investment-strategy-pipeline-jyfby5
git checkout claude/investment-strategy-pipeline-jyfby5
git pull origin claude/investment-strategy-pipeline-jyfby5
```

## B. API Keyは無し、代わりにCompliance確認が必須の前提条件

Company IRは公開Web Pageへの通常のHTTP GETであり、APIキー等の認証情報は
不要(v1はLogin-required Sourceを扱わない、Section 19)。**その代わりに、
Fetchを行う前に対象企業のrobots.txt・利用規約を人間が確認することが
必須の前提条件**である。以下を確認してから進めること:

1. 対象URLの`robots.txt`(例: `https://ir.example.co.jp/robots.txt`)を
   ブラウザで直接開き、対象Pathが`Disallow`されていないか確認する。
2. 対象企業サイトの利用規約(多くの場合フッターの「利用規約」等から
   到達可能)を確認し、自動取得・保存・再配布についての制限が無いか
   確認する。
3. 上記いずれかが不明・曖昧な場合は、**Automated Retrievalを行わない**
   (Section 7、Fail Closed)。

## C. Compliance確認結果の記録 + 最小Smoke Test(1 URLのみ)

Step Bで実際に確認した結果を`ComplianceCheckResult`として明示的に構築し、
1つのURLのみFetchする(複数URL・全ページ巡回等への拡大は行わない)。

```powershell
python -c "
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from datetime import datetime, UTC
from lib.disclosures.providers.company_ir import CompanyIrAdapter, ComplianceCheckResult, ComplianceStatus

# Step Bで実際に確認した結果をそのまま反映すること(既定でALLOWEDにしない)。
compliance = ComplianceCheckResult(
    terms_checked=True,
    robots_checked=True,
    automated_retrieval=ComplianceStatus.ALLOWED,  # 実際にrobots.txt/利用規約を確認した場合のみALLOWED
    redistribution=ComplianceStatus.UNCLEAR,
    retention=ComplianceStatus.UNCLEAR,
    attribution_required=ComplianceStatus.NOT_CHECKED,
    checked_by='USER_MANUAL_REVIEW_<今日の日付>',
    checked_at=datetime.now(UTC),
    notes='<確認したrobots.txt/利用規約のURLや要点>',
)

adapter = CompanyIrAdapter()
result = adapter.fetch_document_raw('<実際に確認した1件のURL>', compliance=compliance)
print('SUCCESS')
print('final_url:', result.payload['final_url'])
print('http_status:', result.payload['http_status'])
print('content_length_observed:', result.payload['content_length_observed'])
print('raw_retrieval_hash:', result.payload['raw_retrieval_hash'])
"
```

**`automated_retrieval`をALLOWED以外(UNCLEAR/DISALLOWED/NOT_CHECKED)に
した場合、`ComplianceError`が送出されFetchが実行されない(Fail Closed、
意図した動作)。**

## D. Raw Snapshotとして保存する

```powershell
python -c "
import sys
sys.path.insert(0, 'Japanese_Equity_Lab')
from pathlib import Path
from datetime import datetime, UTC
from lib.disclosures.providers.company_ir import CompanyIrAdapter, ComplianceCheckResult, ComplianceStatus
from lib.snapshot import RawSnapshotStore

compliance = ComplianceCheckResult(
    terms_checked=True, robots_checked=True,
    automated_retrieval=ComplianceStatus.ALLOWED,
    redistribution=ComplianceStatus.UNCLEAR, retention=ComplianceStatus.UNCLEAR,
    attribution_required=ComplianceStatus.NOT_CHECKED,
    checked_by='USER_MANUAL_REVIEW_<今日の日付>', checked_at=datetime.now(UTC),
    notes='<確認内容>',
)
adapter = CompanyIrAdapter()
result = adapter.fetch_document_raw('<実際に確認した1件のURL>', compliance=compliance)

store = RawSnapshotStore(Path('Japanese_Equity_Lab/01_data/raw'))
manifest = store.save(result, snapshot_id='company_ir_smoke_test_1')
print('saved:', manifest.local_file)
"
```

## E. 保存したRawファイルを直接確認する(正規化前の生の形を見る)

```powershell
Get-Content Japanese_Equity_Lab/01_data/raw/COMPANY_IR/company_ir_smoke_test_1.manifest.json
```

`request_parameters`が`{"requested_url": "..."}`のみであり、認証情報や
Cookie等が一切含まれていないことを目視確認すること。

## F. 診断Script

Company IR専用の診断Script(EDINETの
`scripts/jquants_financial_summary_diagnostic.py`相当)は、このRoundでは
作成していない(Known Limitation、下記参照)。Step Eの`Get-Content`が
現時点での唯一のRaw確認手段である。

## G. Offlineでの再実行(ネットワーク接続なし)

```powershell
python -c "
import sys, json
sys.path.insert(0, 'Japanese_Equity_Lab')
from pathlib import Path
from datetime import datetime, UTC
from lib.snapshot import RawSnapshotStore
from lib.disclosures.providers.company_ir_normalize import build_company_ir_document
from lib.disclosures.evidence import disclosure_document_to_evidence
from lib.sources.catalog import SourceAuthorityClass

store = RawSnapshotStore(Path('Japanese_Equity_Lab/01_data/raw'))
_manifest, payload = store.load('COMPANY_IR', 'company_ir_smoke_test_1')

document, metadata = build_company_ir_document(
    payload,
    internal_document_id='DOC_SMOKE_1',
    title='<対象PageのTitleを人間が確認して入力>',
    retrieved_at=datetime.fromisoformat(_manifest.retrieved_at),
)
print('document_kind:', document.document_kind)
print('market_public_at:', document.market_public_at)
print('provider_available_at:', document.provider_available_at)

evidence = disclosure_document_to_evidence(document, source_authority_class=SourceAuthorityClass.COMPANY_PRIMARY)
print('evidence.content:', evidence.content)
print('evidence.source.available_at:', evidence.source.available_at)
"
```

このStepはNetwork呼び出しを一切行わない(保存済みSnapshotのみから
再実行できることを確認する、Offline Reproducibility原則)。

## H. 想定される観測結果(これが見えれば疎通成功)

- Step Cで`SUCCESS`が表示され、`http_status`が200番台であること。
- Step Dで`saved: COMPANY_IR/company_ir_smoke_test_1.json`のような
  Pathが表示されること。
- Step Eで`request_parameters`が`requested_url`のみを含み、他のKeyが
  無いこと。
- Step Gで`document_kind: DocumentKind.UNKNOWN`
  (常にUNKNOWN、自動分類はしない設計)、`market_public_at: None`
  (明示的に渡さない限り)、`provider_available_at: None`(常にNone)が
  表示されること。
- Step Gで`evidence.content`にbullish/buy/好調等の解釈語が含まれない
  こと。

## I. 何を貼り付けて報告してもらいたいか

- **貼り付けてほしいもの**: Step Cの`SUCCESS`行以降の出力、Step Hの
  各項目が実際に一致したかどうか。
- **絶対に貼り付けないでほしいもの**: `requested_url`/`final_url`に
  もしSigned URL等が含まれていた場合はそのURL全体(Query Parameter部分。
  ただし本Adapterは認証情報らしきQuery Parameterを含むURLを
  Compliance判定前にFail Closedで拒否するため、通常は発生しない)。

## J. Local Live Validation Round(2026-08-18)でのEgress確認結果

Userから改めてLocal Live Validation Roundの開始指示があった際、実際の
Company IR URLへFetchを試みる前に、このSession自身のNetwork Egress
可否を先に`curl`で確認した(D0046/D0047のEDINET/TDnetと同じ手順)。
`https://www.google.com/`・Live Validation Candidateとして検討していた
`https://global.toyota/en/robots.txt`のいずれも`CONNECT tunnel failed,
response 403`(組織のEgress Policyによる拒否)であり、既知にAllowlist
された`https://pypi.org/`は成功した。Agent Proxy自身の`/__agentproxy/
status`も同じ`connect_rejected`Failureを記録しており、特定のCompany
IR Siteの問題ではなくこのSession自体が任意の外部Host(Company IR
Domain含む)へ技術的に到達できないことを確認した(`EGRESS_BLOCKED`)。
Agent Proxy自身のTroubleshooting Docが「Policy拒否はRetry/回避策を
試みず報告すること」と明記しているため、これ以上の接続試行(別経路での
回避含む)は行っていない。したがって本節時点でもStep C以降(Live
Fetch・Raw保存・Offline再実行)は一度も実行できていない。詳細は
`DECISIONS.md`「D0053 追記」参照。

## Known Limitations(このRound時点)

- 実在のCompany IR Websiteへ、このSession(Claude Cloud環境)からも
  Userのローカル環境からも、Live Fetchを一度も実施していない
  (`implementation_status=SKELETON`のまま)。このSessionからのEgress
  自体が組織Policyにより一貫してBlockされることを2026-08-18に`curl`で
  直接確認済み(§J参照、EDINET/TDnetと同じ`EGRESS_BLOCKED`)。
- Company IR専用の診断Script(Step F)は未作成。
- Compliance確認(robots.txt/利用規約)は、このLab自身が自動解析する
  仕組みを持たない(意図的な設計判断)。したがって、どの企業が実際に
  Automated Retrievalを許可しているかの一覧・DatabaseもこのLabは
  持たない(1社ごとにUserが個別に確認する)。
- Historical PIT Reconstructionはできない(Section 15): 今Company IR
  Pageを取得しても、そのPDFが過去のある時刻から実際にWebsite上で取得
  可能だったことを遡って証明できない。
