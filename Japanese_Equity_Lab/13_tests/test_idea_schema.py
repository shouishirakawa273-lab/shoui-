from __future__ import annotations

from datetime import UTC, datetime

from lib.schemas.idea import Idea, IdeaSourceType, IdeaStatus, SourceReliability


def test_idea_defaults_and_immutability() -> None:
    idea = Idea(
        idea_id="I0001",
        discovered_at=datetime(2026, 8, 16, tzinfo=UTC),
        source_type=IdeaSourceType.YOUTUBE,
        source_url="https://example.com/watch?v=xxxxx",
        source_author="channel_name",
        published_at=datetime(2026, 8, 10, tzinfo=UTC),
        original_claim="この銘柄は受注が伸びている",
        ai_summary="動画では受注残の増加を根拠に強気の見通しが語られている",
    )
    assert idea.status == IdeaStatus.NEW
    assert idea.source_reliability == SourceReliability.UNKNOWN
    assert idea.required_data == ()
    assert idea.schema_version == "1.0"
