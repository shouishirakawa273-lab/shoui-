"""Global Market DatasetをPhase3D Data Catalogへ登録する(Phase4E-1)。

`ImplementationStatus`(実装状況)と、このModuleが`known_limitations`へ
自由記述で記録するValidation Status(`DESIGN_COMPLETE_AWAITING_SPEC_
VERIFICATION`等)は別軸として明示する(Macro Phase4D/Positioning Phase4C
と同じ方針。そのためだけの`DatasetDescriptor`Schema変更は行わない)。

**このRoundでAdapterを実装した候補は無い**。data-source-researcher Agent
(2026-08-18)による調査の結果、FRED(米セントルイス連銀)・ECB(Frankfurter
経由)・CBOE・US Treasuryいずれも公式仕様へこのSessionから接続できず
(`EGRESS_BLOCKED`、`EDINET_SOURCE_ONBOARDING.md`と同じ制約)、全ての情報が
SEARCH-SNIPPET-DERIVED(UNVERIFIED)に留まった。検索Snippetのみを根拠に
Adapterを実装しない(Phase4E-1要件§8)。

research Agentは「FRED(単一APIキーでEquity Index/FX/Rate/Volatilityを
横断できるUmbrella候補、かつFRED/ALFREDのVintage Query機構がPIT観点で
最も有望)」を最優先候補として推奨した。ここではその推奨順位に沿って、
Equity Index(SP500)・FX(USDJPY・EURUSD)・Rate(US10Y)・Volatility(VIX)の
4カテゴリ・5候補をCatalogへ記録する。Commodity(WTI/Brent/Gold/Copper)は
研究Agent自身の推奨でも次Round以降に見送られており、ここでは登録しない。
"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_fred_sp500_dataset_descriptor() -> DatasetDescriptor:
    """FRED `SP500`(S&P 500 Price Index)経由の米国株価指数候補。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher Agentの調査では
    Equity Index候補の中で最も強く裏付けられた(REST API・無料APIキー
    登録Flow、複数の独立した検索結果が同じ「Price Index、Total Returnでは
    ない」という記述に収斂)候補だったが、Wire Schema・実際のTimestamp
    Field意味論・Rate Limitいずれも未読のまま(EGRESS_BLOCKED)。**FRED/
    SPDJI間の2014年Licensing Agreementにより過去10年分のRolling Window
    にしか公式にはアクセスできない**という、これまでのLab Sourceには
    無かった制約が複数Snippetで収斂しており、これは実装判断そのものを
    左右しうる制約として特筆する。Total Return版(`SP500TR`)がFRED上に
    存在するかはUNCONFIRMED。
    """
    return DatasetDescriptor(
        dataset_id="fred_sp500",
        source_id="fred",
        capability=DataCapability.GLOBAL_MARKET,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、Session Closeベースと推定)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US",),
        cost_or_plan_dependency="無料APIキー登録が必要(推定、未検証)。",
        known_limitations=(
            "Wire Schema・実際のTimestamp Field意味論(market_public_at相当の有無)・Rate Limit、"
            "いずれも未確認。FRED/S&P Dow Jones Indices間の2014年Licensing Agreementにより過去10年分の"
            "Rolling Windowにしか公式にはアクセスできないという制約が複数独立Snippetで収斂しているが、"
            "未読のまま(PIT/Backtest上の重大な制約になりうる)。Price IndexとTotal Return(`SP500TR`)の"
            "FRED上の存在有無・区別も未確認。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_"
            "VERIFICATION(Adapter未実装、data-source-researcher推奨順位1位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_fred_dexjpus_dataset_descriptor() -> DatasetDescriptor:
    """FRED `DEXJPUS`(USD/JPY、Federal Reserve H.10由来)経由のFX候補。

    **未実装(NOT_IMPLEMENTED)**。「NY市場正午時点のBuying Rate」という
    歴史的記述と、2019年2月のH.10 Trade-Weighted Index算出方法変更という
    別のSnippetが見つかったが、DEXJPUS自体の現在のSourcing/Cutoff時刻が
    この変更の影響を受けているかは未確認。Equity Close(16:00 Local)と
    同じSemanticsを強制してはならない(Phase4E-1要件§14)ため、実装時は
    FX固有のResolverを別途設計する必要がある。
    """
    return DatasetDescriptor(
        dataset_id="fred_dexjpus",
        source_id="fred",
        capability=DataCapability.GLOBAL_MARKET,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(営業日、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US", "JP"),
        cost_or_plan_dependency="無料APIキー登録が必要(推定、未検証)。",
        known_limitations=(
            "「NY市場正午時点のBuying Rate」という歴史的記述(H.10)と、2019年2月のH.10 Trade-Weighted"
            "Index算出方法変更という別Snippetが見つかったが、DEXJPUSの現在のSourcing/Cutoff時刻自体への"
            "影響は未確認。市場実勢Rate(Traded FX)とOfficial Reference Rateの区別を維持したまま扱う"
            "必要がある(Phase4E-1要件§17)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_"
            "VERIFICATION(Adapter未実装、data-source-researcher推奨順位2位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_fred_dexuseu_dataset_descriptor() -> DatasetDescriptor:
    """FRED `DEXUSEU`(EUR/USD、Federal Reserve H.10由来)経由のFX候補。

    **未実装(NOT_IMPLEMENTED)**。`DEXJPUS`と同型のTimestamp Semantics上の
    未確認事項を持つ。EUR/JPYはFRED上に直接系列が無く、実装する場合は
    DEXUSEU×DEXJPUSのCross Rate計算が必要になるが、これは他の値からの
    推測禁止原則(ルートCLAUDE.md)に抵触しないよう、実装するなら明示的な
    Derived Value Pipelineとして設計し、Providerの一次値と同列に扱わない。
    """
    return DatasetDescriptor(
        dataset_id="fred_dexuseu",
        source_id="fred",
        capability=DataCapability.GLOBAL_MARKET,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(営業日、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US", "EU"),
        cost_or_plan_dependency="無料APIキー登録が必要(推定、未検証)。",
        known_limitations=(
            "DEXJPUSと同型のTimestamp Semantics未確認事項を持つ。EUR/JPYはFRED上に直接系列が無く、"
            "実装する場合はDEXUSEU×DEXJPUSのCross Rate計算が必要になる——これは明示的なDerived Value"
            "Pipelineとして設計する必要があり、Providerの一次値と同列に扱ってはならない(数値を他の値から"
            "計算・推測しないというルートCLAUDE.md原則)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_"
            "SPEC_VERIFICATION(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_fred_dgs10_dataset_descriptor() -> DatasetDescriptor:
    """FRED `DGS10`(US 10年国債Constant Maturity Yield)経由の金利候補。

    **未実装(NOT_IMPLEMENTED)**。FRED配信の由来は米財務省(Office of Debt
    Management)の公式Par Yield Curveであり、NY連銀がおよそ15:30 US
    Eastern時点のBid-side気配値を取得して算出するという具体的な公表
    Timing記述が見つかったが、Treasury自身のページからは未読。過去の
    個別日次値がSilent Restateされるかは未確認(Methodology変更の記録は
    あるが、個別値のRevisionとは別概念として扱う)。
    """
    return DatasetDescriptor(
        dataset_id="fred_dgs10",
        source_id="fred",
        capability=DataCapability.GLOBAL_MARKET,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(営業日、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US",),
        cost_or_plan_dependency="無料APIキー登録が必要(推定、未検証)。",
        known_limitations=(
            "米財務省がおよそ15:30 US Eastern時点のBid-side気配値から算出するという公表Timing記述が"
            "見つかったが未読のまま。過去の個別日次値がSilent Restateされるか(Methodology変更の記録とは"
            "別概念)は未確認。Official Treasury Par Yieldと市場実勢Yield・政策金利(Fed Funds Rate等)を"
            "混同しない設計が必要(Phase4E-1要件§16)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_"
            "VERIFICATION(Adapter未実装、data-source-researcher推奨順位3位、home.treasury.govとの"
            "Cross-Check未実施)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_fred_vixcls_dataset_descriptor() -> DatasetDescriptor:
    """FRED `VIXCLS`(CBOE Volatility Index, Close)経由のVolatility候補。

    **未実装(NOT_IMPLEMENTED)**。CBOEが原典(Originating Source)、FREDは
    配信層(Delivery Provider)である(`SOURCE-004`原則、D0042)。CBOEの
    Regular Trading Hours算出Windowは9:30am-4:15pm ET(=Closeは4:15pm ET
    であり、Equity市場の4:00pm Closeとは異なる)という具体的な差異が
    見つかったが未読のまま。
    """
    return DatasetDescriptor(
        dataset_id="fred_vixcls",
        source_id="fred",
        capability=DataCapability.GLOBAL_MARKET,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、Close値)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US",),
        cost_or_plan_dependency="無料APIキー登録が必要(推定、未検証)。",
        known_limitations=(
            "原典(CBOE)と配信層(FRED)を分離して記録する必要がある(SOURCE-004原則)。CBOEのRegular"
            "Trading Hours算出Windowは9:30am-4:15pm ETであり、Closeは4:15pm ET——Equity市場の4:00pm"
            "Closeとは異なる——という具体的な差異が見つかったが未読のまま。CBOE自身の一次データ・"
            "Methodology PDFいずれも未取得。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_"
            "VERIFICATION(Adapter未実装、data-source-researcher推奨順位4位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )
