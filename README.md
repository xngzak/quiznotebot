# Notion → X(Twitter) 自動投稿ボット

Notion の DB からランダムに 1 つのレコードを取得して X に投稿するスクリプトです。

[クイズ勉強用 bot](https://x.com/quiznotebot)で運用中です。

## セットアップ

### 1. 必要なライブラリをインストール

```bash
# sudo apt-get update
# sudo apt install python3-pip
pip install python-dotenv notion-client requests
```

PATH の warning が出た場合：

```bash
# ~/.bashrcにローカルbinディレクトリを追加
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc

# PATHが正しく設定されているか確認
echo $PATH | grep -o "$HOME/.local/bin"
```

2. 環境変数ファイルを作成

### 2. 環境変数ファイルを作成

```bash
cp .env.example .env
nano .env
```

`.env`ファイルを更新する

### 3. Notion 設定

1. [Notion Developers](https://www.notion.so/my-integrations)で Integration を作成
2. Integration Token をコピー
3. 使用する Notion の DB ページで「...」→「Add connections」から Integration を招待
4. Database ID を Notion の DB の URL から取得（32 文字の部分）

### 4. X(Twitter) API 設定

1. [Twitter Developer Portal](https://developer.twitter.com/en/portal/dashboard)でプロジェクトを作成
2. アプリをプロジェクトに紐付け
3. Consumer Keys と Access Token を生成

## 実行

```bash
python3 postQuizNote.py
```

## 定期実行設定（crontab）

```bash
# crontabファイルを編集
crontab -e

# 定期実行スケジュールを追加(毎日9時〜23時まで1時間ごとに実行する場合)
0 9-23 * * * cd $HOME/quiznotebot && /usr/bin/python3 postQuizNote.py

# crontabの設定確認
bashcrontab -l
```

これは再起動後も実行されるため一時的にジョブを無効にするには、`crontab -e`で開いたエディタで該当の行の先頭に#を追加してコメントアウトする。
