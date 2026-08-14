"""共通の例外クラス。"""


class ProviderError(Exception):
    """データ取得に失敗した際の理由付きエラー。呼び出し側は必ずcatchしてUIに理由を表示する。"""
