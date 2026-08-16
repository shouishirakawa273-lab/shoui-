"""Japanese Equity Research Lab 共通の例外。"""

from __future__ import annotations


class LookAheadBiasError(Exception):
    """decision_at時点でまだ利用可能でなかった情報が渡された場合に送出する。"""


class HypothesisImmutabilityError(Exception):
    """LOCKED以降のHypothesisの条件(terms)を書き換えようとした場合に送出する。"""


class AppendOnlyViolationError(Exception):
    """追記専用ストレージ(Experiment Registry等)への上書き・重複IDを検知した場合に送出する。"""
