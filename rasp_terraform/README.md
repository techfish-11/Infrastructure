# Raspberry Pi 上の Grafana と ntopng 用の Terraform セットアップ

この Terraform 設定は、Docker を使用して Raspberry Pi 上に Grafana と ntopng のコンテナをデプロイします。
私の環境ではGrafanaを使用してシステムの監視を行い、ntopngを使用してネットワークトラフィックの分析を行っています。

## 前提条件

- Raspberry Pi に Docker がインストールされている
- Raspberry Pi に Terraform がインストールされている
- Docker ソケットがアクセス可能 (`/var/run/docker.sock`)

## 使用方法

1. このリポジトリを Raspberry Pi にクローンします。
2. `rasp_terraform` ディレクトリに移動します。
3. Terraform を初期化します：
   ```
   terraform init
   ```
4. プランを確認します：
   ```
   terraform plan
   ```
5. 設定を適用します：
   ```
   terraform apply
   ```

## アクセス

- Grafana: http://localhost:3000 (デフォルト admin/admin)
- ntopng: http://localhost:3001
- Redis: localhost:6379

## 変数

- `grafana_admin_password`: Grafana の管理者パスワード (デフォルト: "admin")
- `ntopng_license`: ntopng のライセンスキー (オプション)

## 注意事項

- ntopng はネットワーク監視のためにホストネットワークモードを使用します。
- データはホストの `/var/lib/grafana` と `/var/lib/ntopng` に永続化されます。
