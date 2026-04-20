"""
Qiita 先週の人気記事（ストック順トップ7）を毎日1本 Slack に投稿するスクリプト

実行モデル:
  - weekly_queue.json が空 or 先週分でなければ先週トップ7を取得してシャッフル保存
  - キューから未投稿の先頭1本を取り出して Slack 投稿し、投稿済みフラグを保存
"""

import json
import os
import random
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

JST = timezone(timedelta(hours=9))

QUEUE_PATH = os.path.join(os.path.dirname(__file__), "weekly_queue.json")


# =========================================================
# 日付ユーティリティ
# =========================================================

def get_last_week_range() -> tuple[str, str]:
    """先週月曜〜日曜の日付を (YYYY-MM-DD, YYYY-MM-DD) で返す"""
    today = datetime.now(JST).date()
    last_monday = today - timedelta(days=today.weekday() + 7)
    last_sunday = last_monday + timedelta(days=6)
    return last_monday.isoformat(), last_sunday.isoformat()


def get_week_id() -> str:
    """先週の ISO 週 ID を返す (例: '2026-W15')"""
    start, _ = get_last_week_range()
    return date.fromisoformat(start).strftime("%G-W%V")


# =========================================================
# キュー管理
# =========================================================

def load_queue() -> dict:
    if os.path.exists(QUEUE_PATH):
        with open(QUEUE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_queue(data: dict):
    with open(QUEUE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# =========================================================
# Qiita API
# =========================================================

def fetch_json(url: str) -> object:
    req = urllib.request.Request(url)
    req.add_header("User-Agent", "tech-articles-bot/1.0")
    with urllib.request.urlopen(req, timeout=10) as res:
        return json.loads(res.read().decode("utf-8"))


def fetch_last_week_top7() -> list[dict]:
    """先週投稿された Qiita 記事をストック数降順で取得し、上位7本をシャッフルして返す"""
    start, end = get_last_week_range()
    query = f"created:>={start} created:<={end}"
    pool = []

    for page in range(1, 11):
        url = (
            "https://qiita.com/api/v2/items"
            f"?per_page=100&page={page}"
            f"&query={urllib.parse.quote(query)}"
        )
        data = fetch_json(url)
        if not data:
            break
        pool.extend(data)
        if len(data) < 100:
            break

    pool.sort(key=lambda x: x.get("stocks_count", 0), reverse=True)

    top7 = [
        {
            "title": item.get("title", ""),
            "url": item.get("url", ""),
            "stocks": item.get("stocks_count", 0),
            "tags": [t["name"] for t in item.get("tags", [])],
            "posted": False,
        }
        for item in pool[:7]
    ]
    random.shuffle(top7)
    return top7


def ensure_queue() -> dict:
    """キューが先週分でなければ更新して返す"""
    week_id = get_week_id()
    data = load_queue()
    if data.get("week") != week_id or not data.get("articles"):
        print(f"先週分（{week_id}）の記事を取得中...")
        articles = fetch_last_week_top7()
        print(f"  {len(articles)} 本取得・シャッフル済み")
        data = {"week": week_id, "articles": articles}
        save_queue(data)
    return data


# =========================================================
# Slack 投稿
# =========================================================

def post_to_slack(article: dict, webhook_url: str, position: int, total: int) -> bool:
    start, end = get_last_week_range()
    tags = "  ".join(f"`{t}`" for t in article["tags"][:3]) if article["tags"] else ""
    text = (
        f"*📰 先週（{start} 〜 {end}）の人気記事*\n"
        f"<{article['url']}|{article['title']}>\n"
    )
    if tags:
        text += f"   {tags}"

    blocks = [
        {"type": "section", "text": {"type": "mrkdwn", "text": text}},
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": f"🤖 tech-articles-bot | Qiita ({position}/{total})"}
            ],
        },
    ]
    payload = json.dumps({"blocks": blocks}).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=10) as res:
        return res.read().decode() == "ok"


# =========================================================
# 設定読み込み
# =========================================================

def load_webhook_url() -> str:
    """環境変数 → config.env の順で SLACK_WEBHOOK_URL を読み込む"""
    url = os.environ.get("SLACK_WEBHOOK_URL", "")
    if url:
        return url
    config_path = os.path.join(os.path.dirname(__file__), "config.env")
    if os.path.exists(config_path):
        with open(config_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    if k.strip() == "SLACK_WEBHOOK_URL":
                        return v.strip()
    return ""


# =========================================================
# メイン
# =========================================================

def main():
    webhook_url = load_webhook_url()
    if not webhook_url:
        print("⚠️  SLACK_WEBHOOK_URL が未設定です。config.env を確認してください。")
        return

    data = ensure_queue()
    articles = data["articles"]
    unposted = [a for a in articles if not a.get("posted")]

    if not unposted:
        print("今週の記事はすべて投稿済みです。")
        return

    article = unposted[0]
    total = len(articles)
    position = total - len(unposted) + 1

    print(f"\n投稿: [{position}/{total}] {article['title']}")
    print(f"  🔖 {article['stocks']}  🔗 {article['url']}")

    try:
        if post_to_slack(article, webhook_url, position, total):
            article["posted"] = True
            save_queue(data)
            print("✅ Slack 投稿完了")
        else:
            print("⚠️  Slack 応答が 'ok' 以外でした")
    except Exception as e:
        print(f"❌ 投稿エラー: {e}")


if __name__ == "__main__":
    main()
