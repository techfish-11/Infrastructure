# Suricata Dashboard

このダッシュボードは CLI (ターミナル) 上で Suricata のイベントをライブ表示するツールです。
Forwarder サービスから POST されたイベントを受信し、上位IPやアラートを集計し、ダッシュボードをターミナルに表示します。

使い方:
1. 依存関係インストール
```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```
2. `.env` を作成（`.env.example` を参照）
3. サーバーを起動
```bash
python cli.py
```

設定:
- `LISTEN_HOST` / `LISTEN_PORT`: ダッシュボードの受信bindアドレス/ポート
- `DASH_AUTH_TYPE`: none/basic/bearer
- `DASH_AUTH_USERNAME`, `DASH_AUTH_PASSWORD`, `DASH_AUTH_BEARER_TOKEN` : 認証設定

連携例 (Forwarder 側):
- 単体コンテナでの連携:  `TARGET_URL` を `http://host.docker.internal:9000/ingest` に設定
- Docker Compose 統合: `docker-compose.integration.yml` を使うと、自動的に両方のサービスが同一ネットワークに配置され、Forwarder 側の `TARGET_URL` を `http://suricata-dashboard:9000/ingest` に設定して連携できます。

例: `suricata/.env` の `TARGET_URL` の設定
```
TARGET_URL=http://suricata-dashboard:9000/ingest
```
