import os
import time
import requests

TOKEN = os.environ["DISCORD_TOKEN"]   # توكن حسابك (من متغيرات Railway)
GUILD_ID = os.environ["GUILD_ID"]     # ID السيرفر

API = "https://discord.com/api/v9"
HEADERS = {
    "Authorization": TOKEN,
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
}

CHANNEL_TYPES = {0, 2, 5, 13}      # نص، صوت، إعلانات، ستيج
DELETABLE_MSG_TYPES = {0, 19, 20}  # عادية، رد، أمر سلاش

total_deleted = 0


def request(method, url, **kwargs):
    """يعيد المحاولة تلقائياً عند الـ rate limit."""
    while True:
        try:
            r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
        except requests.RequestException as e:
            print("خطأ شبكة، إعادة محاولة:", e)
            time.sleep(5)
            continue
        if r.status_code == 429:
            wait = r.json().get("retry_after", 1) + 0.5
            print(f"Rate limit، انتظار {wait:.1f} ثانية...")
            time.sleep(wait)
            continue
        return r


def clean_channel(channel_id, name, my_id):
    global total_deleted
    before = None
    deleted_here = 0

    while True:
        params = {"limit": 100}
        if before:
            params["before"] = before
        r = request("GET", f"{API}/channels/{channel_id}/messages", params=params)

        if r.status_code in (403, 404):
            print(f"[{name}] ما في صلاحية، تخطي")
            return
        if r.status_code != 200:
            print(f"[{name}] خطأ {r.status_code}: {r.text[:100]}")
            return

        msgs = r.json()
        if not msgs:
            break
        before = msgs[-1]["id"]  # الترقيم بيعتمد على آخر رسالة بالدفعة، فالحذف ما بيأثر عليه

        for m in msgs:
            if m["author"]["id"] != my_id or m["type"] not in DELETABLE_MSG_TYPES:
                continue
            d = request("DELETE", f"{API}/channels/{channel_id}/messages/{m['id']}")
            if d.status_code in (204, 404):
                deleted_here += 1
                total_deleted += 1
                if total_deleted % 50 == 0:
                    print(f"المجموع حتى الآن: {total_deleted}")
            time.sleep(0.3)

    print(f"[{name}] تم حذف {deleted_here} | المجموع: {total_deleted}")


def get_archived_threads(channel_id):
    threads, before = [], None
    while True:
        params = {"limit": 100}
        if before:
            params["before"] = before
        r = request("GET", f"{API}/channels/{channel_id}/threads/archived/public", params=params)
        if r.status_code != 200:
            break
        data = r.json()
        threads += data.get("threads", [])
        if not data.get("has_more") or not data.get("threads"):
            break
        before = data["threads"][-1]["thread_metadata"]["archive_timestamp"]
    return threads


def main():
    me = request("GET", f"{API}/users/@me")
    if me.status_code != 200:
        print("التوكن غير صحيح:", me.status_code, me.text)
        return
    my_id = me.json()["id"]
    print("تسجيل الدخول كـ", me.json().get("username"))

    ch = request("GET", f"{API}/guilds/{GUILD_ID}/channels")
    if ch.status_code != 200:
        print("ما قدرت اجيب القنوات:", ch.status_code, ch.text)
        return
    channels = ch.json()

    targets = [(c["id"], c["name"]) for c in channels if c["type"] in CHANNEL_TYPES]

    # الثريدات النشطة
    t = request("GET", f"{API}/guilds/{GUILD_ID}/threads/active")
    if t.status_code == 200:
        targets += [(x["id"], f"thread:{x['name']}") for x in t.json().get("threads", [])]

    # الثريدات المؤرشفة (العامة) + منشورات الفورم
    for c in channels:
        if c["type"] in (0, 5, 15):
            targets += [(x["id"], f"thread:{x['name']}") for x in get_archived_threads(c["id"])]

    print(f"عدد القنوات والثريدات: {len(targets)}")
    for cid, name in targets:
        clean_channel(cid, name, my_id)

    print(f"خلصنا. تم حذف {total_deleted} رسالة.")


if __name__ == "__main__":
    main()
