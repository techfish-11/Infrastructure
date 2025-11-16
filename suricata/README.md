# Suricata EVE Forwarder

このディレクトリは、Suricataの`eve.json`（JSON Lines）を解析して指定したHTTPエンドポイントへ配信するサーバーです。

特徴:
- `eve.json`ファイルをtailして、新しいイベントをバッチで転送します
- HTTP認証（Basic / Bearer）をサポート
- 環境変数で設定可能（`.env`）
- Dockerコンテナとして実行可能

使い方（ローカル）:

1. Python環境を作成、依存関係をインストール

```bash
python -m venv venv
venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

2. `.env` を作成（`.env.example`を参照）し、TARGET_URLなどの環境変数を設定

3. サーバーを起動

```bash
uvicorn app:app --host 0.0.0.0 --port 8000
```

Dockerで実行する:

```bash
docker build -t suricata-forwarder .
docker run --env-file .env -v /path/to/eve.json:/var/log/suricata/eve.json:ro -p 8000:8000 suricata-forwarder
```

Docker Compose例:

```bash
docker-compose up -d --build
```

APIエンドポイント:
- `GET /health` - ヘルスチェック
- `GET /stats` - イベント転送状況の統計（total_forwarded, bufferedなど）
- `POST /send_now` - 直近のイベント（最大BATCH_SIZE）を即時転送

環境変数は `EVE_FILE_PATH`, `TARGET_URL`, `HTTP_AUTH_TYPE`, `HTTP_AUTH_USERNAME`, `HTTP_AUTH_PASSWORD`, `HTTP_AUTH_BEARER_TOKEN`, `BATCH_SIZE`, `BATCH_INTERVAL`, `READ_INTERVAL` などを参照してください。
