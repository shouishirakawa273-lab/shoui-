"""Japan/Global News DatasetをPhase3D Data Catalogへ登録する(Phase4E-2/4E-3)。

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

## Phase4E-3(Global News)向け追加候補

同じdata-source-researcher Agent(2026-08-18)によるGlobal News候補調査
(Reuters/LSEG・Bloomberg・AP・AFP・SEC・Federal Reserve・US Treasury・
ECB・Bank of England・GDELT・NewsAPI.org・Google News RSS等)も同様に
`EGRESS_BLOCKED`であり、以下2件のみ「構造/Timestamp/Licenseのいずれかが
比較的明確」として登録する(Phase4E-3要件§33、Wire Service勢は
Enterprise契約前提でこのLabの個人ローカル実行という前提にそぐわないため
除外、NewsAPI.orgは全文再配布不可というTerms自体は明確だが全文保存を
前提とするこのLabの用途に合わないため除外、Google News RSSは非公式・
無Documentのため除外)。
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


def build_gdelt_doc_dataset_descriptor() -> DatasetDescriptor:
    """GDELT DOC 2.0 API/Bulk Export(世界の報道をMonitoringしEvent-level
    Metadataを構造化するAcademic/Open Project)経由の候補(Phase4E-3)。

    **未実装(NOT_IMPLEMENTED)**。data-source-researcher AgentがGlobal News
    候補の中で最も構造/Timezone Documentationが明確と評価したが、GDELTが
    配信するのは**News記事そのもの(全文)ではなく、記事から抽出された
    Event-level Metadata**である(URL・出典・言語・トーン等)——本文保存を
    前提にできない(`ContentAvailability.REFERENCE_ONLY`が上限)。UTC
    default/明示的Timezone Documentationは複数独立Snippetで確認されたが、
    このSession自身は未読(`EGRESS_BLOCKED`)。「Unrestricted use...without
    fee」という利用許諾を主張するSnippetがあるが、License全文自体は未読の
    ためUNKNOWN != ALLOWEDの原則により確定させない(Phase4E-3要件§24)。
    GDELTは複数のNews Source(Reuters/AP等を含む)を横断的にMonitoringする
    Secondary Aggregatorであり、Originating Source自体ではないため
    `SourceAuthorityClass.VERIFIED_SECONDARY`とする。
    """
    return DatasetDescriptor(
        dataset_id="gdelt_doc_2",
        source_id="gdelt",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.VERIFIED_SECONDARY,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="15分毎更新と示唆(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=(),
        cost_or_plan_dependency="無料・認証不要と思われる(未確認)。",
        known_limitations=(
            "News記事の全文ではなくEvent-level Metadata(URL・出典・言語・トーン等)の配信であり、"
            "本文保存を前提にできない(ContentAvailability=REFERENCE_ONLY止まりが安全側)。UTC既定/"
            "DST関連の明示的Timezone DocumentationはSnippet上では複数独立に確認されたが本文自体は"
            "未読。「Unrestricted use...without fee」という利用許諾の主張も同様に未読のため確定させ"
            "ない(UNKNOWN != ALLOWED)。Reuters/AP等の一次記事を横断的にMonitoringするSecondary"
            "Aggregatorであり、記事のOriginating Source自体の権威付けとは別軸。VALIDATION_STATUS="
            "DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装、data-source-researcher推奨"
            "順位1位)。"
        ),
        notes="Source Candidate Research: data-source-researcher Agent 2026-08-18、DECISIONS.md参照。",
    )


def build_sec_press_release_dataset_descriptor() -> DatasetDescriptor:
    """SEC(米国証券取引委員会)報道発表資料/Litigation Release RSS経由の
    候補(Phase4E-3)。

    **未実装(NOT_IMPLEMENTED)**。無料・認証不要と示唆される公式RSS Feedの
    存在はSnippetで確認されたが未読。data-source-researcher Agentが2つの
    具体的なPIT関連Riskを指摘した: (1) SECのRSS自身のTimezone表記が
    「EST」という年間を通じた固定Labelを使っているとの示唆があり(DST期間中
    実際にはEDTのはずだが区別されていない)、abbreviation由来のTimezoneは
    このLabの原則上IANA Timezoneへ自動変換しない(D0056で確認済みの
    `ZoneInfo("EST")`固定UTC-5問題と同型、Phase4E-3要件§14)、(2) EDGAR
    構造化開示のAcceptance Datetime(EDGAR受理時刻)とFiling Date(開示書類
    自体の日付)は別概念であり、Press Release RSSのpubDateがどちらに相当
    するかは未確認。
    """
    return DatasetDescriptor(
        dataset_id="sec_press_release",
        source_id="sec",
        capability=DataCapability.NEWS,
        authority_class=SourceAuthorityClass.PRIMARY_OFFICIAL,
        implementation_status=ImplementationStatus.NOT_IMPLEMENTED,
        update_frequency="EVENT_DRIVEN(未確認)",
        pit_available=False,
        applicable_codes=None,
        applicable_countries=("US",),
        cost_or_plan_dependency="無料・認証不要と思われる(未確認)。",
        known_limitations=(
            "公式RSS Feed(press releases/litigation releases)の存在はSnippetで示唆されたが未読。"
            "SEC自身のRSS DocumentationがTimezoneを「EST」という年間固定Labelで表記している可能性が"
            "あり(DST期間中の実際のOffsetと不一致の恐れ)、この曖昧なAbbreviationはIANA Timezoneへ"
            "自動変換しない(source_declared_timezoneとしてそのまま保持する方針、published_atは"
            "確認できるまでUNKNOWNのまま)。EDGARのAcceptance Datetime(受理時刻)とFiling Date"
            "(書類自体の日付)は別概念であり、Press Release RSSのpubDateがどちらに相当するか未確認。"
            "VALIDATION_STATUS=DESIGN_COMPLETE_AWAITING_SPEC_VERIFICATION(Adapter未実装、"
            "data-source-researcher推奨順位2位)。参考: 同じ調査でUS Treasuryの過去のRSS Feedに"
            "2021年の実際のReplay Bug(古いItemが再配信されたIncident)が報告されていることが判明した"
            "——Treasury自体は候補として採用していないが、Government RSS全般に対するPIT Riskの実例"
            "としてValidation Backlogへ記録する。"
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
