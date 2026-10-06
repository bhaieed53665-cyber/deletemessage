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


def request(method, url, **kwargs):
    """يعيد المحاولة تلقائياً عند الـ rate limit."""
    while True:
        r = requests.request(method, url, headers=HEADERS, timeout=30, **kwargs)
        if r.status_code == 429:
            wait = r.json().get("retry_after", 1) + 0.5
            print(f"Rate limit، انتظار {wait:.1f} ثانية...")
            time.sleep(wait)
            continue
        return r


def main():
    me = request("GET", f"{API}/users/@me")
    if me.status_code != 200:
        print("التوكن غير صحيح:", me.status_code, me.text)
        return
    my_id = me.json()["id"]
    print("تسجيل الدخول كـ", me.json().get("username"))

    deleted = 0
    offset = 0  # بيزيد فقط لما في رسائل ما بتنحذف (مثل رسائل النظام)

    while True:
        r = request(
            "GET",
            f"{API}/guilds/{GUILD_ID}/messages/search",
            params={"author_id": my_id, "include_nsfw": "true", "offset": offset},
        )

        if r.status_code == 202:  # ديسكورد لسا عم يجهز الفهرس
            time.sleep(r.json().get("retry_after", 2))
            continue
        if r.status_code != 200:
            print("خطأ بالبحث:", r.status_code, r.text)
            break

        data = r.json()
        hits = [
            m
            for group in data.get("messages", [])
            for m in group
            if m.get("hit") and m["author"]["id"] == my_id
        ]

        if not hits:
            break

        failed = 0
        for m in hits:
            d = request("DELETE", f"{API}/channels/{m['channel_id']}/messages/{m['id']}")
            if d.status_code in (204, 404):
                deleted += 1
                print(f"تم الحذف ({deleted})")
            else:
                failed += 1
            time.sleep(0.4)

        offset += failed

    print(f"خلصنا. تم حذف {deleted} رسالة.")


if __name__ == "__main__":
    main()
