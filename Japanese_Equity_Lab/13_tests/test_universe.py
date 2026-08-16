from __future__ import annotations

from datetime import UTC, date, datetime

from lib.universe import ListingBasedUniverseProvider, ListingRecord, UniverseResolution


def test_empty_listings_is_data_unavailable_not_empty_universe() -> None:
    """listing dataが無い場合、「投資可能銘柄が0件」という架空の結論を出さない。"""
    provider = ListingBasedUniverseProvider([])
    snapshot = provider.as_of(datetime(2026, 1, 10, tzinfo=UTC))
    assert snapshot.resolution == UniverseResolution.DATA_UNAVAILABLE
    assert snapshot.codes == ()


def test_resolved_excludes_delisted_and_not_yet_listed_stocks() -> None:
    listings = [
        ListingRecord(code="7203", market="Prime", listing_date=date(1949, 5, 16)),
        ListingRecord(code="9999", market="Prime", listing_date=date(2026, 6, 1)),  # まだ上場していない
        ListingRecord(code="8888", market="Prime", listing_date=date(2000, 1, 1), delisting_date=date(2025, 12, 1)),  # 廃止済み
    ]
    provider = ListingBasedUniverseProvider(listings)
    snapshot = provider.as_of(datetime(2026, 1, 10, tzinfo=UTC))

    assert snapshot.resolution == UniverseResolution.RESOLVED
    assert snapshot.codes == ("7203",)


def test_resolved_respects_tradable_window() -> None:
    listings = [
        ListingRecord(
            code="1234",
            market="Prime",
            listing_date=date(2000, 1, 1),
            tradable_from=date(2026, 1, 1),
            tradable_until=date(2026, 1, 31),
        ),
    ]
    provider = ListingBasedUniverseProvider(listings)

    inside = provider.as_of(datetime(2026, 1, 15, tzinfo=UTC))
    after = provider.as_of(datetime(2026, 2, 1, tzinfo=UTC))

    assert inside.codes == ("1234",)
    assert after.codes == ()


def test_survivorship_bias_auto_detected_when_no_delisting_dates_present() -> None:
    """全listingにdelisting_dateが無い場合(=現在の上場銘柄しか分からない場合)、
    明示的に指定しなくてもsurvivorship_bias_unresolvedが自動的にTrueになる。"""
    listings = [ListingRecord(code="7203", market="Prime", listing_date=date(1949, 5, 16))]
    provider = ListingBasedUniverseProvider(listings)
    snapshot = provider.as_of(datetime(2020, 1, 10, tzinfo=UTC))
    assert snapshot.survivorship_bias_unresolved is True
    assert "廃止銘柄を捕捉できていない可能性がある" in snapshot.note


def test_survivorship_bias_not_flagged_when_delisting_dates_are_present() -> None:
    """1件でもdelisting_dateがあれば、少なくとも部分的に廃止銘柄を扱えているとみなす。"""
    listings = [
        ListingRecord(code="7203", market="Prime", listing_date=date(1949, 5, 16)),
        ListingRecord(code="8888", market="Prime", listing_date=date(2000, 1, 1), delisting_date=date(2025, 12, 1)),
    ]
    provider = ListingBasedUniverseProvider(listings)
    snapshot = provider.as_of(datetime(2020, 1, 10, tzinfo=UTC))
    assert snapshot.survivorship_bias_unresolved is False
    assert snapshot.note == ""


def test_survivorship_bias_can_be_forced_true_explicitly() -> None:
    listings = [
        ListingRecord(code="7203", market="Prime", listing_date=date(1949, 5, 16), delisting_date=date(2099, 1, 1)),
    ]
    provider = ListingBasedUniverseProvider(listings, survivorship_bias_unresolved=True)
    snapshot = provider.as_of(datetime(2020, 1, 10, tzinfo=UTC))
    assert snapshot.survivorship_bias_unresolved is True
