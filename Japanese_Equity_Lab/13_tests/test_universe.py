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
