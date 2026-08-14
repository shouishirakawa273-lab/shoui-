"""日本株・米国株スクリーニング/比較ツール — Streamlitエントリポイント。

起動方法:
    streamlit run app.py
"""

from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from dotenv import load_dotenv

from core.cache import Cache
from core.comparison import (
    MAX_COMPARISON_TARGETS,
    MIN_COMPARISON_TARGETS,
    build_comparison_table,
    normalize_for_radar,
)
from core.errors import ProviderError
from core.forecast import get_forecast
from core.lookup import load_snapshot, load_snapshots
from core.models import NOT_AVAILABLE
from core.providers.market_data import infer_market
from core.screening import Operator, ScreeningRule, screen
from core.watchlist import Watchlist, list_watchlists

load_dotenv()

st.set_page_config(page_title="株式スクリーニング・比較ツール", layout="wide")


@st.cache_resource
def get_cache() -> Cache:
    return Cache()


DISCLAIMER = (
    "⚠️ **投資助言ではありません。** "
    "本ツールが表示するデータは参考情報であり、正確性・最新性を保証しません。"
    "投資判断は自己責任で行ってください。"
)


def render_disclaimer() -> None:
    st.warning(DISCLAIMER)


def render_snapshot_card(code: str) -> None:
    try:
        snapshot = load_snapshot(code, cache=get_cache())
    except ProviderError as exc:
        st.error(f"{code}: {exc}")
        return

    st.subheader(f"{snapshot.name or code} ({code})")
    st.caption(f"取得日時: {snapshot.fetched_at.strftime('%Y-%m-%d %H:%M')} / データソース: {snapshot.source}")

    if snapshot.warnings:
        for w in snapshot.warnings:
            st.warning(f"⚠️ {w.message}")

    cols = st.columns(4)
    cols[0].metric("株価", f"{snapshot.price:,.2f} {snapshot.currency}" if snapshot.price else NOT_AVAILABLE)
    cols[1].metric("PER", f"{snapshot.per:.2f}" if snapshot.per is not None else NOT_AVAILABLE)
    cols[2].metric("PBR", f"{snapshot.pbr:.2f}" if snapshot.pbr is not None else NOT_AVAILABLE)
    cols[3].metric("配当利回り", f"{snapshot.dividend_yield:.2%}" if snapshot.dividend_yield is not None else NOT_AVAILABLE)

    cols2 = st.columns(4)
    cols2[0].metric("ROE", f"{snapshot.roe:.2%}" if snapshot.roe is not None else NOT_AVAILABLE)
    cols2[1].metric("時価総額", f"{snapshot.market_cap:,.0f}" if snapshot.market_cap is not None else NOT_AVAILABLE)
    cols2[2].metric("52週高値", f"{snapshot.week52_high:,.2f}" if snapshot.week52_high is not None else NOT_AVAILABLE)
    cols2[3].metric("52週安値", f"{snapshot.week52_low:,.2f}" if snapshot.week52_low is not None else NOT_AVAILABLE)

    st.markdown(f"**セクター**: {snapshot.sector or NOT_AVAILABLE} / **業種**: {snapshot.industry or NOT_AVAILABLE}")

    st.markdown("##### 直近業績(実績)")
    perf_cols = st.columns(3)
    perf_cols[0].metric("売上高", f"{snapshot.revenue_ttm:,.0f}" if snapshot.revenue_ttm is not None else NOT_AVAILABLE)
    perf_cols[1].metric(
        "営業利益", f"{snapshot.operating_income_ttm:,.0f}" if snapshot.operating_income_ttm is not None else NOT_AVAILABLE
    )
    perf_cols[2].metric("純利益", f"{snapshot.net_income_ttm:,.0f}" if snapshot.net_income_ttm is not None else NOT_AVAILABLE)

    st.markdown("##### 業績予想")
    market = infer_market(code)
    try:
        forecast = get_forecast(code, market)
    except ProviderError as exc:
        st.info(f"業績予想を取得できませんでした: {exc}")
        return

    forecast_rows = []
    for v in forecast.values:
        if v.available:
            forecast_rows.append(
                {
                    "項目": v.metric,
                    "値": v.value,
                    "区分": f"🔮 {v.label.value}" if v.label else "-",
                    "出典": v.source,
                    "更新日": v.as_of,
                }
            )
        else:
            forecast_rows.append({"項目": v.metric, "値": NOT_AVAILABLE, "区分": "-", "出典": v.source, "更新日": v.as_of or "-"})
    st.dataframe(pd.DataFrame(forecast_rows), hide_index=True, use_container_width=True)
    st.caption(
        "業績予想は実績値と異なり、会社発表またはアナリストによる見込み値です。上表の「区分」「出典」「更新日」を必ず確認してください。"
    )


def render_search_tab() -> None:
    st.markdown("証券コード(例: 7203)またはティッカー(例: AAPL)を入力してください。")
    code = st.text_input("銘柄コード / ティッカー", value="7203")
    if st.button("取得", key="search_fetch"):
        render_snapshot_card(code.strip())


def render_comparison_tab() -> None:
    st.markdown(f"{MIN_COMPARISON_TARGETS}〜{MAX_COMPARISON_TARGETS}銘柄を入力してください(カンマ区切り)。")
    raw = st.text_input("銘柄コード一覧", value="7203, 6758, AAPL")
    codes = [c.strip() for c in raw.split(",") if c.strip()]

    if st.button("比較", key="compare_fetch"):
        if not (MIN_COMPARISON_TARGETS <= len(codes) <= MAX_COMPARISON_TARGETS):
            st.error(f"{MIN_COMPARISON_TARGETS}〜{MAX_COMPARISON_TARGETS}銘柄を指定してください(現在{len(codes)}件)")
            return

        snapshots, errors = load_snapshots(codes, cache=get_cache())
        for code, reason in errors.items():
            st.error(f"{code}: {reason}")
        if not snapshots:
            return

        st.markdown("##### 指標比較表")
        st.dataframe(pd.DataFrame(build_comparison_table(snapshots)), hide_index=True, use_container_width=True)

        st.markdown("##### レーダーチャート(指標を0〜1に正規化。PER/PBRは低いほど高スコア)")
        series = normalize_for_radar(snapshots)
        categories = list(series.keys())
        fig = go.Figure()
        for i, s in enumerate(snapshots):
            fig.add_trace(
                go.Scatterpolar(
                    r=[series[cat][i] for cat in categories],
                    theta=categories,
                    fill="toself",
                    name=s.name or s.code,
                )
            )
        fig.update_layout(polar=dict(radialaxis=dict(visible=True, range=[0, 1])), showlegend=True)
        st.plotly_chart(fig, use_container_width=True)


def render_screening_tab() -> None:
    watchlists = list_watchlists()
    if not watchlists:
        st.info("watchlists/ にウォッチリスト(JSON)がありません。")
        return

    selected = st.selectbox("ウォッチリスト", watchlists)
    wl = Watchlist.load(selected)
    st.caption(f"対象銘柄: {', '.join(wl.codes)}")

    st.markdown("##### フィルタ条件")
    col1, col2 = st.columns(2)
    with col1:
        per_max = st.number_input("PER 以下", value=0.0, step=1.0, help="0のときはフィルタしない")
        pbr_max = st.number_input("PBR 以下", value=0.0, step=0.1, help="0のときはフィルタしない")
    with col2:
        dividend_min = st.number_input("配当利回り(%) 以上", value=0.0, step=0.1, help="0のときはフィルタしない")
        market_cap_min = st.number_input("時価総額 以上", value=0.0, step=1_000_000.0, help="0のときはフィルタしない")

    if st.button("スクリーニング実行"):
        snapshots, errors = load_snapshots(wl.codes, cache=get_cache())
        for code, reason in errors.items():
            st.error(f"{code}: {reason}")

        rules: list[ScreeningRule] = []
        if per_max > 0:
            rules.append(ScreeningRule(field="per", operator=Operator.LTE, threshold=per_max))
        if pbr_max > 0:
            rules.append(ScreeningRule(field="pbr", operator=Operator.LTE, threshold=pbr_max))
        if dividend_min > 0:
            rules.append(ScreeningRule(field="dividend_yield", operator=Operator.GTE, threshold=dividend_min / 100))
        if market_cap_min > 0:
            rules.append(ScreeningRule(field="market_cap", operator=Operator.GTE, threshold=market_cap_min))

        result = screen(snapshots, rules) if rules else snapshots
        st.markdown(f"##### 該当銘柄: {len(result)}件")
        if result:
            st.dataframe(pd.DataFrame(build_comparison_table(result)), hide_index=True, use_container_width=True)


def main() -> None:
    st.title("📈 株式スクリーニング・比較ツール")
    render_disclaimer()

    tab1, tab2, tab3 = st.tabs(["銘柄検索", "比較", "スクリーニング"])
    with tab1:
        render_search_tab()
    with tab2:
        render_comparison_tab()
    with tab3:
        render_screening_tab()


if __name__ == "__main__":
    main()
