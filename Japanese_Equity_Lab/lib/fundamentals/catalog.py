"""Financial Summary DatasetをPhase3D Data Catalogへ登録する(Phase4A、D0043)。"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_financial_summary_dataset_descriptor() -> DatasetDescriptor:
    """`/v2/fins/summary`のCatalog登録情報。

    `implementation_status=CONNECTED`: 2026-08-16、ユーザーが4銘柄
    (7203/6758/8056/3626)でローカルPCから実際に`/v2/fins/summary`へ接続し、
    実Raw Responseの一部Field名・Wire Format・DocType値を確認した
    (DECISIONS.md D0043参照)。ただし依然として未確認の項目が残るため
    (`known_limitations`参照)、公式仕様の全項目を検証済みという意味ではない。
    `pit_available=True`は「decision_atごとのAs-of解決を
    `fundamentals_as_of()`が構造上サポートする」という意味であり、実データでの
    provider_available_at精度を保証するものではない(`known_limitations`参照)。
    """
    return DatasetDescriptor(
        dataset_id="jquants_fins_summary",
        source_id="jquants",
        capability=DataCapability.FUNDAMENTAL,
        authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        implementation_status=ImplementationStatus.CONNECTED,
        update_frequency="決算短信等の開示都度(不定期)",
        pit_available=True,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "Light Plan(ユーザー申告)で利用可能と確認済み(4銘柄実データ疎通成功)。"
            "Endpoint固有Rate Limit 60req/分(ユーザー提示、実挙動は未検証)"
        ),
        known_limitations=(
            "Non-Consolidated DocType・USGAAPのDocType・4Q/5Qの実データ・Forecast Revision専用"
            "DocType・Correction/Restatement Relationshipは未確認(推測実装していない)。"
            "Pagination実挙動・Rate Limit実挙動も未検証。"
            "provider_available_atは実際の観測ログが無いため常にavailability_basis=UNKNOWN"
            "(Reproducible System Simulationの既定では利用不可として扱われる)。"
            "'_JP'接尾辞DocType(3626で確認)の公式な意味(JGAAPと同義か等)は未確認のため、"
            "IFRSと区別できる中立的な識別子(PROVIDER_SUFFIX_JP)のみ使用し'JGAAP'とは呼ばない。"
            "TA/Eq/EqAR/CFO/CFI/CFF/CashEq/配当/株式数/ROE等のFieldはRawに保持されるが"
            "Metricへは未マッピング。/v2/fins/summaryのcode指定クエリはfrom/toで絞り込まれず"
            "対象Codeの全履歴を返す(D0043確認済み)。"
        ),
        notes="normalizer_version=FINS_SUMMARY_NORMALIZER_V1(lib.fundamentals.model.NORMALIZER_VERSION)",
    )
