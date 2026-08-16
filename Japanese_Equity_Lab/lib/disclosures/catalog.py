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


__all__ = ["build_disclosure_common_core_dataset_descriptor"]
