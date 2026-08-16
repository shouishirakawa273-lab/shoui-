"""Financial Summary DatasetをPhase3D Data Catalogへ登録する(Phase4A、D0043)。"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_financial_summary_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/fins/summary`のCatalog登録情報。

    `implementation_status=FIXTURE_ONLY`: Fixture(合成データ)での動作確認のみ
    完了しており、実データでの疎通確認はまだ行っていない(CODE_COMPLETE_
    AWAITING_LOCAL_VALIDATION、DECISIONS.md D0043参照)。`pit_available=True`は
    「decision_atごとのAs-of解決を`fundamentals_as_of()`が構造上サポートする」
    という意味であり、実データでのprovider_available_at精度を保証するものではない
    (`known_limitations`参照)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_fins_summary",
        source_id="jquants",
        capability=DataCapability.FUNDAMENTAL,
        authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        implementation_status=ImplementationStatus.FIXTURE_ONLY,
        update_frequency="決算短信等の開示都度(不定期)",
        pit_available=True,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="Light Plan(ユーザー申告)で利用可能と仮定、未検証。Endpoint固有Rate Limit 60req/分(ユーザー提示)",
        known_limitations=(
            "Field名(DiscNo/DocType/DiscDate/DiscTime/CurPerType/Sales/OP/NP等)は未検証"
            "(ネットワーク遮断のため公式ドキュメントへ接続できない、DECISIONS.md D0043参照)。"
            "provider_available_atは実際の観測ログが無いため常にavailability_basis=UNKNOWN"
            "(Reproducible System Simulationの既定では利用不可として扱われる)。"
            "DocType -> Accounting Standardの対応は未確認(空Mapping、fail closed)。"
            "Revision Relationship(DiscNo間の親子関係)は未確認のため保持しない。"
        ),
        notes="normalizer_version=FINS_SUMMARY_NORMALIZER_V1(lib.fundamentals.model.NORMALIZER_VERSION)",
    )
