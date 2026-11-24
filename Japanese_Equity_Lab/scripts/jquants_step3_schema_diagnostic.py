"""Step 3 追加Field/Endpointの Observed Wire Schema 診断(読み取り専用)。

`JQUANTS_V2_STEP3_SOURCE_ONBOARDING.md` §15 の確認項目を1回の実行で観測する。
手順の全体は `JQUANTS_V2_STEP3_LOCAL_VALIDATION_GUIDE.md`。

**このスクリプトは観測のみを行う。** 正規化しない。Metricを作らない。Adapterに
Endpointを実装しない。判定も行わない(「期待どおりか」は人間が見る)。

Rate Limit: 未実装Endpointも `JQuantsAdapter._get_all_pages` を経由するので、
既存の `_throttle()`(1.05秒間隔)がそのまま効く。`requests` で直接叩かない
(ルートCLAUDE.md §5)。

APIキーは `.env` から読み、値は一切出力しない。

実行例:
    python scripts/jquants_step3_schema_diagnostic.py
    python scripts/jquants_step3_schema_diagnostic.py --save-snapshot
    python scripts/jquants_step3_schema_diagnostic.py --code 8035 --reit-code 89520
"""

from __future__ import annotations

import argparse
import sys
import traceback
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

sys.dont_write_bytecode = True
_LAB_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = _LAB_DIR.parent
sys.path.insert(0, str(_LAB_DIR))

from dotenv import load_dotenv  # noqa: E402
from lib.cli_io import HUMAN_READABLE, JSON_SAFE, force_output_encoding  # noqa: E402
from lib.data_sources.jquants import JQuantsAdapter  # noqa: E402
from lib.errors import DataSourceError  # noqa: E402

WATCHED_FIELDS = (
    "ShEq",
    "NCShEq",
    "ROE",
    "NCROE",
    "BPS",
    "NCBPS",
    "Eq",
    "NCEq",
    "ShOutFY",
    "TrShFY",
    "AvgSh",
    "DivAnn",
    "FDivAnn",
    "NxFDivAnn",
    "PayoutRatioAnn",
    "DivUnit",
    "FDivUnit",
    "OdP",
    "OP",
)
"""今回マッピング候補になるField。空欄率と「いつから入っているか」を見る。

**ここに書くのは公式仕様または `normalize.py` で確認済みのField名だけ。**
2026-11-24に `OpP` という推測した名前を入れてしまい、REITで0/27になったのを
「REITは営業利益を開示しない」と読みかけた。実在する名前は `OP` である
(`normalize.py` の `_METRIC_FIELD_MAP`)。存在しないFieldは常に0件になるので、
**充填率0は「開示されていない」の証拠にならない。** 下の存在チェックで切り分ける。
"""

SPLIT_WINDOW = ("2021-09-25", "2021-10-08")
"""7203で1株当たり基準が切り替わった前後。EPS/BPSが調整済みかを見る。"""


def _filled(row: dict[str, Any], field: str) -> bool:
    return str(row.get(field, "")).strip() != ""


def _section(title: str) -> None:
    print()
    print("=" * 72)
    print(title)
    print("=" * 72)


def _run(label: str, fn: Any) -> Any:
    """1項目が失敗しても残りを続ける。失敗は隠さず表示する。"""
    try:
        return fn()
    except DataSourceError as exc:
        print(f"  !! {label}: DataSourceError: {exc}")
    except Exception:  # noqa: BLE001 - 診断スクリプトなので全部見せる
        print(f"  !! {label}: 予期しない例外")
        traceback.print_exc(limit=3)
    return None


def check_fins_fields(adapter: JQuantsAdapter, code: str, *, label: str = "普通株") -> list[dict[str, Any]]:
    """項目1・2: `ShEq`/`ROE` 等が過去行にも入っているか。

    REITでも同じことを見る。`/equities/valuation` がREITでほぼ空だと確定したので、
    REIT側の値が `/fins/summary` から取れるかどうかが併用方針の成否を決める。
    """
    _section(f"[1,2] /fins/summary 追加Fieldの充填状況 ({label} code={code})")
    result = adapter.fetch_financial_statements(codes=[code], start_date=date(2015, 1, 1), end_date=date.today())
    rows: list[dict[str, Any]] = list(result.payload)
    print(f"  records: {len(rows)}  retrieved_at: {result.retrieved_at.isoformat()}")
    if not rows:
        print("  !! 0件。以降の判定はできない")
        return rows

    print(f"  fields in first record: {len(rows[0])}")

    # Field名の綴り間違いを充填率0と混同しないための切り分け。
    schema = {k for r in rows for k in r}
    unknown = [f for f in WATCHED_FIELDS if f not in schema]
    if unknown:
        print()
        print("  !! Schemaに存在しないField名(観測ではなく名前の誤り):")
        for field in unknown:
            print(f"       {field}")
        print("     -> 公式仕様で名前を確認すること。0件を「未開示」と読まない。")

    print()
    print("  充填率(Schemaに存在するFieldのみ):")
    for field in WATCHED_FIELDS:
        if field not in schema:
            continue
        n = sum(1 for r in rows if _filled(r, field))
        bar = "#" * round(20 * n / len(rows))
        print(f"    {field:16s} {n:3d}/{len(rows)}  {bar}")

    ordered = sorted(rows, key=lambda r: (str(r.get("DiscDate", "")), str(r.get("DiscTime", ""))))
    print()
    print("  いつから入っているか(最初に値が現れた開示):")
    for field in ("ShEq", "ROE", "BPS", "ShOutFY", "AvgSh", "DivAnn"):
        first = next((r for r in ordered if _filled(r, field)), None)
        print(f"    {field:16s} {first.get('DiscDate') if first else '(一度も現れない)'}")

    print()
    print("  年次推移(決算短信系のみ、DiscDate順):")
    print(f"    {'DiscDate':12s} {'Per':4s} {'ShEq':>18s} {'ROE':>9s} {'BPS':>10s}")
    for r in ordered:
        doc = str(r.get("DocType", ""))
        if "FinancialStatements" not in doc:
            continue
        print(
            f"    {str(r.get('DiscDate', '')):12s} {str(r.get('CurPerType', '')):4s} "
            f"{(str(r.get('ShEq', '')).strip() or '-'):>18s} "
            f"{(str(r.get('ROE', '')).strip() or '-'):>9s} "
            f"{(str(r.get('BPS', '')).strip() or '-'):>10s}"
        )
    return rows


def check_doc_types(rows: list[dict[str, Any]]) -> None:
    """項目7: 実データのDocTypeが公式一覧42種に収まるか。"""
    _section("[7] DocType の集合")
    seen = sorted({str(r.get("DocType", "")) for r in rows})
    for doc in seen:
        n = sum(1 for r in rows if str(r.get("DocType", "")) == doc)
        suffix = doc.rsplit("_", 1)[-1] if "_" in doc else "(なし)"
        print(f"    {doc:56s} {n:3d}  基準={suffix}")
    print()
    print("  公式一覧の会計基準接尾辞: JP / US / IFRS / JMIS / Foreign / REIT")
    print("  (一覧外の値があれば、公式一覧が網羅的でない証拠。DECISIONS.mdへ追記する)")


def check_prodcat(adapter: JQuantsAdapter, codes: tuple[str, ...]) -> None:
    """項目6: `ProdCat` で銘柄種別が判定できるか。"""
    _section("[6] /equities/master の ProdCat")
    master = list(adapter.fetch_equities_master().payload)
    print(f"  master records: {len(master)}")
    wanted = {c[:4] for c in codes}
    print(f"    {'Code':8s} {'ProdCat':8s} {'Mkt':6s} {'S33':6s} 会社名")
    for row in master:
        code = str(row.get("Code", ""))
        if code[:4] not in wanted:
            continue
        print(
            f"    {code:8s} {str(row.get('ProdCat', '-')):8s} {str(row.get('Mkt', '-')):6s} "
            f"{str(row.get('S33', '-')):6s} {row.get('CoName', '')}"
        )
    print()
    print("  011=内国株券(優先株も含む) 012=優先出資証券 013=REIT 014=ETF")
    print("  021=外国株券 022=外国REIT 023=外国ETF 024=外国株預託証券")


def check_valuation(adapter: JQuantsAdapter, code: str, *, label: str) -> None:
    """項目3・4: `/equities/valuation` の実Fieldと銘柄種別ごとの挙動。"""
    _section(f"[3,4] /equities/valuation ({label} code={code})")
    rows = list(adapter._get_all_pages("/equities/valuation", {"code": code}, error_label="valuation"))
    print(f"  records: {len(rows)}")
    if not rows:
        print("  !! 0件")
        return
    print(f"  fields: {sorted(rows[0].keys())}")
    dates = [str(r.get("Date", "")) for r in rows if r.get("Date")]
    if dates:
        print(f"  oldest: {min(dates)}   newest: {max(dates)}")
    print()
    print("  各Fieldのnull率:")
    for field in sorted(rows[0].keys()):
        if field in ("Date", "Code"):
            continue
        n = sum(1 for r in rows if r.get(field) is None or str(r.get(field, "")).strip() == "")
        print(f"    {field:10s} null {n:5d}/{len(rows)}")
    print()
    print(f"  最新行: {rows[-1]}")


def check_split_continuity(adapter: JQuantsAdapter, code: str) -> None:
    """項目5: 一株当たり指標が分割をまたいで連続するか。"""
    start, end = SPLIT_WINDOW
    _section(f"[5] /equities/valuation 分割前後の連続性 (code={code}, {start}〜{end})")
    rows = list(
        adapter._get_all_pages(
            "/equities/valuation",
            {"code": code, "from": start, "to": end},
            error_label="valuation-split",
        )
    )
    if not rows:
        print("  !! 0件。この期間はカバレッジ外の可能性")
        return
    print(f"    {'Date':12s} {'EPS':>10s} {'BPS':>10s} {'PER':>9s} {'PBR':>8s}")
    for r in sorted(rows, key=lambda x: str(x.get("Date", ""))):
        print(
            f"    {str(r.get('Date', '')):12s} {str(r.get('EPS', '-')):>10s} "
            f"{str(r.get('BPS', '-')):>10s} {str(r.get('PER', '-')):>9s} {str(r.get('PBR', '-')):>8s}"
        )
    print()
    print("  段差があれば未調整(per_share.py の対象を広げる)。連続なら調整済み。")


def check_earnings_date(adapter: JQuantsAdapter, code: str) -> None:
    """項目8: `/fins/earnings-date` の実Field。"""
    _section(f"[8] /fins/earnings-date (code={code})")
    rows = list(adapter._get_all_pages("/fins/earnings-date", {"code": code}, error_label="earnings-date"))
    print(f"  records: {len(rows)}")
    if not rows:
        print("  !! 0件。検索キーの指定方法を見直す")
        return
    print(f"  fields: {sorted(rows[0].keys())}")
    print()
    print("  先頭5件:")
    for r in rows[:5]:
        print(f"    {r}")
    print()
    print("  末尾3件:")
    for r in rows[-3:]:
        print(f"    {r}")


def check_range_params(adapter: JQuantsAdapter, code: str) -> None:
    """仕様書との食い違い: `/fins/summary` は `from`/`to` を受け付けるのか。"""
    _section(f"[追加] /fins/summary の from/to は効いているか (code={code})")
    n1 = len(adapter._get_all_pages("/fins/summary", {"code": code}, error_label="no-range"))
    n2 = len(
        adapter._get_all_pages(
            "/fins/summary",
            {"code": code, "from": "2024-01-01", "to": "2024-12-31"},
            error_label="with-range",
        )
    )
    print(f"  code のみ      : {n1} 件")
    print(f"  code+from+to  : {n2} 件")
    print(f"  同数か        : {n1 == n2}")
    print()
    print("  公式パラメータ表は code / date / cursor の3つで from/to を載せていない。")
    print("  同数なら送信しても無視されている(D0043の実観測の説明になる)。")


def save_snapshot(adapter: JQuantsAdapter, code: str) -> None:
    """観測した生Payloadを既存の RawSnapshotStore で保存する。"""
    from lib.snapshot import RawSnapshotStore

    _section(f"Raw Snapshot 保存 (code={code})")
    result = adapter.fetch_financial_statements(codes=[code], start_date=date(2015, 1, 1), end_date=date.today())
    store = RawSnapshotStore(_LAB_DIR / "01_data" / "raw")
    snapshot_id = f"SNAP_JQ_STEP3_FINS_{code}_{datetime.now(UTC):%Y%m%d}"
    manifest = store.save(result, snapshot_id=snapshot_id)
    print(f"  saved: {manifest.snapshot_id}")
    print(f"  records: {manifest.record_count}")
    print(f"  hash: {manifest.content_hash[:16]}...")
    print()
    print("  同一DiscNoの上書き訂正で訂正前の値は失われる。これが唯一の記録になる。")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--code", default="7203", help="普通株の確認対象(既定: 7203)")
    parser.add_argument("--reit-code", default="89510", help="REITの確認対象(既定: 89510 日本ビルファンド)")
    parser.add_argument("--save-snapshot", action="store_true", help="生PayloadをRawSnapshotStoreへ保存する")
    args = parser.parse_args(argv)

    # リダイレクト時のcp932符号化エラーを防ぐ(lib/cli_io.py の経緯を参照)。
    # BOMは先頭1つだけにしたいので、`2>&1` で合流するstderrには付けない。
    force_output_encoding(HUMAN_READABLE, streams=[sys.stdout])
    force_output_encoding(JSON_SAFE, streams=[sys.stderr])

    load_dotenv(_REPO_ROOT / ".env")
    adapter = JQuantsAdapter()
    if not adapter.configured:
        print("JQUANTS_API_KEY が設定されていません(.env を確認してください)", file=sys.stderr)
        return 2

    print("J-Quants V2 Step 3 Schema Diagnostic - 読み取り専用・観測のみ")
    print(f"実行: {datetime.now(UTC).isoformat()}  対象: {args.code} / {args.reit_code}")

    rows = _run("fins fields", lambda: check_fins_fields(adapter, args.code)) or []
    if rows:
        _run("doc types", lambda: check_doc_types(rows))
    reit_rows = _run("fins fields reit", lambda: check_fins_fields(adapter, args.reit_code, label="REIT")) or []
    if reit_rows:
        _run("doc types reit", lambda: check_doc_types(reit_rows))
    _run("prodcat", lambda: check_prodcat(adapter, (args.code, args.reit_code)))
    _run("valuation common", lambda: check_valuation(adapter, args.code, label="普通株"))
    _run("valuation reit", lambda: check_valuation(adapter, args.reit_code, label="REIT"))
    _run("split continuity", lambda: check_split_continuity(adapter, args.code))
    _run("earnings date", lambda: check_earnings_date(adapter, args.code))
    _run("range params", lambda: check_range_params(adapter, args.code))
    if args.save_snapshot:
        _run("snapshot", lambda: save_snapshot(adapter, args.code))

    print()
    print("完了。期待との照合は JQUANTS_V2_STEP3_LOCAL_VALIDATION_GUIDE.md の §I を参照。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
