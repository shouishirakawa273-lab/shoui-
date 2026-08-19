"""Japanese Equity Research Lab 共通の例外。"""

from __future__ import annotations


class LookAheadBiasError(Exception):
    """decision_at時点でまだ利用可能でなかった情報が渡された場合に送出する。"""


class HypothesisImmutabilityError(Exception):
    """LOCKED以降のHypothesisの条件(terms)を書き換えようとした場合に送出する。"""


class AppendOnlyViolationError(Exception):
    """追記専用ストレージ(Experiment Registry等)への上書き・重複IDを検知した場合に送出する。"""


class DataSourceError(Exception):
    """外部データソース(J-Quants等)への接続・認証・取得に失敗した場合に送出する。

    メッセージ・chained exceptionにAPIキー/トークンを含めないこと
    (URLクエリパラメータに認証情報を載せるAPIのエラーは特に注意する)。"""


class PreregistrationImmutabilityError(Exception):
    """PREREGISTERED以降のPreregistrationのCore Fieldsを書き換えようとした場合に
    送出する(Phase5、`lib.research.preregistration`)。"""


class LockedTestAccessError(Exception):
    """Locked TestをUnlockせずに読もうとした場合、または既にUnlock済みのLocked
    Testを再度Unlockしようとした場合に送出する(Phase5、`lib.research.locked_
    test`)。"""
