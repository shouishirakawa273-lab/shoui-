# 99_archive/13_tests/fixtures/

Phase3A.1でJ-Quants API V1形状からV2形状へ全面移行した際、V1のField名
(`Code/Date/Open/High/Low/Close/Volume`、`HolidayDivision`)を前提としていた
fixtureファイルをここへ退避した(削除はしない、CLAUDE.md安全原則)。

- `synthetic_jquants_daily_quotes_v1_pre_jquants_v2_migration.json`: Phase2〜2.2で
  使用していたPipeline Validation Fixture(V1形状)。V2形状版は
  `13_tests/fixtures/synthetic_jquants_v2_bars.json`。
- `portfolio_scenario_v1_pre_jquants_v2_migration.json`: Phase2.2で追加した
  Portfolio Scenario Fixture(V1形状)。V2形状版は
  `13_tests/fixtures/portfolio_scenario_v2.json`。

いずれも価格・カレンダーの値そのものは変更せず、Field名とTop-levelキー名のみを
V2形状(`equity_bars`/`HolDiv`等)へ機械的に変換した(`AdjFactor=1.0`/`ExRT=null`を
全行に追加)。詳細はDECISIONS.md D0031参照。
