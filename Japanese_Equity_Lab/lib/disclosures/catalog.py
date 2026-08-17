"""Disclosure Common CoreをPhase3D Data Catalogへ登録する(Phase4B-1、D0045)。"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_disclosure_common_core_dataset_descriptor() -> DatasetDescriptor:
    """Disclosure Common Core(Source非依存のArchitecture)自体のCatalog登録情報。

    `implementation_status=FIXTURE_ONLY`: 実SourceへPhase4B-1では一切接続
    しておらず、Provider-neutralなFixtureでのArchitecture検証のみ完了
    (`CODE_COMPLETE`、実Source接続はPhase4B-2以降)。`source_id`/`authority_
    class`はDisclosure Common Core自体には特定のSourceが存在しないため
    Placeholder値とし、実Source接続時(TDnet/EDINET/Company IR等)に
    Source別のDatasetDescriptorを別途登録すること(このDescriptorを
    書き換えるのではなく追加する)。
    """
    return DatasetDescriptor(
        dataset_id="disclosure_common_core",
        source_id="disclosure_common_core_architecture",
        capability=DataCapability.DISCLOSURE,
        authority_class=SourceAuthorityClass.SECONDARY,
        implementation_status=ImplementationStatus.FIXTURE_ONLY,
        update_frequency="Source依存(未接続のため取得不可)",
        pit_available=True,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="取得不可(実Source未接続)",
        known_limitations=(
            "実Source(TDnet/EDINET/Company IR)へ未接続。Provider-neutralな"
            "Fixture Schemaでの動作確認のみ。DocumentKind Mapping・"
            "AttachmentKind Mappingはいずれも公式仕様未確認のFixture専用値。"
            "本文Semantic Extraction(Claim/Event抽出)は未実装(Phase4B-1の"
            "意図的なScope外)。Document間Relationshipは明示的根拠がある場合"
            "のみ設定し、自動推測はしない。"
        ),
        notes="normalizer_version=DISCLOSURE_COMMON_CORE_NORMALIZER_V1(lib.disclosures.model.NORMALIZER_VERSION)",
    )


def build_edinet_dataset_descriptor() -> DatasetDescriptor:
    """EDINET(金融庁 開示書類システム) API V2 のCatalog登録情報(Phase4B-2)。

    `implementation_status=NOT_IMPLEMENTED`: `lib.disclosures.providers.edinet.
    EdinetAdapter`はDocuments List/Document DownloadのRaw HTTP Fetchのみを
    提供し、`DisclosureDocument`への正規化(field mapping)は一切行っていない。
    本セッションは`api.edinet-fsa.go.jp`・FSA公式資料のいずれへも接続できず
    (egressポリシーによりブロック、`curl`で`CONNECT tunnel failed, 403`を
    独立に確認済み)、`data-source-researcher`によるOnboarding調査も
    二次情報のみに基づく未確認結果(一部相互矛盾)に留まった
    (`EDINET_SOURCE_ONBOARDING.md`参照)。したがって`SKELETON`
    (実仕様に基づくAdapter骨格)ではなく`NOT_IMPLEMENTED`とする —
    Raw Fetch用のコードは存在するが、その対象Field名・Query仕様自体が
    未確認であるため。

    `originating_source`と`delivery_provider`は、EDINET APIを直接呼び出す
    設計である限り同一(`"EDINET"`)— 別Provider経由での配信は現時点で
    想定していない(D0042のOrigin/Delivery分離を踏襲、値が分かれるのは
    将来他Provider経由でEDINET由来情報を取得する場合のみ)。
    """
    return DatasetDescriptor(
        dataset_id="edinet_disclosures",
        source_id="EDINET",
        capability=DataCapability.DISCLOSURE,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="UNKNOWN(公式資料未確認、更新頻度・縦覧期間の範囲が未確定)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="UNKNOWN(無料と思われるが一次資料で未確認)",
        known_limitations=(
            "公式FSA/EDINET資料・API本体への接続がいずれも本セッションからブロックされて"
            "おり(EGRESS_BLOCKED、独立にcurlでも確認)、Documents Listの実フィールド名・"
            "submitDateTime/opeDateTimeの意味論・parentDocIDの訂正関係・"
            "withdrawalStatusの列挙値・secCode形式・Document Downloadのtype値、"
            "いずれも未確認(一部は情報源間で相互矛盾)。詳細は"
            "EDINET_SOURCE_ONBOARDING.mdを参照。ローカル環境での実API疎通確認が"
            "完了するまで、DisclosureDocumentへの正規化(field mapping)・"
            "DocumentKind/Form Codeマッピング・Entity Registry統合・"
            "market_public_at/provider_available_atへの反映は一切行わない"
            "(pit_available=Falseはこれを表す — Raw Fetchはできても、"
            "確認済みのPIT意味論に基づくAs-of Viewはまだ提供できない)。"
        ),
        notes=(
            "Raw Fetchのみ: lib.disclosures.providers.edinet.EdinetAdapter。"
            "originating_source=delivery_provider='EDINET'(直接接続、Phase4B-2時点)。"
        ),
    )


__all__ = ["build_disclosure_common_core_dataset_descriptor", "build_edinet_dataset_descriptor"]
