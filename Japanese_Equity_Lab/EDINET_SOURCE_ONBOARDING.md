# EDINET API V2 — Source Onboarding Report (Phase4B-2)

作成: `data-source-researcher` subagent(`source-onboarding` skill)、2026-08-17。
Main Claudeによる直接の追記なし(subagentの調査結果をそのまま保存)。

## 0. Environment / Access Finding(まず読むこと)

**本セッションから一次資料へのアクセスはブロックされた。** EDINET/FSA公式と思われる
URLすべてに`WebFetch`を試みたが、ネットワークegressプロキシにより
すべて`EGRESS_BLOCKED`で拒否された:

- `https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf`
  (「EDINET API仕様書(Version 2)2026年6月 金融庁企画市場局企業開示課」PDFと
  思われるもの — 現行の公式API仕様書らしきタイトルで検索結果に繰り返し出現)
- `https://disclosure2.edinet-fsa.go.jp/weee0010.aspx`
- `https://www.fsa.go.jp/search/20240401/1c_edinet.html`
- `https://disclosure.edinet-fsa.go.jp/api/v2/documents.json`

副次資料(セカンダリソース)へも範囲を広げたが、こちらもブロックされた:
`time2log.com`、`zenn.dev`(複数記事)、`lifetechia.com`、`note.com`、
`qiita.com`、`edinetdb.jp`、`data.e-gov.go.jp`、`en.wikipedia.org`、
`ja.wikipedia.org`、`web.archive.org`(archive経由も失敗)。到達できたのは
`github.com`と`pypi.org`のみで、いずれもFSA発行コンテンツではなくサードパーティ製
OSSラッパーのコードのみ。

`/root/.ccr/README.md`の方針により、403/407系のegress拒否は組織ポリシーであり
再試行や回避を行わないこと、と明記されているため、これ以上の回避は試みていない。

**結果として**: 公式EDINET API仕様書PDF・公式FSAページ・大半の副次ブログ記事のいずれも
本セッションから直接読むことができなかった。得られた情報は`WebSearch`が生成した
要約スニペットのみ(スニペット自体が副次的な日本語ブログの要約/引用であり、
そのページ自体を直接読んではいない)と、WebFetchで到達できた2件のGitHub上の
サードパーティ製ラッパーライブラリ(`matthelmer/edinet-tools`、
`chakki-works/edinet-python`のPyPIページ)のみ。

**このため、以下のほぼ全項目を一次資料未確認として扱う。** 検索スニペット由来の主張には
`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`のラベルを付す — これは通常の副次資料引用より
さらに一段低い確度である(ページ自体を読んでおらず、AIが生成した要約のみを見ている
ため)。タスク指示自体の原則("公式資料に到達できない場合はUNKNOWN/
REQUIRES_LOCAL_VALIDATIONとし、推測しない")に従い、いずれも"Confirmed"へは昇格させない。
Document Download APIの`type`パラメータのマッピングについては発見した2つの情報源が
**互いに矛盾**しており(§10参照)、これ自体がこの情報全体を実装の根拠にすべきでない
ことの証拠である。

**推奨**: 実際に`disclosure2dl.edinet-fsa.go.jp`と`api.edinet-fsa.go.jp`へ到達できる
環境(例: ユーザーのローカルPC)から、このチェックリストを再実行するか、少なくとも
スポットチェックすることが、アダプタ/Normalizerコードを書く前に必要。ローカル検証が
必要な項目はすべて`REQUIRES_LOCAL_VALIDATION`とラベルした。

---

## 1. Identity & Access

| 項目 | 内容 |
| --- | --- |
| Source識別名(公式名) | "EDINET"(Electronic Disclosure for Investors' NETwork)、金融庁(FSA)企画市場局企業開示課が運営。`SEARCH-SNIPPET-DERIVED`、未直接確認。 |
| Originating Source vs Delivery Provider | EDINET APIを直接呼ぶ場合は同一エンティティ: `originating_source="EDINET"`, `delivery_provider="EDINET"`。(将来、EDINET由来データがJ-Quants等の第三者経由で配信される場合は`delivery_provider≠"EDINET"`となる — D0042/D0043のOrigin/Delivery分離を踏襲。) |
| 公式ドキュメントURL | 検索結果に繰り返し出現: `https://disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/download/ESE140206.pdf`("EDINET API仕様書(Version 2)"、タイトルスニペットでは2026年6月付。2024年7月付の旧版も別途インデックスされており、FSAが定期的に改訂している可能性を示唆)。**このURL/版が実際に最新かつ正しいかは未確認。** `REQUIRES_LOCAL_VALIDATION`。 |
| APIバージョン | タイトルのみから"Version 2"(v2)と判断(本文未読)。EDINET v1は2024-03-29頃に廃止されたとの言及がFSAのX/Twitterアカウント投稿を参照するスニペットにあったが、`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、fsa.go.jp自体からではない。 |
| 認証方式 | 矛盾/未確認のシグナルあり: あるスニペットは`Subscription-Key`という**クエリパラメータ**(例: `...&Subscription-Key=<key>`)を挙げており、タスク側で仮定した`Ocp-Apim-Subscription-Key`**ヘッダ**とは異なる。EDINET API v2がAzure API Management上でホストされているとの情報も別途あり(その場合ヘッダ形式・クエリパラメータ形式の両方をサポートするのが一般的)、可能性としてはあり得るが、仕様書本文を読んで確認できていないため、正確なパラメータ名・大文字小文字・ヘッダ対応可否は未確認。`REQUIRES_LOCAL_VALIDATION`。 |
| 契約/プラン要件 | 検索スニペットはv2が「APIキーを要する」ことで一致しており、セルフサービスのアカウント作成経由で取得できるらしい("２章 APIの利用準備"という節タイトルがスニペットに出現、アカウント作成+キー発行の説明と思われる)。有料ティアの明示的な言及はなし。無条件で無料かどうかは`UNKNOWN`(未確認)。本Agentの制約上、実際にキー取得は試みていない。 |
| コスト | `SEARCH-SNIPPET-DERIVED (UNVERIFIED)`: 無料と思われる。実際に読んだ公式ページからの確認ではないため、正式な報告としては`UNKNOWN`とする。 |
| ライセンス/再配布制限 | `UNKNOWN`。FSAの利用規約ページやAPI仕様書の該当セクションのいずれにも到達できなかった。ブログタイトルの一つ("EDINET APIで株式投資① 規約を読んでみる")から専用の利用規約文書が存在することは示唆されるが、内容は未確認。**これは`RawSnapshotStore`へ生データをどの程度保持してよいかの判断をブロックする — 何かを保存する前に規約を実際に確認する必要がある。** `REQUIRES_LOCAL_VALIDATION`。 |

---

## 2. Coverage & Availability

| 項目 | 内容 |
| --- | --- |
| 過去データ範囲(Historical coverage) | `UNKNOWN`。2024年付の仕様書タイトルの文脈と思われるスニペットに「縦覧期間及び延長期間にある書類を取得対象とします」との言及があった — もし正確なら、Documents List APIの網羅範囲は「これまで提出された全て」ではなく、**法定の縦覧期間(公衆縦覧期間)+延長期間内にある書類**に限定される可能性を意味する。これは過去に公開されていた古い書類がAPI経由では取得できなくなっている可能性を示唆し、タスクで懸念されていた「APIの現在のカバレッジ ≠ 完全な法定提出履歴」のリスクそのものである。ただし主張元の本文を読めていないため`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`、未確認。`REQUIRES_LOCAL_VALIDATION`(例: `date=`を2010年など過去日付にして問い合わせ、結果が返るか/縦覧期間経過後に書類が消えるかをテストする)。 |
| 現在の可用性(継続更新中か) | 直接確認はしていないが、EDINETがFSAの継続稼働中の開示システムであることから妥当。読んだ資料からの確定事実としては`UNKNOWN`。 |
| 更新タイミング(イベント後どの程度でデータが現れるか) | `UNKNOWN` — 下記§4(タイムスタンプ意味論)そのものであり、未確認。 |
| レート制限(プラン全体) | 公式に文書化された数値のレート制限は見つからなかった。複数の独立した検索スニペットが「仕様書には明示的なリクエスト数/分の制限は記載されていない」という点で一致するが、実運用上はリクエスト間に約3〜5秒の間隔が必要、持続的な高負荷時にキーが一時停止される可能性(HTTP 429の言及が一件のスニペットにあり)という非公式/経験則的な情報のみ。これは公式なSLAとして扱ってはならない。`REQUIRES_LOCAL_VALIDATION`(スロットル値を決める前に確認する。ルートCLAUDE.mdルール5「外部APIのレート制限を守る」との関係で、EDINETには"守るべき"公式な数値が存在しない可能性があること自体を記録する必要があり、無制限だと勝手に仮定してはならない)。 |
| Endpoint別レート制限 | `UNKNOWN`、上記と同じ留保。 |
| ページネーション機構 | `UNKNOWN`。どのスニペットにも見つからなかった。Documents List APIが1回の呼び出しにつき`date`1つという設計であることから(§8参照)、伝統的なページネーションが存在せず1日分の全リストが1レスポンスで返る可能性はあるが、これは推測であり確認された事実ではない。確認済みであるかのようにコード化してはならない。`REQUIRES_LOCAL_VALIDATION`。 |
| 一括/ファイルダウンロードの可用性 | Document Download API(Documents List APIとは別)は`type`パラメータ経由で文書パッケージ(XBRL/PDF/CSV等)を書類ごとにダウンロードできるように見える — 一括アーカイブ/ダンプ機構ではなく書類単位のダウンロードらしいが、直接読んだ資料からの確認ではない。確定事実としては`UNKNOWN`。 |

---

## 3. Revision & Correction Semantics

| 項目 | 内容 |
| --- | --- |
| 訂正(Correction)の意味論 | タスクでは`parentDocID`フィールドの存在が仮定されていた。`parentDocID`らしき関係を示唆する言及は繰り返し見つかった(いずれも未直接確認)が、**`parentDocID`の存在が「この文書は親文書を訂正/置換する」ことを意味すると明言している資料は確認できなかった。** 本プロジェクト自身の`lib/disclosures/model.py`の`DocumentRelationshipKind`docstring(「推測で設定しない…関係の存在自体が未確認の場合はRelationship Recordを作らない」)に従い、これは`UNKNOWN`として扱うべきであり、`CORRECTS`と仮定してはならない。`REQUIRES_LOCAL_VALIDATION` — 実際のAPIキーで実際の訂正報告書を取得し、実際のフィールド名/値/意味論を仕様書本文と照合する。 |
| 公式に定義された訂正用フォームコード | `UNKNOWN`。「訂正」フォームコードが別途区分・列挙されているかは未確認(日本の開示実務では一般に訂正有価証券報告書等が区分されるのが通例だが、EDINET固有の公式リストとしては未確認)。 |
| 削除(Deletion)の意味論 | あるスニペットは`withdrawalStatus`フィールドについて「0が通常、それ以外の値は取下げを示す」とのみ記述していたが、これは`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`であり、実際の列挙値も、取下げ文書がAPIレスポンスから完全に除外されるのかフラグのみが立つのかも不明。両方とも成立し得る互いに排他的な設計であり、確認が必要。`REQUIRES_LOCAL_VALIDATION`。 |
| 改訂の意味論(親子関係 vs 独立系列) | `UNKNOWN` — 訂正の意味論と同様。本プロジェクト自身が`/v2/fins/summary`について採用した既定方針(D0043: 確認可能な親子関係が存在しない限り、改訂は独立した時系列として保持する)を、確認が取れるまではEDINETについても既定の安全側動作とすべき。 |

---

## 4. PIT Timestamp Semantics(タスク上、最重要項目)

| 項目 | 内容 |
| --- | --- |
| `submitDateTime` | 複数のスニペットに実在するフィールド名として出現(例値の形式: `"2019-11-01 09:00"`)。これが実際に何を計測しているか(FSAへの提出時刻か、公衆縦覧可能になった時刻か)は**未確認**。`UNKNOWN`。 |
| `opeDateTime` | あるスニペットはこのフィールド名の存在を認めており、「nullの場合もあれば日時値を含む場合もある」とのことだが、それが何の操作(編集?取下げ?再処理?)を表すかの**定義は見つからなかった**。`UNKNOWN`。 |
| 「FSAへ提出」と「公衆に公開」の区別 | `UNKNOWN`。読める資料には見つからなかった。これはまさに`lib/disclosures/model.py`の`DisclosureDocument.market_public_at`と`provider_available_at`が意図的に分離している曖昧性そのものであり、その設計自体の既存の文書化された方針(「`provider_available_at`は実際の観測ログが無い限り`availability_basis=UNKNOWN`のまま保持し、`market_public_at`へFallbackしない」)に従い、**`submitDateTime`・`opeDateTime`のいずれも、仕様書本文または実際のレスポンスに基づく意味論の確認が取れるまでは、`market_public_at`・`provider_available_at`のいずれへも`AvailabilityBasis.UNKNOWN`以外の根拠でマッピングしてはならない。** |
| タイムゾーン | 未確認。日本の政府システムであることからJSTは妥当な仮定だが、本Agent自身の制約(「推測しない」)に従い、`UNKNOWN(JSTと仮定、要確認)`と明記する必要があり、実装がtz-naiveな値を無言でJSTとして扱ってはならない — `DisclosureDocument.__post_init__`は既にtz-aware datetimeを要求しているため、これは明示的・根拠づけられた決定が必要であり、デフォルト値で済ませてはならない。`REQUIRES_LOCAL_VALIDATION`。 |

---

## 5. Identity Mapping

| 項目 | 内容 |
| --- | --- |
| EDINETコード形式 | あるスニペット(FSA自身のEDINETコードリスト文書を引用しているように読めるが、直接は未読)は: 6文字、"E"+5桁の数字、順次採番、現在有効な開示書類を持つ提出者に対して公開、としている。`SEARCH-SNIPPET-DERIVED (UNVERIFIED)` — 一般に知られているEDINETコードの形状(例: `E02166`)と整合的で妥当だが、実際に読んだ資料からの確認ではない。 |
| `secCode`形式 | `UNKNOWN`。4桁か5桁ゼロパディングか、あるいはJ-Quantsの5桁ゼロパディング規約(D0039)と一致するかは未確認。これはEDINETの`secCode`をJ-Quantsと同じ方法で`EntityRegistry`へ結合できるか、それとも独自の正規化ステップが必要かに直結する — **確認なしに一致すると仮定してはならない。** `REQUIRES_LOCAL_VALIDATION`。 |
| JCN(法人番号)形式 | 構造的には`UNKNOWN`(13桁は日本の法人番号の一般的な標準だが、EDINETが実際にこれを提供しているか、どの程度の信頼性で提供しているかは未確認)。GitHub上のラッパーライブラリ(`edinet-tools`)は「法人番号を含む複数の識別子で11,000以上のエンティティ」を解決すると謳っており、少なくとも時折はフィールドが埋まっていることを示唆するが、信頼性・網羅性は未確認。`UNKNOWN`。 |
| Entity Registry マッピング方針 | `lib/sources/entity_registry.py`の既存設計により、EDINETコード/secCode/JCNはそれぞれ`provider_identifiers["edinet"]`名前空間(または同等)のエントリとして`issuer_id`経由で解決されるべきで、J-Quantsコードへ直接結合してはならない。ここで新規の設計は不要 — 既存の`EntityIdentifierMapping`/`EntityRegistry.resolve(as_of=...)`構造がこれをそのままサポートする。不足しているのは、それを正しく埋めるための確認済みEDINET側識別子形式/意味論であり、上記の通り`UNKNOWN`。 |

---

## 6. Submitter vs Subject(大量保有報告書等)

`issuerEdinetCode` / `subjectEdinetCode`は、検索スニペットの中でそれらしいフィールド名として
言及されており、`issuerEdinetCode`は「大量保有の対象となる発行会社のEDINETコード」、
`subjectEdinetCode`は「公開買付けにおける対象会社のEDINETコード」と説明されていた。
これは妥当(大量保有・公開買付けの開示は発行体/提出者の区別を必要とする)だが、
**`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`のみ** — 仕様書本文のフィールド別表を読んでおらず、
正確なフィールド名、どの文書種別で埋まるか、タスクで仮定されていた提出者を表す
`edinetCode`/`filerName`の組が別途存在するかは確認できていない。`REQUIRES_LOCAL_VALIDATION`
— 実際のAPIキーで実際の大量保有報告書を取得し、実フィールドを確認する。

---

## 7. Document Download API `type`パラメータ

**矛盾する情報を発見 — ローカル検証なしにどちらも信用しないこと。** タスクで仮定された
マッピング(1=XBRL, 2=PDF, 3=添付書類, 4=英文書類, 5=CSV)は確認できなかった。
代わりに見つかったのは:

- ある検索スニペットの要約(出典不明の副次資料、仕様書のパラフレーズの可能性あり)は
  「`type=1` = 提出本文書及び監査報告書」、別途「`type=5`」をXBRL由来のCSV
  (UTF-16、タブ区切り)と説明していた。
- GitHub上のサードパーティラッパー(`matthelmer/edinet-tools`)は**まったく異なる方式**を
  使用: `type=0`(既定)→XBRL CSV、`type=1`→HTML、`type=2`→PDF。

これら2つは互いに矛盾しており(同じ数字が異なる形式にマッピングされている)、
**少なくともどちらか一方が誤っているか、別のエンドポイントを説明しているか、
ラッパーライブラリが公式`type`値をそのまま渡さず独自に内部変換している**強い証拠である。
どちらが正しいかを推測で解決することはしない — `UNKNOWN`、`REQUIRES_LOCAL_VALIDATION`
(実際の仕様書PDF及び/または実際のダウンロード呼び出しでの確認が必要)。

---

## 8. Documents List API クエリの意味論(項目2)

検索スニペットは(同じ「未直接確認」の留保付きで)以下の点で一致:

- エンドポイント形式: `GET https://api.edinet-fsa.go.jp/api/v2/documents.json?date=YYYY-MM-DD&type=2&Subscription-Key=<key>` — すなわち**日付ベース、1回の呼び出しにつき1日**であり、日付範囲や会社コードによるクエリではない。
- `type=1` vs `type=2`: あるスニペットは`type=1`はその日の書類の**件数のみ**を返す(メタデータのみ、リストなし)、`type=2`は実際の書類リスト+メタデータを返す、としている — これはタスク自身のフレーミング(「メタデータのみ vs メタデータ+リスト」)とおおむね整合的だが、繰り返しになるが`SEARCH-SNIPPET-DERIVED (UNVERIFIED)`。
- Documents List エンドポイントに会社コードベース・日付範囲ベースのクエリモードが存在するという証拠は見つからなかった。もし本当にないなら、複数日の取得には1日分ずつ`date=`を指定して繰り返し呼び出す必要がある。未確認。`REQUIRES_LOCAL_VALIDATION`。

---

## 9. Documents List のレスポンススキーマ(項目3)

タスクで列挙されたフィールドリスト(`docID`, `edinetCode`, `secCode`, `JCN`, `filerName`,
`fundCode`, `ordinanceCode`, `formCode`, `docTypeCode`, `periodStart`, `periodEnd`,
`submitDateTime`, `docDescription`, `issuerEdinetCode`, `subjectEdinetCode`,
`subsidiaryEdinetCode`, `currentReportReason`, `parentDocID`, `opeDateTime`,
`withdrawalStatus`, `docInfoEditStatus`, `disclosureStatus`, `xbrlFlag`, `pdfFlag`,
`attachDocFlag`, `englishDocFlag`, `csvFlag`, `legalStatus`)を一次資料と照合して
確認・否定することはできなかった。複数の異なる検索/スニペットにまたがって
何らかの独立した裏付けが見られたフィールド(それでも未確認): `docID`, `edinetCode`,
`secCode`, `JCN`, `filerName`, `docDescription`, `docTypeCode`, `submitDateTime`,
`parentDocID`, `opeDateTime`, `withdrawalStatus`, `docInfoEditStatus`, `disclosureStatus`,
`legalStatus`, `issuerEdinetCode`, `subjectEdinetCode`。以下については裏付けが
見つからなかった(存在しないという意味ではなく、確認できなかったという意味):
`fundCode`, `ordinanceCode`, `formCode`, `periodStart`, `periodEnd`, `subsidiaryEdinetCode`,
`currentReportReason`, `xbrlFlag`, `pdfFlag`, `attachDocFlag`, `englishDocFlag`, `csvFlag`。
**これらのいずれも確認済みのWire Schemaとして扱ってはならない。** 宣言/観測されたスキーマ
全体を`UNKNOWN`、`REQUIRES_LOCAL_VALIDATION`とする — 実際の
`GET .../documents.json?date=...&type=2`レスポンスを実際の仕様書表と照合する必要がある。
これはPhase4Aが`/v2/fins/summary`について行った(D0043)のと全く同じ手順。

---

## 10. Form Code List(項目7)

「EDINET API関連資料」というタイトルのページ
(`disclosure2dl.edinet-fsa.go.jp/guide/static/disclosure/WZEK0110.html`)が検索結果に
繰り返し出現し、あるスニペットは仕様書PDFに「別紙1 様式コードリスト」「別紙2
提出書類一覧のデータ出力例」が付属していると説明していた。これは公式・安定した
様式コードリファレンスが存在し、仕様書とともに公開されていることと整合的だが、
いずれのURLも開いて内容や、具体的な種別(有価証券報告書, 訂正報告書, 大量保有報告書,
臨時報告書等)のカバレッジを確認することはできなかった。`REQUIRES_LOCAL_VALIDATION`。

---

## 11. Storage

| 項目 | 内容 |
| --- | --- |
| 生データ保存ポリシーへの影響 | `UNKNOWN` — §1のライセンス/利用規約の欠落によりブロックされている。本プロジェクトの既定の安全側方針(`UNKNOWN_RESTRICTIONS`→制限)に従い、実際に利用規約を読んで確認するまでは、EDINETの生ペイロードを長期間自由に保持できると仮定すべきでない。 |
| ファイル/PDF/XBRLの可用性 | 妥当(EDINETは本質的にXBRL/PDF提出書類のリポジトリ)だが、正確なダウンロード種別の意味論は未確認(§7参照)。 |
| チェックサム/ハッシュの可用性 | `UNKNOWN`。本Labの`RawSnapshotStore`独自のハッシュとは別に、APIがダウンロード成果物のコンテンツハッシュ/チェックサムを提供しているという言及は見つからなかった。 |

---

## 12. Known Limitations(明示、隠さない)

1. **本セッションでは一次資料を一件も直接読むことができなかった** — FSA/EDINET公式の
   URLほぼすべて、および大半の副次URLがネットワークegressポリシーによりブロックされた。
   本報告書はほぼ全面的に`WebSearch`のスニペット合成に基づいており、通常の副次/ブログ
   引用よりさらに一段低い確度である。
2. 認証パラメータ名/大文字小文字(`Subscription-Key`クエリパラメータ vs
   `Ocp-Apim-Subscription-Key`ヘッダ) — 未確認。
3. `submitDateTime`/`opeDateTime`の正確な意味とタイムゾーン — 未確認。これにより
   `DisclosureDocument.market_public_at`/`provider_available_at`への確信を持った
   マッピングがブロックされる。両方とも解決するまで`AvailabilityBasis.UNKNOWN`のまま
   とすること。
4. `parentDocID`の訂正/関係の意味論 — 未確認。`DocumentRelationshipKind.CORRECTS`へ
   自動マッピングしてはならない。
5. `withdrawalStatus`/`docInfoEditStatus`/`disclosureStatus`の列挙値・正確な意味 — 未確認。
6. Document Downloadの`type`パラメータ値 — 2つの副次資料の間で**実際に矛盾する**情報が
   見つかった。未解決として扱い、「おそらく正しい」と扱わない。
7. `secCode`形式とJ-Quantsの5桁ゼロパディング規約(D0039)との関係 — 未確認。互換性を
   仮定しない。
8. Documents Listレスポンスの全フィールドリスト — 一次資料での確認なし。タスク側の
   提案フィールドリストは全体として検証も反証もされていない。
9. レート制限 — 公式に文書化された数値は見つからず、未読の副次資料由来の非公式/経験則的な
   間隔情報のみ。
10. 過去データ範囲/保持ポリシー — APIのカバレッジが「縦覧期間+延長期間」に限定されている
    可能性を示唆するシグナルがあるが未確認。もし本当なら、Backfillの網羅性に実務上の
    影響がある。
11. `RawSnapshotStore`へ取得ペイロードを保存する際のライセンス/再配布条件 — 未確認。
12. Documents List APIのページネーション機構 — 未確認。
13. 無料APIキーが無条件に利用可能かどうか、実際の取得プロセス/プランティア — 未確認
    (本Agent自身の制約により、実際のキー取得は試みていない)。

---

## 13. `lib/disclosures/model.py`へのマッピング(状態: すべて保留)

上記を踏まえ、現時点では`DisclosureDocument`/`DisclosureAttachment`のいかなるフィールドも、
仮定したEDINETフィールドマッピングから値を埋めるべきではない:

- `market_public_at` / `market_public_at_basis` → 確認済みの`submitDateTime`/`opeDateTime`
  意味論が得られるまで`UNKNOWN`。
- `provider_available_at` / `provider_available_at_basis` → `UNKNOWN`
  (モデル自身の既定方針 — `market_public_at`へFallbackしない、と整合)。
- `document_kind`(`DocumentKind` enum) → 公式の様式コードリストを実際に読み、明示的な
  Mapping Tableを構築するまで`formCode`/`docTypeCode`から埋めることはできない
  (本プロジェクトの規約: 「Provider固有Codeからのmappingは明示的Mapping Tableのみで行い、
  substring heuristicは使わない」— 未マッピングのコードは`UNKNOWN`へfail-closedする)。
- `DocumentRelationship`(`DocumentRelationshipKind`) → `parentDocID`の意味論が確認される
  まで、いかなるRelationship Recordも作らない — モデル自身のdocstring通り
  「関係の存在自体が未確認の場合、このRecordを作らない」。
- `entity_id` → EDINETコード/`secCode`/JCNの形式が確認され、`provider_identifiers["edinet"]`
  マッピングとして実際の`valid_from`/`valid_until`とともに登録されるまで、
  `EntityRegistry`経由で解決できない。
- Document Download API向けの`AttachmentKind`/`AttachmentAvailability` → §7の未解決な
  `type`パラメータの矛盾によりブロックされている。

---

## Bottom line

現時点の情報は、EDINETアダプタ/Normalizerを書く根拠として使用すべきではない。
最優先の次のステップは、**実際に`disclosure2dl.edinet-fsa.go.jp`と
`api.edinet-fsa.go.jp`へ到達できる環境(例: ユーザー自身のマシン)からのローカル検証**
である: 実際の仕様書PDFを開き、キーを登録し、実際のDocuments List呼び出しを1件、
実際のDocument Download呼び出しを1件行い、**観測された**Wire Schemaを仕様書の主張と
突き合わせる — これはPhase4Aが J-Quants `/v2/fins/summary` に対して行った(D0043)のと
全く同じ「宣言 vs 観測、両方を保持する」規律。それまでは、上記すべての項目は
Source Catalog/`DATA_SOURCE_ARCHITECTURE.md`のEDINET行において`UNKNOWN`または
`REQUIRES_LOCAL_VALIDATION`のままとし、EDINETの`DatasetDescriptor.implementation_status`は
`NOT_IMPLEMENTED`のままとする。

**このAgentがコンテキストとして読んだ既存リポジトリファイル(編集なし):**
- `/home/user/shoui-/Japanese_Equity_Lab/DATA_SOURCE_ARCHITECTURE.md`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/sources/catalog.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/sources/entity_registry.py`
- `/home/user/shoui-/Japanese_Equity_Lab/lib/disclosures/model.py`
