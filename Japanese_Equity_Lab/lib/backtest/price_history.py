"""decision_at(as_of)単位でPrice Historyを取得するInterfaceと実装(Phase3A.2、D0035)。

D0034で判明した問題: `BacktestEngine.run()`が全期間共通の調整済みPrice Series
(`price_history: Mapping[str, Sequence[AdjustedOHLCVBar]]`)を1回だけ事前計算し、
各decision_atではそこから単純にスライスしていたため、単一のas_ofでCorporate Action
Adjustmentを適用すると、Walk-Forwardで複数のdecision_atをまたぐ場合に一部の
decision_atが「まだ知り得ないはずの将来のCorporate Actionで調整された価格」を
見てしまう可能性があった。

この問題を解消するため、`BacktestEngine`は`PriceHistorySource` Protocolだけに依存し、
「decision_at時点のPrice Historyを取得する」という抽象的なInterfaceの向こうにある
具体的な調整方法(Corporate Action Adjustmentの有無、Providerの種類等)を一切知らない
ようにする。

- `StaticPriceHistory`: 既に確定したBar列をそのまま返す(Corporate Action調整は
  行わない)。fixtureや、株式分割を扱わない合成データ向け。Phase3A.1以前の
  `price_history`引数(plain dict)と完全に同じ挙動を再現する。
- `AsOfAdjustedPriceHistory`: Raw Price History + Corporate Action Eventsから、
  呼び出しごと(decision_atごと)にPIT-safeなAdjusted Bar列を構築する
  (`build_provider_derived_adjusted_bars`を都度呼び出す)。
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime
from typing import Protocol

from lib.schemas.price_data import AdjustedOHLCVBar, CorporateAction, RawOHLCVBar, build_provider_derived_adjusted_bars


class PriceHistorySource(Protocol):
    """ある時点(as_of)までに利用可能だったPrice Historyを取得するInterface。

    `BacktestEngine`はこのInterfaceのみに依存し、Corporate Action Adjustmentの
    具体的な実装(Provider固有ロジック含む)を一切知らない。
    """

    def bars_up_to(self, code: str, as_of: datetime) -> Sequence[AdjustedOHLCVBar]:
        """as_of時点で利用可能だった、その時点までのBar列(session_date昇順)を返す。

        `session_date <= as_of.date()`のBarのみを含み、Corporate Action Adjustmentを
        行う実装の場合はas_of時点でeffectiveなCorporate Actionのみを反映する
        (未来のCorporate Actionは構造的に混入しない)。
        """
        ...

    def bar_on(self, code: str, session_date: date, *, as_of: datetime) -> AdjustedOHLCVBar | None:
        """特定日のBarを、as_of時点の調整基準で返す(該当データが無ければNone)。

        Trade Entry/Exitの価格取得に使う。Entry/Exitの2点は同一のas_of
        (通常はexit_dateの大引け)で調整することで、保有期間中に発生した
        Corporate Actionがあっても、Entry/Exit間のReturn計算が正しく連続する
        (保有期間中の分割でReturnが不正に歪まない)。
        """
        ...


class StaticPriceHistory:
    """既に確定した(Corporate Action調整を考慮しない、あるいは調整不要な)固定Bar列を
    そのまま返す実装。fixture等、株式分割を扱わないテスト・合成データ向け。

    as_ofはsession_dateのフィルタにのみ使い、Corporate Action調整計算は一切行わない
    (Phase3A.1以前の`price_history`引数(plain dict)と完全に同じ挙動)。
    """

    def __init__(self, bars_by_code: Mapping[str, Sequence[AdjustedOHLCVBar]]) -> None:
        self._by_code: dict[str, list[AdjustedOHLCVBar]] = {
            code: sorted(bars, key=lambda b: b.session_date) for code, bars in bars_by_code.items()
        }
        self._by_code_by_date: dict[str, dict[date, AdjustedOHLCVBar]] = {
            code: {b.session_date: b for b in bars} for code, bars in self._by_code.items()
        }

    def bars_up_to(self, code: str, as_of: datetime) -> Sequence[AdjustedOHLCVBar]:
        return [b for b in self._by_code.get(code, ()) if b.session_date <= as_of.date()]

    def bar_on(self, code: str, session_date: date, *, as_of: datetime) -> AdjustedOHLCVBar | None:
        del as_of  # Staticな実装ではas_ofによる調整は行わない
        return self._by_code_by_date.get(code, {}).get(session_date)


class AsOfAdjustedPriceHistory:
    """Raw Price History + Corporate Action Eventsから、decision_atごとにPIT-safeな
    Adjusted Bar列を都度構築する実装(D0034/D0035)。

    Raw O/H/L/C/VoをCanonical Historyとし(RESEARCH_RULES.md参照)、Provider固有の
    Adjusted fields(AdjO/AdjC等)は使わない。`build_provider_derived_adjusted_bars`
    (`lib/schemas/price_data.py`)を都度呼び出すことで、「as_ofより後に効力発生する
    Corporate Actionは絶対に混入しない」ことを構造的に保証する
    (Raw Dataset自体に未来のCorporate Action Eventが含まれていても構わない。
    それを「使ってしまう」ことだけを防ぐ)。

    Performance: 銘柄ごとにRaw bars/Eventsを事前indexしておき、呼び出しのたびに
    「その銘柄の」raw_bars/eventsだけをas_ofで絞り込む(他銘柄の計算とは独立、
    Test Eのticker isolationが構造的に成り立つ)。Phase3A.2では正確性を優先し、
    as_of単位のcacheや累積factorの差分更新のような最適化までは行っていないが、
    将来的にそれらを追加しやすい構造にしている。
    """

    def __init__(
        self,
        raw_bars_by_code: Mapping[str, Sequence[RawOHLCVBar]],
        events_by_code: Mapping[str, Sequence[CorporateAction]],
    ) -> None:
        self._raw_by_code: dict[str, list[RawOHLCVBar]] = {
            code: sorted(bars, key=lambda b: b.session_date) for code, bars in raw_bars_by_code.items()
        }
        self._events_by_code: dict[str, list[CorporateAction]] = {code: list(events) for code, events in events_by_code.items()}

    def bars_up_to(self, code: str, as_of: datetime) -> Sequence[AdjustedOHLCVBar]:
        raw_bars = [b for b in self._raw_by_code.get(code, ()) if b.session_date <= as_of.date()]
        events = self._events_by_code.get(code, ())
        return build_provider_derived_adjusted_bars(raw_bars, list(events), as_of=as_of)

    def bar_on(self, code: str, session_date: date, *, as_of: datetime) -> AdjustedOHLCVBar | None:
        for bar in self.bars_up_to(code, as_of):
            if bar.session_date == session_date:
                return bar
        return None
