"""銘柄種別の判定(`ProdCat`)。

**値を見てからソースを選ばないための土台である。** `/equities/valuation` は
REITで `MktCap` 以外すべてnullを返すが(89510で2440/2440行を観測)、nullになる
理由はREITだけではなく、新規上場・決算期変更・未開示も含む。したがって
「nullなら別のソースから計算する」という実装は、**本当に取得不可な値を自作値で
埋めることになり、ルートCLAUDE.mdの「取得できない項目を他の値から計算・推測して
埋めることは禁止」に正面から違反する。**

そこで**取得する前に銘柄種別でソースを決め打ちする**。選んだソースがnullを返したら
「取得不可」とし、別ソースへ黙って切り替えない。

`ProdCat` は `/equities/master` の宣言Fieldであり、公式仕様に次の性質がある
(`https://jpx-jquants.com/ja/spec/eq-master/product-category`):

- 銘柄マスタの値を無修正で返す
- コード定義は全期間(2008-05-07開始)を通じて同一
- 全期間・全銘柄で値が存在し、欠損はない
- **`011`(内国株券)には優先株等も含まれるため、`ProdCat` だけでは普通株を特定
  できない**
- ETN・インフラファンドに専用コードはない

最後の2点が効く。`011` の銘柄が `/equities/valuation` でnullを返した場合、それは
優先株だった可能性を含む。上の原則どおり「取得不可」とし、別ソースへ切り替えない
——優先株のPERを自作しても意味がないので、この挙動は正しい方向に転ぶ。

`ProdCat` は日付ごとのマスタ値なので、PIT的には**判定時点の値**を使う。
"""

from __future__ import annotations

import logging
from collections.abc import Mapping, Sequence
from enum import StrEnum

logger = logging.getLogger(__name__)

PROD_CAT_DOMESTIC_SHARE = "011"
PROD_CAT_PREFERRED_SUBSCRIPTION = "012"
PROD_CAT_REIT = "013"
PROD_CAT_ETF = "014"
PROD_CAT_FOREIGN_SHARE = "021"
PROD_CAT_FOREIGN_REIT = "022"
PROD_CAT_FOREIGN_ETF = "023"
PROD_CAT_FOREIGN_DEPOSITARY_RECEIPT = "024"


class InstrumentKind(StrEnum):
    """ソースの決め打ちに必要な粒度だけを持つ分類。

    `ProdCat` の8コードをそのまま持たないのは、**この分類が「どのFieldから読むか」
    を決めるためのものだから**。内国株券と外国株券は同じField群から読むので
    区別しない。REITは1口当たり分配金を使うので分ける。
    """

    SHARE = "SHARE"
    """株式(内国`011`・外国`021`・預託証券`024`)。一株当たりの配当Fieldを使う。

    **`011`には優先株等も含まれる**ため、これは「普通株である」という主張ではない。
    """
    REIT = "REIT"
    """REIT(内国`013`・外国`022`)。1口当たり分配金Fieldを使う。"""
    OTHER = "OTHER"
    """ETF(`014`/`023`)・優先出資証券(`012`)等。どのFieldが適切か確認していない。"""
    UNKNOWN = "UNKNOWN"
    """`ProdCat` が取得できなかった。欠損は無いはずなので、起きたら調査対象。"""


_PROD_CAT_TO_KIND: dict[str, InstrumentKind] = {
    PROD_CAT_DOMESTIC_SHARE: InstrumentKind.SHARE,
    PROD_CAT_FOREIGN_SHARE: InstrumentKind.SHARE,
    PROD_CAT_FOREIGN_DEPOSITARY_RECEIPT: InstrumentKind.SHARE,
    PROD_CAT_REIT: InstrumentKind.REIT,
    PROD_CAT_FOREIGN_REIT: InstrumentKind.REIT,
    PROD_CAT_PREFERRED_SUBSCRIPTION: InstrumentKind.OTHER,
    PROD_CAT_ETF: InstrumentKind.OTHER,
    PROD_CAT_FOREIGN_ETF: InstrumentKind.OTHER,
}


def classify_prod_cat(prod_cat: str | None) -> InstrumentKind:
    """`ProdCat` を分類する。未知のコードは `UNKNOWN` へfail closedする。

    新しい商品区分が追加された場合に `OTHER` へ落とさないのは、`OTHER` が
    「既知だが対象外」を意味するため。未知は未知として露出させる。
    """
    if prod_cat is None or prod_cat.strip() == "":
        return InstrumentKind.UNKNOWN
    kind = _PROD_CAT_TO_KIND.get(prod_cat.strip())
    if kind is None:
        logger.warning("screener: 未知のProdCat '%s' のためInstrumentKindをUNKNOWNにfail closedします", prod_cat)
        return InstrumentKind.UNKNOWN
    return kind


def classify_codes(
    *,
    codes: Sequence[str],
    master_payload: Sequence[Mapping[str, object]],
) -> dict[str, InstrumentKind]:
    """内部Code -> `InstrumentKind`。

    `master_payload` は `/equities/master` のRaw。Provider Codeは5桁、内部Codeは
    4桁で、**ここでProvider Codeを内部Codeへ書き換えない**。先頭4桁の一致で
    引き当てるだけにして、`lib/sources/entity_registry.py` の責務を奪わない。

    マスタに現れないCodeは `UNKNOWN`。空欄にせず明示する。
    """
    by_prefix: dict[str, str] = {}
    for row in master_payload:
        raw_code = row.get("Code")
        if not isinstance(raw_code, str) or len(raw_code) < 4:
            continue
        prod_cat = row.get("ProdCat")
        by_prefix[raw_code[:4]] = prod_cat if isinstance(prod_cat, str) else ""

    resolved: dict[str, InstrumentKind] = {}
    for code in codes:
        prefix = code[:4]
        if prefix not in by_prefix:
            logger.warning("screener: %s が/equities/masterに見つからずInstrumentKindはUNKNOWNです", code)
            resolved[code] = InstrumentKind.UNKNOWN
            continue
        resolved[code] = classify_prod_cat(by_prefix[prefix])
    return resolved
