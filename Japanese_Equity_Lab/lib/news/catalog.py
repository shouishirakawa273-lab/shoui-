"""Japan News DatasetをPhase3D Data Catalogへ登録する(Phase4E-2)。

`ImplementationStatus`(実装状況)と、このModuleが`known_limitations`へ
自由記述で記録するValidation Status(`DESIGN_COMPLETE_AWAITING_SPEC_
VERIFICATION`等)は別軸として明示する(Positioning Phase4C/Macro Phase4D/
Global Market Phase4E-1と同じ方針。そのためだけの`DatasetDescriptor`
Schema変更は行わない)。

**このRoundでAdapterを実装した候補は無い**。data-source-researcher Agent
(2026-08-18)がPR TIMES・JPX News Releases・FSA・METI・BOJ・Nikkei・
Reuters/Refinitiv・Bloomberg・Kyodo/Jiji等を調査したが、このSession自身の
Network Egressが全ての候補Provider Domain(`prtimes.jp`/`developers.
prtimes.com`/`www.jpx.co.jp`/`www.fsa.go.jp`/`jp.reuters.com`等)へ
一貫してBlockされており(`EGRESS_BLOCKED`)、全ての情報がSEARCH-SNIPPET-
DERIVED(UNVERIFIED)に留まった。検索Snippetのみを根拠にAdapterを実装
しない(Phase4E-2要件§8)。
"""

from __future__ import annotations

from lib.sources.catalog import DataCapability, DatasetDescriptor, ImplementationStatus, SourceAuthorityClass


def build_prtimes_dataset_descriptor() -> DatasetDescriptor:
    """PR TIMES(プレスリリース配信サービス)経由の企業Press Release候補。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher Agentの調査では
    最も構造的に有望な候補(会社別/リリース別RSS Feedの存在が複数独立
    Snippetで裏付けられ、`{company_id}.{release_seq}`という2部構成の
    数値識別子Schemeも示唆された)だったが、2つの重大なGapが未解決:
    (1) 全文保存・再配布に関するTerms(`prtimes.jp/main/html/kiyaku`、
    未読)が制限的である可能性、(2) 公開Article/RSS自体が実際に露出する
    Timestamp Fieldの粒度(著者用UI側の10分刻みScheduling機能からの
    示唆のみで、公開側の実際のField仕様は未確認)。originating_source
    (Press Release発行企業)とdelivery_provider("PRTIMES")の分離が必要
    (D0042、EDINET経由J-Quantsと同型)。
    """
    return DatasetDescriptor(
        dataset_id="prtimes_press_release",
        source_id="prtimes",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.COMPANY_PRIMARY,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="EVENT_DRIVEN(会社側が任意のTimingでRelease配信、未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="閲覧・RSS購読は無料と思われる(未確認)。配信企業側は有料(このLabには無関係)。",
        known_limitations=(
            "公式Public REST/JSON APIの存在が確認できず(developers.prtimes.com自体は未読)、"
            "会社別/リリース別RSSの存在のみ複数独立Snippetで裏付けられた。全文保存・再配布に関するTerms"
            "(企業規約第6条相当)が制限的な可能性があり、全文保存を前提にできない(Content Availability="
            "METADATA_ONLY/REFERENCE_ONLY止まりが安全側)。公開Article/RSSが実際に露出するTimestamp"
            "Fieldの粒度・Timezoneも未確認(著者用UIの10分刻みScheduling機能からの示唆のみ)。company_id"
            "からCanonical Entity RegistryへのMapping手法も未設計(PR TIMESは上場企業に限らない自己登録"
            "制のため)。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装、"
            "data-source-researcher推奨順位1位、ただしLicense/Timestamp Field双方の確認が実装前提)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_jpx_news_releases_dataset_descriptor() -> DatasetDescriptor:
    """JPX(日本取引所グループ)News Releases(個別銘柄開示=TDnetとは別、
    取引所自体からのお知らせ)経由の候補。

    **未実装(NOT_IMPLEMENTED)**。RSS Feed(`www.jpx.co.jp/rss/`)の存在は
    示唆されたが未読。RSSの`pubDate`がFull Datetimeか日付のみかは未確認。
    """
    return DatasetDescriptor(
        dataset_id="jpx_news_releases",
        source_id="jpx",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="EVENT_DRIVEN(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料・認証不要と思われる(未確認)。",
        known_limitations=(
            "RSS Feed(www.jpx.co.jp/rss/)の存在はSnippetで示唆されたが未読。RSSのpubDateがFull"
            "DatetimeかDate-onlyか、Timezoneがどう表現されるかいずれも未確認。個別銘柄開示(TDnet)とは"
            "別の、取引所自体からのお知らせ(制度変更・システム関連等)であり、Content自体のRelevance範囲"
            "も未確認。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_fsa_press_release_dataset_descriptor() -> DatasetDescriptor:
    """金融庁(FSA)報道発表資料RSS経由の候補。

    **未実装(NOT_IMPLEMENTED)**。RSS Feed(`www.fsa.go.jp/kouhou/rss.html`、
    証券取引等監視委員会[SESC]向け別Feedも存在すると示唆)の存在はSnippetで
    示唆されたが未読。
    """
    return DatasetDescriptor(
        dataset_id="fsa_press_release",
        source_id="fsa",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="EVENT_DRIVEN(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料・認証不要と思われる(未確認)。",
        known_limitations=(
            "RSS Feed(www.fsa.go.jp/kouhou/rss.html)・SESC向け別Feedの存在はSnippetで示唆されたが"
            "未読。Timestamp Field仕様・Correction/Update挙動いずれも未確認。VALIDATION_STATUS="
            "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_meti_news_release_dataset_descriptor() -> DatasetDescriptor:
    """経済産業省(METI)News Release RSS経由の候補。

    **未実装(NOT_IMPLEMENTED)**。RSS Feed(`www.meti.go.jp/rss/`、
    Press Release/METI Journal/統計新着通知の3系統と示唆)の存在はSnippetで
    示唆されたが未読。Live Site上のArchive Depthが「過去3年度分」に限られ
    るという記述がある(未確認)。
    """
    return DatasetDescriptor(
        dataset_id="meti_news_release",
        source_id="meti",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="EVENT_DRIVEN(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("JP",),
        cost_or_plan_dependency="無料・認証不要と思われる(未確認)。",
        known_limitations=(
            "RSS Feed(www.meti.go.jp/rss/、Press Release/METI Journal/統計新着通知の3系統と示唆)の"
            "存在はSnippetで示唆されたが未読。Live Site上のArchive Depthが「過去3年度分」に限られる"
            "という記述があり(未確認)、それ以前は国立国会図書館のWeb Archivingプロジェクト経由のみと"
            "示唆される——このLab自身のRawSnapshotStoreによるForward Snapshot保存の必要性が他候補より"
            "高い可能性がある。VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION"
            "(Adapter未実装)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )
