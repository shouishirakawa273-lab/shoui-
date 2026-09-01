"""Consensus/Expectations Inputs DatasetをPhase3D Data Catalogへ登録する
(Phase4E-4)。

`ImplementationStatus`(実装状況)と、このModuleが`known_limitations`へ
自由記述で記録するValidation Status(`DESIGN_COMPLETE_AWAITING_SPEC_
VERIFICATION`等)は別軸として明示する(Positioning Phase4C/Macro
Phase4D/Global Market Phase4E-1/News Phase4E-2〜3と同じ方針)。

**このRoundでAdapterを実装した候補は無い**。data-source-researcher Agent
(2026-08-19)がLSEG/Refinitiv I/B/E/S・Bloomberg BEst・FactSet
Estimates・S&P Capital IQ・Visible Alpha・QUICK・IFIS Japan・Nikkei
NEEDS/Compass・Alpha Vantageを調査したが、このSession自身のNetwork
Egressが全ての候補Provider Domainへ一貫してBlockされており
(`EGRESS_BLOCKED`)、GitHub上の2つの非公式クライアントコード(実際に
読めた、`VERIFIED_SECONDARY`)を除き全ての情報がSEARCH-SNIPPET-DERIVED
(UNVERIFIED)に留まった。検索Snippetのみを根拠にAdapterを実装しない
(Phase4E-4要件§9)。

## このRoundで登録した候補(2件)

Historical Vintage支持の明確さ・Japan Coverage・Timestamp Semanticsの
明確さを基準に(Phase4E-4要件§56)、Catalogが本来意図する「実装候補の
検索可能な一覧」(`lib.sources.catalog`モジュールDocstring参照)という
目的に沿う、個人ローカル実行という本LabのCLAUDE.md前提のもとで将来
接続しうる候補のみを登録する:

- `quick_consensus_japan`: data-source-researcher推奨順位1位(Japan
  Coverage最強の主張、Point-in-Time Consensus主張あり、個人向け製品Line
  [Qr1 Personal]の存在が示唆されるがConsensus自体がそこに含まれるかは
  未確認)。
- `ifis_japan_consensus`: Japan-domesticかつJP-GAAP特有の経常利益等を
  含む候補だが、PIT/Vintage主張自体が他候補より弱い(見つからなかった)。

**登録しなかった候補**: LSEG/Refinitiv I/B/E/S・Bloomberg BEst・
**FactSet Estimates Point-in-Time Consensus**・S&P Capital IQ・Visible
Alphaはいずれも明確にENTERPRISE専用と判断され(Terminal/Platform契約
前提)、個別Catalog Entryとしては登録せず`CONSENSUS_ARCHITECTURE.md`の
Source Landscape節で記録するに留める(skeptic-reviewer Finding、
Phase4E-4: FactSetのみ「Benchmark参照目的」という別基準でCatalog登録
していたが、これは他のENTERPRISE専用候補への除外基準と矛盾しており、
Catalog自体の目的[実装候補の一覧、恒久的Documentation参照用ではない]
とも合わない判断だったため、他のENTERPRISE専用候補と同じ扱いへ統一
した——FactSetのTimestamp Semantics記述自体の価値は失われておらず、
`CONSENSUS_ARCHITECTURE.md`のSource Candidate Landscape節でより詳細に
記録している)。Nikkei CompassはService終了(Discontinued)が確認された
ため候補から除外。Nikkei NEEDSはPIT主張自体が見つからず、そもそも実際
のSell-side Consensus Estimateを持つか(Derived Multipleのみの可能性)
不明のため登録を見送った。Alpha Vantageの`EARNINGS_ESTIMATES`Endpoint
はdata-source-researcher Agentが2つの独立したClient Code(1つはAlpha
Vantage公式Organizationの`alphavantage_mcp` README)を実際に読んだ結果、
その存在自体を確認できなかった(存在しない可能性が高い)——存在未確認
のEndpointを前提にしたCatalog登録はしない。
"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_quick_consensus_japan_dataset_descriptor() -> DatasetDescriptor:
    """QUICK Consensus(QUICKコンセンサス、QUICK Corp.、日本経済新聞社
    グループ)経由の日本株Analyst Consensus候補。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher Agentの調査では
    Japan Equity Coverageについて「2005年以降の中小型株を含む最も広い
    Coverage」という主張が見つかり、"point in time consensus data"という
    直接的な(ただし簡潔な)PIT主張もあった。Sales/Net Income/EPS/DPS/
    ROE/EBITDA等、EPS単独ではない広いMetric Setが示唆された。ただし
    Timestamp Semantics(Snapshot Cutoff時刻の定義)の詳細・"QUICK Data
    Factory"/"QUICK APIs"のAuthentication方式・個人向け製品Line
    ("Qr1 Personal")にConsensus Dataが含まれるか、いずれも未確認。
    """
    return DatasetDescriptor(
        dataset_id="quick_consensus_japan",
        source_id="quick",
        capability=DataCapability.EXPECTATIONS,
        authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、SEARCH-SNIPPET-DERIVED: Brokerの見積を日次で平均集計と示唆)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "UNKNOWN(likely PAID/institutional-oriented)。個人向け製品Line(Qr1 Personal)の存在は"
            "示唆されたが、QUICK Consensus自体がそこに含まれるか未確認。QUICK Data Factory/QUICK APIs"
            "は法人向けContract前提の可能性が高い(未確認)。"
        ),
        applicable_sectors=(),
        known_limitations=(
            "Historical Consensus Vintage問い合わせが真のAs-of-Date再構成なのか、単なる定期Archive"
            "Snapshotなのか区別できていない。Timestamp Semantics(Snapshot Cutoff時刻の定義)未確認。"
            "API/Auth方式・Wire Schema・License/Redistribution Terms、いずれも未確認。個人/自営業者が"
            "契約可能なTierの有無が最大の未解決論点(data-source-researcher自身が次の調査対象として"
            "最優先に指名)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter"
            "未実装、data-source-researcher推奨順位1位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-19、DECISIONS.md参照。",
    )


def build_ifis_japan_consensus_dataset_descriptor() -> DatasetDescriptor:
    """IFIS Japan(アイフィスジャパン)コンセンサス・データ・サービス経由の
    候補。

    **未実装(NOT_IMPLEMENTED)**。日本国内特化のProviderで、経常利益等
    JP-GAAP特有の科目を含む広いMetric Setが示唆された。ただしPIT/Vintage
    問い合わせについての主張自体が(QUICK/FactSetと異なり)見つからず、
    このLabの最重要関心事(Historical Vintage支持)について最弱の候補と
    なる。個人向け無料閲覧サイト("IFIS株予報")の存在が示唆されたが、
    仮に無料でもWeb Viewerであり構造化取得に適さない可能性が高く、
    Scraping前提のAdapterはこのLabの原則(§7、Structured Sourceを優先)
    に反するため検討しない。
    """
    return DatasetDescriptor(
        dataset_id="ifis_japan_consensus",
        source_id="ifis",
        capability=DataCapability.EXPECTATIONS,
        authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、SEARCH-SNIPPET-DERIVED)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="PAID、主に機関投資家・証券会社向けと示唆(個人向けTierの有無は未確認)。",
        applicable_sectors=(),
        known_limitations=(
            "Historical Consensus Vintage/PIT問い合わせについての主張自体が見つからず、QUICK/FactSet"
            "より弱い候補。Bulk Data Serviceの実際のWire Schema・API有無(Bulk/File配信のみの可能性)・"
            "License/Redistribution Terms、いずれも未確認。個人向け無料Web Viewer('IFIS株予報')の"
            "存在は示唆されたが構造化データ取得に適さない可能性が高く、Scraping前提の実装は検討しない。"
            "VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-19、DECISIONS.md参照。",
    )


__all__ = [
    "build_ifis_japan_consensus_dataset_descriptor",
    "build_quick_consensus_japan_dataset_descriptor",
]
