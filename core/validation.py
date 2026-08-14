"""機械的に判定可能な異常値チェック。

Claude(LLM)は取得した数値が実態として正しいかを判断できないため、
「明らかにおかしい値」を機械的なルールで検知し、警告として表示・ログする。
数値そのものは書き換えず、警告を付与するだけに留める(勝手に補正しない)。
"""

from __future__ import annotations

import logging

from core.models import StockSnapshot, ValidationWarning

logger = logging.getLogger(__name__)

# しきい値は「明らかに異常」と判断できる範囲に留め、正常なレンジを誤検知しない
PER_MAX = 500
PER_MIN = -500
PBR_MAX = 100
PBR_MIN = 0
DIVIDEND_YIELD_MAX = 0.20  # 20%超は通常あり得ない
ROE_ABS_MAX = 5.0  # 500%超

# 前日比・前期比などの変化率チェック用(将来の拡張ポイント)
CHANGE_RATE_MAX = 0.60  # 1日で60%超の変動は異常の可能性が高い


def validate_snapshot(snapshot: StockSnapshot) -> list[ValidationWarning]:
    """スナップショットの各指標を検査し、異常が疑われる項目の警告リストを返す。"""
    warnings: list[ValidationWarning] = []

    if snapshot.per is not None and not (PER_MIN <= snapshot.per <= PER_MAX):
        warnings.append(
            ValidationWarning(
                field="per",
                message=f"PERが異常値の可能性があります({snapshot.per})",
                raw_value=snapshot.per,
            )
        )

    if snapshot.pbr is not None and not (PBR_MIN <= snapshot.pbr <= PBR_MAX):
        warnings.append(
            ValidationWarning(
                field="pbr",
                message=f"PBRが異常値の可能性があります({snapshot.pbr})",
                raw_value=snapshot.pbr,
            )
        )

    if snapshot.dividend_yield is not None and not (0 <= snapshot.dividend_yield <= DIVIDEND_YIELD_MAX):
        warnings.append(
            ValidationWarning(
                field="dividend_yield",
                message=f"配当利回りが異常値の可能性があります({snapshot.dividend_yield:.2%})",
                raw_value=snapshot.dividend_yield,
            )
        )

    if snapshot.roe is not None and abs(snapshot.roe) > ROE_ABS_MAX:
        warnings.append(
            ValidationWarning(
                field="roe",
                message=f"ROEが異常値の可能性があります({snapshot.roe:.2%})",
                raw_value=snapshot.roe,
            )
        )

    if snapshot.week52_high is not None and snapshot.week52_low is not None and snapshot.week52_high < snapshot.week52_low:
        warnings.append(
            ValidationWarning(
                field="week52_range",
                message="52週高値が52週安値を下回っています(取得ミスの可能性)",
            )
        )

    if snapshot.price is not None and snapshot.price <= 0:
        warnings.append(
            ValidationWarning(
                field="price",
                message=f"株価が0以下です({snapshot.price})",
                raw_value=snapshot.price,
            )
        )

    if warnings:
        logger.warning(
            "validation warnings for %s (%s): %s",
            snapshot.code,
            snapshot.market.value,
            [w.message for w in warnings],
        )

    return warnings


def check_change_rate(previous: float, current: float, field_name: str) -> ValidationWarning | None:
    """前日比・前期比等の変化率が非現実的でないかチェックする。"""
    if previous == 0:
        return None
    rate = (current - previous) / abs(previous)
    if abs(rate) > CHANGE_RATE_MAX:
        warning = ValidationWarning(
            field=field_name,
            message=f"{field_name}の変化率が異常値の可能性があります({rate:.1%})",
            raw_value=rate,
        )
        logger.warning("change-rate validation warning: %s", warning.message)
        return warning
    return None
