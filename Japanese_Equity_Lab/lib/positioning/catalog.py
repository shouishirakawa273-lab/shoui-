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
    """`/v2/markets/margin-interest`(銘柄別信用取引週末残高)。

    **ENDPOINT_CONFIRMED、実装は引き続きNOT_IMPLEMENTED**。JQS-STD-01
    (2026-09-08、DECISIONS.md参照)のRead-Only Live Probeで`code`+`from`/`to`
    指定により200・Field名(`Date`/`Code`/`ShrtVol`/`LongVol`/`ShrtNegVol`/
    `LongNegVol`/`ShrtStdVol`/`LongStdVol`/`IssType`等)を直接確認した。旧
    `/v2/markets/weekly_margin_interest`という推測PathはSEARCH-SNIPPET-DERIVED
    (UNVERIFIED)の誤りで、実際は403「Endpoint自体が存在しない」であることを
    JQS-STD-01で確認済み(この記述はDECISIONS.mdの過去の誤り記録を書き換える
    ものではなく、新しい確認結果として追記する)。Publication Lag(週末という
    観測期間終了日から実際にAPIで参照可能になるまでの遅延)・Revision表現・
    PIT安全な`available_at`導出方法は未確認のまま。VALIDATION_STATUS=
    ENDPOINT_CONFIRMED/IMPLEMENTATION_PENDING/PIT_PENDING(Adapter・
    Normalizer・EvidenceRecord化は未着手)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_weekly_margin_interest",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Weekly(Field名からの推定、Publication Lag未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "現在の契約(JQS-STD-01確認時点)でEndpoint自体への疎通・200 Responseを確認済み。"
            "どの契約Plan以上で必要かという境界自体は未確認(現在の契約より下位のPlanでも"
            "利用可能かは未検証)。"
        ),
        known_limitations=(
            "Endpoint PathはJQS-STD-01で200確認済み(ENDPOINT_CONFIRMED)。Field名は最小限"
            "確認したが、Wire Schema全体・Publication Lag(週末からAPI利用可能までの遅延)・"
            "Revision/訂正の表現方法は未確認。VALIDATION_STATUS=IMPLEMENTATION_PENDING/"
            "PIT_PENDING(Adapter未実装、Local Validation未実施)。"
        ),
        notes=(
            "Source Candidate Research: data-source-researcher Agent 2026-08-18。"
            "Path確認: JQS-STD-01(2026-09-08)、DECISIONS.md参照。"
        ),
    )


def build_jquants_margin_alert_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/margin-alert`(日々公表銘柄・信用取引残高高水準Alert)。

    **ENDPOINT_CONFIRMED、実装は引き続きNOT_IMPLEMENTED**。JQS-STD-01
    (2026-09-08、DECISIONS.md参照)のRead-Only Live Probeで`code`必須Parameter
    であることと200 Responseを確認した(Probe対象銘柄・期間ではAlert 0件
    だったため、実際のRecord Field名までは確認できていない)。旧Catalogには
    このDatasetの候補記述自体が存在しなかった(JQS-STD-01Aで新規追加)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_margin_alert",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(未確認、Endpoint名からの推定)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="現在の契約(JQS-STD-01確認時点)でEndpoint自体への疎通・200 Responseを確認済み。",
        known_limitations=(
            "Endpoint PathはJQS-STD-01で200確認済み(ENDPOINT_CONFIRMED、`code`必須)。"
            "Probe対象銘柄・期間ではAlert 0件だったため、実際のRecord Field名(Wire Schema)は"
            "未確認。Publication Lag・Revision表現も未確認。VALIDATION_STATUS=IMPLEMENTATION_"
            "PENDING/PIT_PENDING(Adapter未実装、Local Validation未実施)。"
        ),
        notes="Path確認: JQS-STD-01(2026-09-08)、DECISIONS.md参照。",
    )


def build_jquants_short_ratio_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/short-ratio`(業種別空売り比率)。

    **ENDPOINT_CONFIRMED、実装は引き続きNOT_IMPLEMENTED**。業種別(個別銘柄
    ではない)の空売り売買代金比率。個別銘柄のPositioning Researchには
    `jquants_short_sale_report`(下記)の方が直接的だが、こちらは業種横断の
    需給概況として別途価値がありうる。JQS-STD-01(2026-09-08、DECISIONS.md
    参照)のRead-Only Live Probeで`date`必須Parameterであることと200・Field名
    (`Date`/`S33`/`SellExShortVa`/`ShrtWithResVa`/`ShrtNoResVa`)を直接確認した。
    旧記述の「`/v1/markets/short_selling`」という旧Version参照は削除する
    (実際に確認できたPathは`/v2/markets/short-ratio`のみ)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_short_ratio",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Daily(Field名からの推定、Publication Lag未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_sectors=(),
        applicable_countries=("JP",),
        cost_or_plan_dependency="現在の契約(JQS-STD-01確認時点)でEndpoint自体への疎通・200 Responseを確認済み。",
        known_limitations=(
            "業種(33業種区分)単位の集計であり個別銘柄Positioningではない。Endpoint PathはJQS-"
            "STD-01で200確認済み(ENDPOINT_CONFIRMED)。Field名は最小限確認したが、Wire Schema"
            "全体・Publication Lagは未確認。VALIDATION_STATUS=IMPLEMENTATION_PENDING/"
            "PIT_PENDING(Adapter未実装)。"
        ),
        notes=(
            "Source Candidate Research: data-source-researcher Agent 2026-08-18。"
            "Path確認: JQS-STD-01(2026-09-08)、DECISIONS.md参照。"
        ),
    )


def build_jquants_short_sale_report_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/markets/short-sale-report`(個別銘柄空売り残高報告)。

    **ENDPOINT_CONFIRMED、実装は引き続きNOT_IMPLEMENTED**。空売り残高割合の
    報告義務に基づく個別銘柄Positioning Dataであり、Phase4C候補の中では最も
    Positioning Research Questionに直結しうる。JQS-STD-01(2026-09-08、
    DECISIONS.md参照)のRead-Only Live Probeで`code`+`from`/`to`指定により
    200・Field名(`DiscDate`/`CalcDate`/`Code`/`SSName`/`SSAddr`/`ShrtPosToSO`/
    `ShrtPosShares`/`ShrtPosUnits`/`PrevRptDate`/`PrevRptRatio`等)を直接確認
    した。旧記述で競合候補だった`/markets/short_selling_positions`は403
    「Endpoint自体が存在しない」ことをJQS-STD-01で確認し、この矛盾は解消
    した。`CalcDate`(計算日)と`DiscDate`(開示日)が別Fieldとして実在する
    ことも確認できたため、Publication Lag(計算日から開示日までの日数)の
    存在自体は確認できたが、実際のLag日数の分布・Revision表現は未確認。
    """
    return DatasetDescriptor(
        dataset_id="jquants_short_sale_report",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Event-driven(報告都度、報告が無い日は提供されない)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="現在の契約(JQS-STD-01確認時点)でEndpoint自体への疎通・200 Responseを確認済み。",
        known_limitations=(
            "Endpoint PathはJQS-STD-01で200確認済み(ENDPOINT_CONFIRMED、旧競合候補`/markets/"
            "short_selling_positions`は403「存在しない」と確認し矛盾解消)。CalcDate/DiscDateの"
            "存在は確認したが、実際のPublication Lag日数の分布・Revision表現(訂正時の扱い)は"
            "未確認。VALIDATION_STATUS=IMPLEMENTATION_PENDING/PIT_PENDING(Adapter未実装)。"
        ),
        notes=(
            "Source Candidate Research: data-source-researcher Agent 2026-08-18。"
            "Path確認: JQS-STD-01(2026-09-08)、DECISIONS.md参照。"
        ),
    )


def build_jquants_investor_type_trading_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/equities/investor-types`(投資部門別売買状況)。

    **ENDPOINT_CONFIRMED、実装は引き続きNOT_IMPLEMENTED**。JQS-STD-01
    (2026-09-08、DECISIONS.md参照)のRead-Only Live Probeで200・Field名
    (`PubDate`/`StDate`/`EnDate`/`Section`/投資部門別`*Sell`/`*Buy`/`*Tot`/
    `*Bal`群)を直接確認した。旧記述の`/v2/markets/trades_spec`という推測
    Pathは誤りで、実際は403「Endpoint自体が存在しない」ことをJQS-STD-01で
    確認済み(この関数・dataset_idはJQS-STD-01Aで`jquants_trades_spec`から
    `jquants_investor_type_trading`へ改称した、DECISIONS.md参照)。最古の
    `PubDate`は2016-09-08で、JQS-STD-01が確認した実効History境界と一致する。
    """
    return DatasetDescriptor(
        dataset_id="jquants_investor_type_trading",
        source_id="jquants",
        capability=DataCapability.POSITIONING,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Weekly(Field名`StDate`/`EnDate`からの推定、Publication Lag未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="現在の契約(JQS-STD-01確認時点)でEndpoint自体への疎通・200 Responseを確認済み。",
        known_limitations=(
            "Endpoint PathはJQS-STD-01で200確認済み(ENDPOINT_CONFIRMED、旧推測Path`/markets/"
            "trades_spec`は403「存在しない」と確認し訂正)。Field名は最小限確認したが、Wire"
            "Schema全体・Publication Lag(週区分から実際のAPI利用可能時刻までの遅延)・"
            "Revision表現(PublishedDate等)は未確認。VALIDATION_STATUS=IMPLEMENTATION_PENDING/"
            "PIT_PENDING(Adapter未実装、Local Validationで最優先候補)。"
        ),
        notes=(
            "Source Candidate Research: data-source-researcher Agent 2026-08-18。"
            "Path確認: JQS-STD-01(2026-09-08)、DECISIONS.md参照。"
        ),
    )
