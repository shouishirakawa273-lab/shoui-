"""J-Quants Provider Code(5桁)とResearch Lab内部Code(4桁)の対応付け。

**実SmokeTestで確認済みの事実**(ユーザー確認、2026-08-16、DECISIONS.md D0036):
内部Code(普通株、例: "7203")をrequestすると、J-Quants API V2のresponseでは
``"Code": "72030"``(5桁)として返ってくる。5桁化された際、末尾1桁が銘柄種別を表し、
普通株は"0"、という理解に基づく(この1パターンのみ実データで確認済み。優先株等
"0"以外の末尾桁を持つケースはこのセッションでは未確認)。

Raw Snapshot(`RawSnapshotStore`)にはProviderの値("72030")をそのまま保存する
(このモジュールの正規化は一切適用しない、加工しない)。この正規化は`convert.py`が
Raw Payloadを`RawOHLCVBar`等のInternal Schemaへ変換する際にのみ適用し、
変換後のSchemaは`code`(内部Code)と`provider_code`(Providerの生の値)を両方
保持することで、両者を混同しないようにする。
"""

from __future__ import annotations

from collections.abc import Sequence

_COMMON_STOCK_SUFFIX = "0"
_PROVIDER_CODE_LENGTH = 5
_INTERNAL_CODE_LENGTH = 4


class TickerCodeNormalizationError(Exception):
    """Provider CodeからInternal Codeを安全に導出できない場合に送出する。"""


def normalize_provider_code_to_internal(provider_code: str) -> str:
    """Provider Codeから普通株のInternal Code(4桁)を安全に導出する。

    確認済みパターン(DECISIONS.md D0036)にのみ対応する。無条件に文字列の末尾を
    削る実装はしない。
    - 5桁の数字文字列で末尾が"0"(普通株、実データで確認済み) -> 先頭4桁を返す。
    - 4桁の数字文字列(Endpointによっては4桁のまま返る可能性への保守的な
      フォールバック、Provider Codeがそのまま内部Codeと一致するケース) -> そのまま返す。
    - 数字のみで構成されているが上記に当てはまらない場合(5桁だが末尾が"0"でない=
      優先株等の可能性、3桁・6桁等)は、実際のProvider Codeの可能性がある
      あいまいなケースとして推測せず`TickerCodeNormalizationError`を送出する。
    - 数字以外の文字を含む場合(fixture/testの合成ラベル、"TOPIX_SYNTH"等)は、
      実際のJ-Quants Provider Code(数字のみ)ではありえないことが構造的に明らかなため、
      そのまま変更せず返す(合成データの識別子はProvider Codeの正規化対象ではない)。
    """
    if not provider_code.isdigit():
        return provider_code
    if len(provider_code) == _PROVIDER_CODE_LENGTH and provider_code.endswith(_COMMON_STOCK_SUFFIX):
        return provider_code[:_INTERNAL_CODE_LENGTH]
    if len(provider_code) == _INTERNAL_CODE_LENGTH:
        return provider_code
    raise TickerCodeNormalizationError(
        f"Provider Code '{provider_code}' から普通株のInternal Codeを安全に導出できません"
        "(確認済みパターン: 5桁かつ末尾'0'、または4桁のみ。DECISIONS.md D0036参照)。"
    )


def build_provider_to_internal_code_index(provider_codes: Sequence[str]) -> dict[str, str]:
    """Master等から得たProvider Codeの集合から、provider_code -> internal_codeの
    対応表を構築する。同じinternal_codeへ複数のprovider_codeが正規化される場合
    (=正規化ルールが実データと整合していない可能性)は、黙って上書きせず
    `TickerCodeNormalizationError`を送出する。"""
    index: dict[str, str] = {}
    for provider_code in provider_codes:
        internal_code = normalize_provider_code_to_internal(provider_code)
        if internal_code in index and index[internal_code] != provider_code:
            raise TickerCodeNormalizationError(
                f"internal_code '{internal_code}' に複数のProvider Codeが対応しています "
                f"('{index[internal_code]}' と '{provider_code}')。正規化ルールが実データと"
                "整合していない可能性があります(DECISIONS.md D0036参照)。"
            )
        index[internal_code] = provider_code
    return index
