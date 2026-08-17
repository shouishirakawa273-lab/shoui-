"""TDnet Incremental Retrieval(Cursor)のState Model骨格のみ(Phase4B-3、D0047)。

**このModuleはAdapter/Normalizerの一部ではない。** TDnet固有のEndpoint/
Field名はまだ何一つ確認できていない(`TDNET_SOURCE_ONBOARDING.md`参照、
本セッションから公式資料へ一切接続できず、`data-source-researcher`の調査も
未確認のSearch Snippetのみに基づく結果に留まった)。したがってこのModuleは
実際の`/v2/td/list`呼び出しを一切行わず、将来Adapterが実装される際に
「Cursorという概念をどうDocument Modelから分離して保持するか」という
Architecture上の骨格のみを提供する(ユーザー指示 §D/§24: 「cursor state
model/interfaceのみ必要最小限で用意可能。Automation/Schedulerは実装禁止」)。

## Cursorは`DisclosureDocument`ではない(最重要原則)

Cursorは「どこまで取得したか」というRetrieval State(取得進捗の識別子)
であり、以下のいずれでもない:

- Disclosure Timestamp(開示が行われた時刻)
- `market_public_at`(市場が実際に知りえた時刻)
- `provider_available_at`(このLabがProvider経由で参照可能になった時刻)

Cursor値自体をDecodeできたとしても、そこから上記いずれかのTimestampを
推測してはならない。Cursorは`DisclosureDocument`/`DisclosureAttachment`
(`lib.disclosures.model`)とは完全に分離したModelとして保持する。

`pagination_key`(同一Queryの残りページを取得する既存の仕組み、
`lib.data_sources.jquants.JQuantsAdapter._get_all_pages`が既に扱っている)
とも別概念として扱う(未確認だが、公式仕様上区別されると報告されている
`TDNET_SOURCE_ONBOARDING.md` §6)。このModuleはCursor(Differential
Retrieval用)専用であり、`pagination_key`のHandlingは既存の`JQuantsAdapter`
パターンをそのまま再利用する想定(将来Adapter実装時)。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


@dataclass(kw_only=True, frozen=True)
class TdnetRetrievalCursorState:
    """1回のIncremental Retrieval試行についてのRetrieval Provenance。

    `query_date`: どの日付を対象にCursorベースのDifferential Retrievalを
    行ったか(TDnet Add-onは当日分のみCursor対応と報告されている、未確認、
    `TDNET_SOURCE_ONBOARDING.md` §2)。**これもTimestampではない** —
    「このRetrieval試行が対象にした日付」という自分自身のQuery Parameter
    の記録に過ぎず、その日にCursor経由で返ってきた各Documentの実際の
    `market_public_at`(開示日時)と自動的に一致する保証は無い。将来
    Adapterを実装する際、`query_date`を「その日Retrievalされた
    Documentは全てその日に開示された」という代替Timestampとして
    Downstreamへ伝播させてはならない(`DiscDate`/`DiscTime`の意味論が
    確認できるまで、Document側のPIT Fieldは別途`AvailabilityBasis.
    UNKNOWN`のまま扱う)。
    `cursor_value`: 今回のRetrieval後に得られたCursor値(次回はこれを渡して
    差分取得する想定)。`None`は「Cursorが返らなかった/対象外だった」ことを
    表す。
    `previous_cursor`: 今回のRetrievalで実際に使用した、前回のCursor値
    (初回Retrievalでは`None`)。
    `retrieved_at`: このLabが実際にRetrievalを行った時刻(tz-aware必須)。
    `response_snapshot_hash`: このRetrievalで得られたRaw Responseの
    Content Hash(`RawSnapshotStore`が別途保存するSnapshotとの対応付け用、
    Optional — 実際にRaw保存を行った場合のみ設定する)。

    このClassはPersistence/Scheduling機構を一切持たない(将来Phase)。
    単なる不変のDataclassであり、呼び出し側が任意の方法(Fileや将来のDB等)
    で保持することを想定するのみ。
    """

    query_date: date
    cursor_value: str | None
    previous_cursor: str | None
    retrieved_at: datetime
    response_snapshot_hash: str | None = None

    def __post_init__(self) -> None:
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at はtz-awareである必要があります")


__all__ = ["TdnetRetrievalCursorState"]
