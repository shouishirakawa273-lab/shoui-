# 03_idea_inbox/

投資アイデアの受信箱。`lib/schemas/idea.Idea` に対応する。

X投稿・YouTubeコメント等は「事実」や「買い推奨」として扱わない。
あくまでHypothesis Generator(仮説の材料)として扱う(RESEARCH_RULES.md参照)。

- `youtube/`: `YT_<video_id>/` 配下に `metadata.json` / `transcript.md` / `comments.parquet` /
  `comment_clusters.md` / `video_summary.md` / `investment_ideas.md` / `hypotheses.md` を置く
  (実装はPhase5、ディレクトリのみ現時点で用意)。
- `x/`: X投稿由来のアイデア。
- `papers/`: 論文由来のアイデア。
- `manual/`: 自分自身の疑問・気付き。

ファイル名は `I<連番>_<日付>_<内容>.md`(例: `I0001_2026-08-16_earnings_revision.md`)。
昇華(Hypothesis化)したら `status` を `PROMOTED_TO_HYPOTHESIS` にし、
`related_ideas` / `source_idea_id` で `04_hypotheses/` の該当ファイルと相互参照する。
