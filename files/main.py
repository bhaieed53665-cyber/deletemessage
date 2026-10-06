import os
import time
import requests

TOKEN = os.environ["DISCORD_TOKEN"]   # توكن حسابك (من متغيرات Railway)
GUILD_ID = os.environ.get("GUILD_ID")  # ID السيرفر (مطلوب فقط إذا ما حددت قنوات)
# IDs القنوات المطلوبة مفصولة بفاصلة، مثال: 111,222,333 (اتركه فاضي لحذف كل السيرفر)
CHANNEL_IDS = [c.strip() for c in os.environ.get("CHANNEL_IDS", "").split(",") if c.strip()]

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
    scanned = 0

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
        scanned += len(msgs)
        if scanned % 1000 < 100:
            print(f"[{name}] تم فحص {scanned} رسالة | حذف {deleted_here}")

        for m in msgs:
            if m["author"]["id"] != my_id or m["type"] not in DELETABLE_MSG_TYPES:
                continue
            d = request("DELETE", f"{API}/channels/{channel_id}/messages/{m['id']}")
            if d.status_code in (204, 404):
                deleted_here += 1
                total_deleted += 1
                if total_deleted % 10 == 0:
                    print(f"تم الحذف: {total_deleted}")
            else:
                print(f"فشل حذف رسالة: {d.status_code} {d.text[:80]}")
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


def clean_channel_fast(channel_id, my_id):
    """يبحث عن رسائلك أنت فقط بالقناة ويحذفها (بدون فحص رسائل الناس)."""
    global total_deleted
    if not GUILD_ID:
        print("GUILD_ID مش موجود، رح يستخدم الفحص العادي")
        return clean_channel(channel_id, channel_id, my_id)

    deleted_here = 0
    offset = 0
    empty_retries = 0

    while True:
        r = request(
            "GET",
            f"{API}/guilds/{GUILD_ID}/messages/search",
            params={
                "author_id": my_id,
                "channel_id": channel_id,
                "include_nsfw": "true",
                "offset": offset,
            },
        )
        if r.status_code == 202:  # الفهرس لسا عم يجهز
            time.sleep(r.json().get("retry_after", 2))
            continue
        if r.status_code != 200:
            print(f"خطأ بالبحث: {r.status_code} {r.text[:100]}")
            break

        data = r.json()
        total = data.get("total_results", 0)
        hits = [
            m
            for group in data.get("messages", [])
            for m in group
            if m.get("hit") and m["author"]["id"] == my_id
        ]

        if not hits:
            if total == 0:
                break  # خلصت رسائلك فعلاً
            empty_retries += 1
            if empty_retries >= 5:
                print("البحث رجع صفحة فاضية رغم وجود رسائل، تحويل للفحص العادي")
                return clean_channel(channel_id, channel_id, my_id)
            time.sleep(5)
            continue
        empty_retries = 0

        print(f"رسائلك المتبقية بالقناة تقريباً: {total}")
        failed = 0
        for m in hits:
            if m["type"] not in DELETABLE_MSG_TYPES:
                failed += 1
                continue
            d = request("DELETE", f"{API}/channels/{channel_id}/messages/{m['id']}")
            if d.status_code in (204, 404):
                deleted_here += 1
                total_deleted += 1
                if total_deleted % 10 == 0:
                    print(f"تم الحذف: {total_deleted}")
            else:
                failed += 1
                print(f"فشل حذف رسالة: {d.status_code} {d.text[:80]}")
            time.sleep(0.3)
        offset += failed

    print(f"[{channel_id}] خلصت. تم حذف {deleted_here} | المجموع: {total_deleted}")


def diagnose(my_id):
    """يعدّ رسائلك بكل قناة بالسيرفر بدون حذف أي شي."""
    ch = request("GET", f"{API}/guilds/{GUILD_ID}/channels")
    if ch.status_code != 200:
        print("ما قدرت اجيب القنوات:", ch.status_code, ch.text)
        return
    chans = [(c["id"], c["name"]) for c in ch.json() if c["type"] in CHANNEL_TYPES]
    t = request("GET", f"{API}/guilds/{GUILD_ID}/threads/active")
    if t.status_code == 200:
        chans += [(x["id"], f"thread:{x['name']}") for x in t.json().get("threads", [])]

    print(f"تشخيص {len(chans)} قناة...")
    results = []
    for cid, name in chans:
        while True:
            r = request(
                "GET",
                f"{API}/guilds/{GUILD_ID}/messages/search",
                params={"author_id": my_id, "channel_id": cid, "include_nsfw": "true"},
            )
            if r.status_code == 202:  # الفهرس لسا عم يجهز
                time.sleep(r.json().get("retry_after", 2))
                continue
            break
        if r.status_code == 200:
            n = r.json().get("total_results", 0)
            if n:
                results.append((n, cid, name))
                print(f"{name} | ID: {cid} | رسائلك: {n}")
        time.sleep(1)

    results.sort(reverse=True)
    print("===== الأعلى =====")
    for n, cid, name in results[:15]:
        print(f"{n} رسالة | {name} | {cid}")
    print(f"المجموع: {sum(n for n, _, _ in results)}")


def main():
    me = request("GET", f"{API}/users/@me")
    if me.status_code != 200:
        print("التوكن غير صحيح:", me.status_code, me.text)
        return
    my_id = me.json()["id"]
    print("تسجيل الدخول كـ", me.json().get("username"))

    # وضع التشخيص: DIAGNOSE=1 بيعدّ رسائلك بكل قناة بدون حذف
    if os.environ.get("DIAGNOSE") == "1":
        if not GUILD_ID:
            print("لازم تحط GUILD_ID للتشخيص")
            return
        diagnose(my_id)
        return

    # إذا حددت قنوات، احذف منها فقط وبدون المرور على باقي السيرفر
    if CHANNEL_IDS:
        print(f"عدد القنوات المحددة: {len(CHANNEL_IDS)}")
        for cid in CHANNEL_IDS:
            clean_channel_fast(cid, my_id)
        print(f"خلصنا. تم حذف {total_deleted} رسالة.")
        return

    if not GUILD_ID:
        print("لازم تحط GUILD_ID أو CHANNEL_IDS")
        return

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
