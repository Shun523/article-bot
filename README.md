# tech-articles-bot

Qiita の先週人気記事（ストック数トップ7）を毎日1本 Slack に投稿する Bot です。

## 仕組み

- 毎日 9:00 JST に GitHub Actions が自動実行
- 週の初回実行時に先週（月〜日）の Qiita 記事をストック数降順で取得し、上位7本をシャッフルして `weekly_queue.json` に保存
- 以降の6日間はキューから1本ずつ投稿（投稿済みフラグで管理）

## セットアップ

### 1. Slack Incoming Webhook URL を取得

1. https://api.slack.com/apps にアクセス
2. **Create New App** → **From scratch**
3. 左メニュー **Incoming Webhooks** → ON
4. **Add New Webhook to Workspace** → 投稿先チャンネルを選択
5. 表示された URL をコピー

### 2. GitHub Secrets に登録

リポジトリの **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| Name | Value |
|------|-------|
| `SLACK_WEBHOOK_URL` | 手順1でコピーした URL |

### 3. GitHub Actions を有効化

リポジトリの **Actions** タブを開き、ワークフローを有効にする。
初回は **Run workflow** ボタンで手動実行して動作確認できます。

## ローカルでのテスト

```bash
cp config.env.example config.env
# config.env を編集して SLACK_WEBHOOK_URL を設定
python article.py
```

## ファイル構成

```
article.py          # メインスクリプト
weekly_queue.json   # 今週の投稿キュー（自動更新）
config.env          # ローカル用シークレット（.gitignore 済み）
config.env.example  # config.env のテンプレート
.github/workflows/
  daily-post.yml    # GitHub Actions ワークフロー
```
