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


def build_tdnet_dataset_descriptor() -> DatasetDescriptor:
    """TDnet(東証適時開示情報伝達システム)、J-Quants API V2 TDnet/適時開示情報
    アドオン経由のCatalog登録情報(Phase4B-3、D0047/D0048)。

    **経緯**: `data-source-researcher`によるSource Onboarding調査
    (`TDNET_SOURCE_ONBOARDING.md`)は、EDINET初回調査(Phase4B-2)よりも
    さらに深刻なBlockに直面した — 本セッションから`jpx-jquants.com`・
    `jpx.gitbook.io`いずれへも接続できず(`curl`で独立に確認済み)、
    タスク上最重要の2項目(訂正/削除/`DiscStatus`/`RevNo`意味論、
    `DiscDate`/`DiscTime`のPIT意味論)いずれも裏付けとなるSourceがゼロ
    だったため、D0047時点では`lib/disclosures/providers/tdnet.py`
    (Adapter/Normalizer)を一切実装しなかった。

    **その後(D0048)**: ユーザーが別のWeb-access環境から2026-08-17時点の
    公式ページを直接確認したと申告し(Provenance Tag`EXTERNAL_OFFICIAL_
    SPEC_VERIFICATION`、`TDNET_SOURCE_ONBOARDING.md`の同名セクション
    参照)、その内容を根拠に`lib.disclosures.providers.tdnet.
    TdnetAdapter`(Raw Fetch)・`lib.disclosures.providers.tdnet_normalize`
    (Normalize、`DisclosureDocument`への変換を含む)を実装した。

    `implementation_status=NOT_IMPLEMENTED`のまま維持する理由: この申告は
    Claude自身がこのSession内で一次資料をFetchして確認したものではなく、
    真の意味でのLocal Real Data Validation(実際にAdd-on契約済みのAPI Keyで
    `/v2/td/list`等を呼び出し、Response実物を観測すること)でもない
    (`EdinetAdapter`がEDINET初回Roundで辿った「まずコードを書き、後日
    ユーザーのローカル環境から実際に呼び出して`CONNECTED`へ昇格させる」
    という手順の、まだ前半段階に相当する)。`TDNET_LOCAL_VALIDATION_
    GUIDE.md`のValidationが完了するまで`NOT_IMPLEMENTED`/`pit_available
    =False`のままとする。

    `originating_source="TDnet"`・`delivery_provider="J-Quants"`(D0042の
    Origin/Delivery分離を踏襲、上場会社[発行体]・TDnet[開示制度/Venue]・
    J-Quants[配信Provider]の3層はさらに別概念、`TDNET_ARCHITECTURE.md`参照)。
    """
    return DatasetDescriptor(
        dataset_id="tdnet_disclosures",
        source_id="TDNET",
        capability=DataCapability.DISCLOSURE,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="UNKNOWN(EXTERNAL_OFFICIAL_SPEC_VERIFICATIONでも更新頻度自体は申告されていない)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency=(
            "月額11,000円(税込)、Lightプラン以上へのAdd-on(EXTERNAL_OFFICIAL_"
            "SPEC_VERIFICATION、ユーザー申告)。Current Userがこのアドオンを"
            "契約済みとは仮定しない(この申告自体もClaude自身が一次資料を"
            "Fetchして確認したものではない)。"
        ),
        known_limitations=(
            "D0047時点: 公式J-Quants/JPX資料への接続が本セッションから一貫して"
            "ブロックされていた(EGRESS_BLOCKED)。D0048でユーザーが別のWeb-"
            "access環境からの直接確認を申告し(EXTERNAL_OFFICIAL_SPEC_"
            "VERIFICATION)、DiscStatus/RevNoのSchema宣言意味論と現在の実装"
            "挙動(常にnull/常に1)の区別、DiscDate/DiscTimeのmarket_public_at"
            "Mapping、Cursor/pagination_key相互排他性、/v2/td/files・/v2/td/"
            "bulkのURL15分失効等を実装へ反映した。ただし: (1) この申告は"
            "Claude自身が一次資料を直接Fetchして確認したものではなく、真の"
            "Local Real Data Validation(実際のAdd-on契約済みAPI Keyでの"
            "呼び出し)でもない。(2) BASE_URL(api.jquants.com/v2の共有)・"
            "Response Envelope形状({'data': [...]}形式)はMain Claudeによる"
            "推論であり、ユーザー申告そのものではない。(3) DiscItems公式Code"
            "Listの内容・Docsのg/s/x短縮Code以外の詳細意味論は依然未確認。"
            "(4) provider_available_atはmarket_public_atが確認できても常に"
            "UNKNOWN(実観測ログが無い限りFallbackしない)。(5) Add-on未契約時"
            "のError挙動・EDINET同様のHTTP-200-masks-error patternの有無は"
            "未確認。詳細はTDNET_SOURCE_ONBOARDING.md・DECISIONS.md D0047/"
            "D0048参照。これらが実際のAdd-on呼び出しで確認されるまで、"
            "implementation_status=NOT_IMPLEMENTED・pit_available=Falseを"
            "維持する。"
        ),
        notes=(
            "Raw Fetch: lib.disclosures.providers.tdnet.TdnetAdapter。"
            "Normalize: lib.disclosures.providers.tdnet_normalize"
            "(TDnet固有FieldはTdnetDocumentMetadataへ保持、Provider-neutral"
            "なCommon Core DisclosureDocumentへは持ち込まない)。"
            "Retrieval Cursor Provenanceの State Model骨格は"
            "lib.disclosures.providers.tdnet_cursor(DisclosureDocumentとは"
            "分離)。いずれもEXTERNAL_OFFICIAL_SPEC_VERIFICATION(D0048)に"
            "基づく実装であり、真のLocal Real Data Validationは未完了。"
            "originating_source='TDnet'、delivery_provider='J-Quants'。"
        ),
    )


__all__ = [
    "build_disclosure_common_core_dataset_descriptor",
    "build_edinet_dataset_descriptor",
    "build_tdnet_dataset_descriptor",
]
