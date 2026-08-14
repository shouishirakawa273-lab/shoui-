# 株式スクリーニング・比較ツール

日本株(証券コード)・米国株(ティッカー)を横断的に検索・比較・スクリーニングできる、個人利用向けのローカルツールです。

> ⚠️ **投資助言ではありません。** 表示されるデータは参考情報であり、正確性・最新性は保証されません。投資判断は自己責任で行ってください。

## できること

- 銘柄コード/ティッカーを入力して、株価・PER・PBR・ROE・配当利回り・時価総額・52週高安・セクター・直近業績を表示
- 3〜5銘柄の指標を横並び比較(表 + レーダーチャート)
- ウォッチリスト(JSON)に対するしきい値スクリーニング(PER/PBR/配当利回り/時価総額)
- 業績予想(会社予想 / アナリスト予想)を実績値と明確に区別して表示(出典・更新日付き)

## 既知の制約

- **J-Quants(日本株の業績予想)**: 無料プランはデータに約12週間の遅延があり、レート制限は5リクエスト/分です。
- **Finnhub(米国株の業績予想)**: 無料枠は米国市場中心で、60コール/分の制限があります。国際銘柄の詳細データは有料プランが必要な場合があります。
- **フィールド名は要検証**: `core/providers/jquants.py` `core/providers/finnhub.py` 内の実レスポンスのフィールド名(`ForecastNetSales`等)は公式ドキュメントに基づく実装時点の想定です。**このツールを開発したセッションはクラウドの隔離環境で動作しており、外部APIへの疎通が一切できない状態でした。** そのため、実際のレスポンス形式は未検証です。初回セットアップ時に必ず下記の疎通確認を行ってください。
- 業績予想データが取得できない場合は数値を推測せず「取得不可」と表示します。

## セットアップ

### 1. 依存パッケージのインストール

```bash
python3 -m venv .venv
source .venv/bin/activate  # Windowsは .venv\Scripts\activate
pip install -r requirements.txt
```

### 2. APIキーの取得(業績予想機能を使う場合)

`.env.example` を `.env` にコピーし、以下の手順で取得したキーを設定してください。

#### J-Quants(日本株)

1. https://jpx-jquants.com/ でアカウントを作成(無料プランあり)
2. マイページからメールアドレス・パスワードでリフレッシュトークンを取得
   (`POST /token/auth_user` → `POST /token/auth_refresh` の手順は公式ドキュメント参照)
3. `.env` の `JQUANTS_REFRESH_TOKEN` に設定

#### Finnhub(米国株)

1. https://finnhub.io/ でアカウントを作成(無料枠あり)
2. ダッシュボードでAPIキーを取得
3. `.env` の `FINNHUB_API_KEY` に設定

### 3. 疎通確認(初回セットアップ時は必須)

APIキー設定後、必ず以下を実行して実際にレスポンスが返ってくることを確認してください。
フィールド名が想定と異なる場合、`core/providers/jquants.py` / `core/providers/finnhub.py` の
`_STATEMENT_FIELD_MAP` 等を実際のレスポンスに合わせて修正する必要があります。

```bash
python scripts/check_provider.py market 7203 AAPL
python scripts/check_provider.py forecast 7203 AAPL
```

### 4. アプリの起動

```bash
streamlit run app.py
```

ブラウザで http://localhost:8501 が開きます。

## テストの実行

```bash
pytest
```

外部API通信はすべてモック化されているため、ネットワーク接続なしで実行できます。

## ウォッチリストの追加

`watchlists/*.json` に以下の形式でファイルを追加してください。

```json
{
  "name": "my_watchlist",
  "codes": ["7203", "6758", "AAPL", "MSFT"]
}
```

## ディレクトリ構成

```
core/                 データ取得・キャッシュ・スクリーニング等のロジック(UI非依存、テスト対象)
  models.py            ドメインモデル
  errors.py            共通例外
  cache.py             SQLiteキャッシュ
  validation.py        異常値検証
  screening.py          スクリーニング
  comparison.py         比較用テーブル・正規化
  watchlist.py          ウォッチリストのJSON管理
  lookup.py             キャッシュ+取得+検証を束ねる高レベルAPI
  forecast.py           市場別に予想プロバイダを選択するファサード
  providers/
    market_data.py       yfinanceベースの実績データ取得
    jquants.py            J-Quants業績予想クライアント
    finnhub.py            Finnhub業績予想クライアント
app.py                 Streamlitエントリポイント
scripts/check_provider.py  ローカルでの疎通確認スクリプト
tests/                 ユニットテスト(pytest)
watchlists/            ウォッチリストJSON
data/                  SQLiteキャッシュの保存先(gitignore対象)
```

## 半自律運用(メンテナンスの自動化)

このプロジェクトの品質ゲート・定期健康診断・異常検知時の自動PR運用については
[CLAUDE.md](./CLAUDE.md) と [CONTRIBUTING.md](./CONTRIBUTING.md) を参照してください。
