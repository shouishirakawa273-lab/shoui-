"""Japan Macro DatasetをPhase3D Data Catalogへ登録する(Phase4D)。

`ImplementationStatus`(実装状況)と、このModuleが`known_limitations`/
`notes`へ自由記述で記録するValidation Status(`DESIGN_COMPLETE_AWAITING_
SPEC_VERIFICATION`等)は別軸として明示する(Phase4D要件§37、Positioning
Phase4Cと同じ方針。そのためだけの`DatasetDescriptor`Schema変更は行わない)。

**このRoundでAdapterを実装した候補は無い**。data-source-researcher Agent
(2026-08-18)による調査の結果、e-Stat/BOJ/ESRI/総務省/厚労省いずれも
公式仕様へこのSessionから接続できず(`EGRESS_BLOCKED`、`EDINET_SOURCE_
ONBOARDING.md`と同じ制約)、全ての情報がSEARCH-SNIPPET-DERIVED
(UNVERIFIED)に留まった。検索Snippetのみを根拠にAdapterを実装しない
(Phase4D要件§33)。
"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_estat_cpi_dataset_descriptor() -> DatasetDescriptor:
    """e-Stat(政府統計の総合窓口、総務省統計局)経由のCPI(全国CPI総合・
    生鮮食品を除く総合=コアCPI・生鮮食品及びエネルギーを除く総合=
    コアコアCPI)候補。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher Agentの調査では、
    5候補中最も強く裏付けられたAPI(バージョン管理されたREST API、
    `appId`登録Flow、複数の独立した検索結果が同じ仕様書PDF名を指し示す)
    だったが、実際のWire Schema・認証Parameter名・Rate Limit・
    Timestamp Field(`provider_available_at`相当)の有無、いずれも未読の
    まま(EGRESS_BLOCKED)。Base Year改定時に`statsDataId`が新設され
    「接続指数」で継続性を後付けする方式が示唆されており、これは
    Vintage Archiveではなく現在時点のContinuity Patchである可能性が高い
    (Section 15、Vintage概念とは別物として扱う)。VALIDATION_STATUS=
    `DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION`。
    """
    return DatasetDescriptor(
        dataset_id="estat_cpi",
        source_id="estat",
        capability=DataCapability.MACRO,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Monthly(未確認、SEARCH-SNIPPET-DERIVED: 原則翌月中旬公表)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料(政府統計標準利用規約に基づくと思われる、未確認)。appId登録が必要(推定、未検証)。",
        known_limitations=(
            "Wire Schema・認証Parameter名・Rate Limit・Timestamp Field(provider_available_at相当)の"
            "有無、いずれも未確認。Vintage/Revision History問い合わせ機構の有無は不明(Base Year改定時の"
            "接続指数による継続性Patchは確認できたが、これはVintage Archiveとは別物)。API Response schema・"
            "利用規約(再配布可否)いずれも未確認。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_"
            "VERIFICATION(Adapter未実装、Local Spec Verificationが最優先候補、data-source-researcher"
            "自身の推奨順位1位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_boj_policy_rate_dataset_descriptor() -> DatasetDescriptor:
    """日本銀行 時系列統計データ検索サイト経由の政策金利候補。

    **未実装(NOT_IMPLEMENTED)**。5候補の中で最も根拠が弱い
    (2026-02-18付BOJ通知の見出しとSNS投稿の要約のみが根拠、公式文書は
    未読)。Structured API(JSON/CSV、認証不要と示唆)が新設されたという
    未検証の主張のみで、Policy Rate自体が単独の系列として取得可能か、
    Money Market Rate系列からの導出が必要かも未確認。
    """
    return DatasetDescriptor(
        dataset_id="boj_policy_rate",
        source_id="boj",
        capability=DataCapability.MACRO,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Event-driven(政策決定都度、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料と思われる(未確認)。",
        known_limitations=(
            "5候補中最も根拠が弱い(2026-02-18付BOJ通知の見出しとSNS投稿要約のみが根拠、公式文書未読)。"
            "Structured API新設の主張自体が未検証。Policy Rate系列の存在形式(単独系列か、Money Market"
            "Rate系列からの導出が必要か)も未確認。Revision Behaviorは未確認(制度上Revisionは考えにくいが"
            "公式に確認できていない)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION"
            "(Adapter未実装、data-source-researcher推奨順位2位、まずAPI新設主張自体の真偽確認が必要)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_esri_gdp_qe_dataset_descriptor() -> DatasetDescriptor:
    """内閣府/ESRI 四半期別GDP速報(QE)候補。

    **未実装(NOT_IMPLEMENTED)**。5候補の中で唯一、公式な多段階Revision
    構造の名称(1次速報 -> 2次速報 -> 確報、Benchmark Revision)が複数の
    独立した検索結果で一致した——ただし未読のまま。専用REST APIの有無は
    未確認(e-Stat経由での取得可能性が示唆されるが未確認)。
    """
    return DatasetDescriptor(
        dataset_id="esri_gdp_qe",
        source_id="esri",
        capability=DataCapability.MACRO,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Quarterly(年8回、1次速報+2次速報、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料と思われる(未確認)。",
        known_limitations=(
            "専用REST APIの有無未確認(ESRIサイト自体はExcel/PDF中心の示唆、e-Stat経由の可能性は未確認)。"
            "1次速報/2次速報/確報という公式Revision Stage名称は複数検索結果で一致したが未読のまま。"
            "過去のRelease Stage別Tableが差し替え後も安定URLで残るか(=偶発的なVintage Archiveとして"
            "機能するか)は不明。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION"
            "(Adapter未実装、data-source-researcher推奨順位3位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_estat_unemployment_rate_dataset_descriptor() -> DatasetDescriptor:
    """総務省統計局 労働力調査(完全失業率)候補。

    **未実装(NOT_IMPLEMENTED)**。e-Stat経由での取得可能性が示唆される
    (Statコード00200531)が、CPIと同一Endpointで取得できるかは未確認。
    公表タイミング・Revision Behaviorいずれも他候補より情報が薄い。
    """
    return DatasetDescriptor(
        dataset_id="estat_unemployment_rate",
        source_id="estat",
        capability=DataCapability.MACRO,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Monthly(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料と思われる(未確認)。e-Stat CPIと同じappId登録が必要と推定(未検証)。",
        known_limitations=(
            "e-Stat CPIと同一Endpoint経由で取得可能かは未確認。公表タイミング(月末公表とする単一の"
            "未検証Snippetのみ、CPIのような曜日規則は見つからず)・Revision Behaviorいずれも他候補より"
            "情報が薄い。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装、"
            "e-Stat CPI検証が先行すれば同時に確認できる可能性が高い)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_mhlw_monthly_labour_survey_dataset_descriptor() -> DatasetDescriptor:
    """厚生労働省 毎月勤労統計調査(賃金)候補。

    **未実装(NOT_IMPLEMENTED)**。5候補の中で最も具体的かつ実在するRevision
    /Benchmark更新の記述(2024年1月のBenchmark更新による指数断層、参考値
    系列の別途公表)が見つかった——ただし未読のまま。PDF中心の公開形式が
    示唆されており、構造化APIでの取得可能性はe-Stat経由以外未確認。
    """
    return DatasetDescriptor(
        dataset_id="mhlw_monthly_labour_survey",
        source_id="mhlw",
        capability=DataCapability.MACRO,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="Monthly(速報+確報の2段階、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料と思われる(未確認)。",
        known_limitations=(
            "PDF中心の公開形式が示唆されており、構造化APIでの取得可能性はe-Stat経由以外未確認。"
            "2024年1月のBenchmark更新(母集団入れ替え)による指数断層と、比較可能性のための「参考値」"
            "系列の別途公表という、5候補中最も具体的なRevision Behaviorの記述が見つかったが未読のまま。"
            "VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装、"
            "data-source-researcher推奨順位4位、ただしRevision設計の参考価値は高い)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )
