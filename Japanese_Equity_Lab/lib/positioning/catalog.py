"""Positioning/需給DatasetをPhase3D Data Catalogへ登録する(Phase4C)。

`ImplementationStatus`(実装状況)と、このModuleが`known_limitations`/`notes`へ
自由記述で記録するValidation Status(FIXTURE_VALIDATED/LOCAL_VALIDATED/
LIVE_VALIDATED/PENDING/EGRESS_BLOCKED等)は別軸として明示する(Phase4C要件
§25、そのためだけの`DatasetDescriptor`Schema変更は行わない — 既存Freeform
Text Fieldで十分と判断)。未検証SourceをLIVE_VALIDATEDと記録しない。
"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_price_derived_liquidity_dataset_descriptor() -> DatasetDescriptor:
    """Price/Volume-derived Positioning Metric(`lib.positioning.derived.
    price_derived`)のCatalog登録情報。

    `implementation_status=CONNECTED`: このModule自体はNetwork I/Oを一切
    行わない純粋関数(`lib.schemas.price_data.RawOHLCVBar`/
    `AdjustedOHLCVBar`という、既にCONNECTED状態のJ-Quants Price Bar
    Connectionから導出された既存Dataのみを入力とする)。したがって「未実装」
    ではなく「常時利用可能」という意味でCONNECTEDとする(Adapter骨格のみで
    実接続が無いSKELETONとは異なる)。

    Validation Status(自由記述): `FIXTURE_VALIDATED`(合成Bar Dataによる
    決定論的Formula検証のみ、このRoundでは実J-Quants Priceに対するEnd-to-End
    Local Validationは実施していない — 上流のRawOHLCVBar/AdjustedOHLCVBar
    自体は既存CONNECTED実績があるため、上流のReal Dataとの疎通確認は既に
    別Phaseで完了済み、`DATA_SOURCE_ARCHITECTURE.md`参照)。
    """
    return DatasetDescriptor(
        dataset_id="price_derived_liquidity",
        source_id="PRICE_DERIVED",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.CONNECTED,
        update_frequency="Daily(取引日ごと)",
        pit_available=True,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="追加コスト無し(既存J-Quants Price Bar Connectionを再利用、新規契約不要)",
        known_limitations=(
            "高度なSignal化(Short Squeeze Score等)は行わない、記述統計(売買代金・"
            "移動平均出来高)のみ。market_public_atはこのSourceでは構造的に一切"
            "設定されない(常にNone/UNKNOWN、価格Barの取引そのものに個別の公表時刻"
            "という概念が無いため)。available_atは東証大引け時刻からのINFERRED"
            "(session_close_at、公式に観測されたExact Timestampではない)。"
            "VALIDATION_STATUS=FIXTURE_VALIDATED(合成Bar Dataでの検証のみ、"
            "このRoundでは未実施)。"
        ),
        notes="normalizer_version=POSITIONING_PRICE_DERIVED_NORMALIZER_V1(lib.positioning.model.NORMALIZER_VERSION_PRICE_DERIVED)",
    )


def build_jquants_weekly_margin_interest_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/weekly_margin_interest`(銘柄別信用取引週末残高)候補。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher Agentによる調査
    (2026-08-18)の結果、全ての情報がWebSearch由来のSEARCH-SNIPPET-DERIVED
    (UNVERIFIED)であり、公式Documentを直接読めていない(このSession自身の
    Egressが公式Doc URLへ一貫してBlockされているため、`EDINET_SOURCE_
    ONBOARDING.md`と同じ制約)。Standard Plan以上が必要という情報が複数の
    独立した検索結果で一致しているが、このLabの現在の契約はLight Plan
    (ユーザー申告)であるため、契約変更なしでは利用不可の可能性が高い。
    Publication Lag(週末という観測期間終了日から、実際にAPIで参照可能に
    なるまでの遅延)を示す情報が一切見つかっておらず、これはPIT実装上
    致命的なGapである。VALIDATION_STATUS=PENDING(Adapter未実装)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_weekly_margin_interest",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Weekly(未確認、SEARCH-SNIPPET-DERIVED)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "Standard Plan以上が必要という情報あり(SEARCH-SNIPPET-DERIVED、複数の独立した検索結果で"
            "一致、未検証)。現在の契約はLight Plan(ユーザー申告)であり利用可能かどうか未確認。"
        ),
        known_limitations=(
            "Field名・Wire Schema未確認。Publication Lag(週末からAPI利用可能までの遅延)不明。"
            "Revision/訂正の表現方法(PublishedDate等)は同カテゴリの別Endpoint(daily_margin_"
            "interest)向けの記述からの類推のみで、この銘柄別週次Endpoint自体では未確認。"
            "Endpoint Path自体も公式Documentで直接確認できていない(WebSearch snippet由来)。"
            "VALIDATION_STATUS=PENDING(Adapter未実装、Local Validation未実施)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_jquants_short_ratio_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/short-ratio`(業種別空売り比率、旧`/v1/markets/short_selling`)候補。

    **未実装(NOT_IMPLEMENTED)**。業種別(個別銘柄ではない)の空売り売買代金
    比率。個別銘柄のPositioning Researchには`jquants_short_sale_report`
    (下記)の方が直接的だが、こちらは業種横断の需給概況として別途価値が
    ありうる。上記`weekly_margin_interest`と同じくSEARCH-SNIPPET-DERIVED
    (UNVERIFIED)のみ、Standard Plan以上が必要という情報あり。
    """
    return DatasetDescriptor(
        dataset_id="jquants_short_ratio",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、SEARCH-SNIPPET-DERIVED)",
        pit_available=False,
        applicable_codes=None,
        applicable_sectors=(),
        applicable_countries=("JP",),
        cost_or_plan_dependency="Standard Plan以上が必要という情報あり(SEARCH-SNIPPET-DERIVED、未検証)。",
        known_limitations=(
            "業種(33業種区分)単位の集計であり個別銘柄Positioningではない。Field名・"
            "Wire Schema・Publication Lag未確認。Endpoint Pathも未検証。"
            "VALIDATION_STATUS=PENDING(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_jquants_short_sale_report_dataset_descriptor() -> DatasetDescriptor:
    """個別銘柄空売り残高報告(Endpoint Path未確定、`/markets/short-sale-report`
    または`/markets/short_selling_positions`の可能性、いずれも未検証)候補。

    **未実装(NOT_IMPLEMENTED)**。空売り残高割合0.5%以上の場合に報告される
    個別銘柄Positioning Dataであり、Phase4C候補の中では最もPositioning
    Research Questionに直結しうる。ただしEndpoint Path自体が2つの独立した
    検索結果で一致していない(未解決の矛盾、`EDINET_SOURCE_ONBOARDING.md`の
    `type`Parameter矛盾と同種の扱い)。`calc_date`(計算日)と`disc_date`
    (開示日)が別々に存在する可能性が示唆されており、これ自体はPublication
    Lagの存在を示す有望な手がかりだが、実際のLag日数は未確認。
    """
    return DatasetDescriptor(
        dataset_id="jquants_short_sale_report",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Event-driven(報告都度、報告が無い日は提供されない、SEARCH-SNIPPET-DERIVED)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="Standard Plan以上が必要という情報あり(SEARCH-SNIPPET-DERIVED、未検証)。",
        known_limitations=(
            "Endpoint Path未確定(2つの独立した検索結果が矛盾: `/markets/short-sale-report`"
            "と`/markets/short_selling_positions`)。Field名・Wire Schema未確認。"
            "calc_date(計算日)とdisc_date(開示日)の関係(Publication Lagの実際の日数)"
            "が未確認。VALIDATION_STATUS=PENDING(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_jquants_trades_spec_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/trades_spec`(投資部門別売買状況)候補。

    **未実装(NOT_IMPLEMENTED)**。Phase4C候補の中で唯一、現在の契約
    (Light Plan)で利用可能である可能性が示唆された(単一の未検証Search
    Snippetのみ、複数情報源での裏付け無し)。Revision表現(同一Section/
    StartDate/EndDateキーに対しPublishedDateが異なる複数Recordが存在し、
    新しいPublishedDateが訂正後Data)についても、Phase4Cで扱う3候補の中では
    最も具体的な手がかりが見つかったが、いずれも未検証。次のLocal
    Validation候補として最優先(data-source-researcher Agentの推奨)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_trades_spec",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Weekly(未確認、SEARCH-SNIPPET-DERIVED)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "Light Plan(現在の契約)で利用可能という情報あり。ただし単一の未検証Search Snippet"
            "のみで裏付けが無く、他3候補(Standard Plan以上、複数Snippetで一致)とは信頼度が"
            "異なる。認証済みDashboard確認またはローカル環境での実接続確認が必要。"
        ),
        known_limitations=(
            "Field名・Wire Schema未確認。Publication Lag(週区分から実際のAPI利用可能時刻までの"
            "遅延)未確認。Revision表現(PublishedDate)の存在が示唆されているが未検証。"
            "VALIDATION_STATUS=PENDING(Adapter未実装、Local Validationで最優先候補)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )
