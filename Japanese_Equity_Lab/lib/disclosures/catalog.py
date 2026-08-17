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
    """EDINET(金融庁 開示書類システム) API V2 のCatalog登録情報(Phase4B-2、
    D0046追記: 2026-08-17 Local Real Data Validation完了を反映)。

    `implementation_status=CONNECTED`: ユーザーのローカル環境から実際に
    `api.edinet-fsa.go.jp`へ接続し、Documents List(`metadata.status="200"`・
    実Field構造)・Document Download(type=1、ZIP、SHA-256確認済み)いずれも
    実データで疎通・Parseを確認した(本Claude Cloudセッション自身は依然
    `api.edinet-fsa.go.jp`へ接続できない — `EdinetAdapter`/`edinet_normalize`
    はユーザー提供の実観測結果に基づいて実装されている)。

    ただし`pit_available=False`のまま: `market_public_at`/
    `provider_available_at`はいずれも`submitDateTime`から自動反映しておらず
    (意味論が未確認、D0046 §9)、`DisclosureDocument`のPIT Fieldは常に
    `UNKNOWN`のままである。「実データを取得・Parseできる」ことと「PIT安全な
    As-of Viewを提供できる」ことは別であり、後者はまだ達成していない。

    `document_kind`のMapping(公式別紙1のForm Code List)・`entity_id`の
    Role-aware解決(Entity Registry統合)はいずれも未実装のまま(D0046 §12/
    §14、Local Descriptionのみからの推測Mappingを避けるため意図的)。

    **Historical Point-in-Time Reconstructionはできない**(D0046 §7/§8、
    最重要の既知の制約): EDINETの過去日付のDocuments Listは日次更新され、
    縦覧期間満了・取下げ・書類情報修正により後から書き換わる。現在
    `date=2024-05-08`を取得しても、それが2024-05-08時点で市場が実際に
    観測できたUniverseと同一である保証はない。過去に実際に保存された
    Immutable Snapshotが無い限り、Historical Backtestでの利用には
    この限界が伴う(Source固有の不可避な制約であり、Architecture上のBugでは
    ない)。

    `originating_source`と`delivery_provider`は、EDINET APIを直接呼び出す
    設計である限り同一(`"EDINET"`)。
    """
    return DatasetDescriptor(
        dataset_id="edinet_disclosures",
        source_id="EDINET",
        capability=DataCapability.DISCLOSURE,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.CONNECTED,
        update_frequency="UNKNOWN(日次更新らしいが正式な更新頻度・SLAは未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="UNKNOWN(APIキー取得は確認済みだが、料金体系・プラン区分は未確認)",
        known_limitations=(
            "Local Real Data Validation(2026-08-17、ユーザーのローカル環境から"
            "1日分[2024-05-08]のDocuments List・1件[docID=S100TD9S, type=1]の"
            "Document Downloadのみ)によりDocuments List/Document Downloadの"
            "疎通・認証(query_param)・エラー形状(HTTP 200 + metadata.statusでの"
            "エラー表現)・確認済みField一覧・Lifecycle Status値は確認済み。"
            "Download type=1..5のマッピングは実際にDownloadして観測したのは"
            "type=1のみで、2〜5はユーザーがローカルで参照した公式仕様書の記述"
            "そのまま(SPEC_CLAIM_ONLY、`EdinetDownloadType`のDocstring参照、"
            "skeptic-reviewer Finding)。ただし: "
            "(1) market_public_at/provider_available_atはsubmitDateTimeから"
            "自動反映していない(意味論未確認のまま)。(2) document_kindは"
            "公式別紙1 Form Code List未確認のため常にUNKNOWN。(3) entity_idは"
            "filer/issuer/subject Role未解決のため常にNone(Raw Roleは"
            "EdinetDocumentMetadataに保持)。(4) Historical Listは日次更新・"
            "書き換わるため、現在の取得は過去時点のPIT Snapshotの代替にならない"
            "(最重要の制約、D0046 §7/§8)。(5) Documents Listの日付範囲・銘柄"
            "コード直接クエリ対応は未確認(1回1日のみ)。(6) レート制限は"
            "公式な数値未確認のまま暫定値を使用。詳細はEDINET_SOURCE_"
            "ONBOARDING.md・DECISIONS.md D0046参照。"
        ),
        notes=(
            "Raw Fetch: lib.disclosures.providers.edinet.EdinetAdapter。"
            "Normalize: lib.disclosures.providers.edinet_normalize"
            "(EDINET固有FieldはEdinetDocumentMetadataへ保持、Common Core"
            "DisclosureDocumentへは持ち込まない)。"
            "originating_source=delivery_provider='EDINET'。"
        ),
    )


__all__ = ["build_disclosure_common_core_dataset_descriptor", "build_edinet_dataset_descriptor"]
