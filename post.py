"""
post.py — Auto-generate topic + tweet via AI, then post to X.

Flow setiap run:
  1. AI pilih topik yang relevan dan menarik (auto)
  2. AI generate tweet dari topik tersebut (< 250 karakter)
  3. Post ke X via cookie-based auth
  4. Catat hasilnya ke posted_log.json

Environment variables (GitHub Actions secrets):
  AI_API       — Base URL OpenAI-compatible  e.g. https://chat.khoirulaziz757.workers.dev/v1
  AI_API_KEY   — API key
  X_AUTH_TOKEN — Cookie auth_token dari X/Twitter
  X_CTO        — Cookie ct0 dari X/Twitter (CSRF token)
"""

import json
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

import requests

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

LOG_FILE = Path("posted_log.json")

AI_MODEL = "@cf/meta/llama-3.3-70b-instruct-fp8-fast"

# Niche/kategori konten — ganti sesuai brand/persona akun-mu
CONTENT_NICHES = [
    "produktivitas dan manajemen waktu",
    "mindset dan pengembangan diri",
    "kebiasaan sukses",
    "belajar dan skill baru",
    "kesehatan mental dan fokus",
    "karier dan dunia kerja",
    "keuangan pribadi",
    "kepemimpinan dan komunikasi",
    "motivasi sehari-hari",
    "kreativitas dan inovasi",
]

# X / Twitter GraphQL endpoint
X_CREATE_TWEET_URL = (
    "https://x.com/i/api/graphql/"
    "oB-5XsA-erG3bgraARPsVA/CreateTweet"
)

X_PUBLIC_BEARER = (
    "Bearer AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D"
    "1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA"
)

# ---------------------------------------------------------------------------
# AI
# ---------------------------------------------------------------------------

def call_ai(system: str, user: str) -> str:
    ai_api = os.environ.get("AI_API", "").rstrip("/")
    ai_key = os.environ.get("AI_API_KEY", "")

    if not ai_api or not ai_key:
        raise EnvironmentError("AI_API dan AI_API_KEY harus di-set.")

    resp = requests.post(
        f"{ai_api}/chat/completions",
        json={
            "model": AI_MODEL,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": 400,
            "temperature": 0.9,
        },
        headers={
            "Authorization": f"Bearer {ai_key}",
            "Content-Type": "application/json",
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"].strip()


def pick_topic() -> str:
    """Minta AI pilih topik spesifik dan unik dari niche yang tersedia."""
    today = datetime.now(timezone.utc).strftime("%A, %d %B %Y")
    niches = "\n".join(f"- {n}" for n in CONTENT_NICHES)

    topic = call_ai(
        system=(
            "Kamu adalah content strategist media sosial. "
            "Tugasmu memilih topik tweet yang spesifik, relevan, dan belum klise. "
            "Balas HANYA dengan topik singkat (5-10 kata), tanpa penjelasan."
        ),
        user=(
            f"Hari ini: {today}\n\n"
            f"Pilih SATU topik yang paling menarik untuk tweet hari ini "
            f"dari niche berikut:\n{niches}\n\n"
            "Topik harus spesifik dan belum terlalu umum. "
            "Contoh yang baik: 'kenapa orang pintar sering overwhelmed' "
            "bukan sekadar 'produktivitas'. "
            "Balas hanya topiknya saja."
        ),
    )
    return topic.strip('"\'').strip()


def generate_tweet(topic: str) -> str:
    """Generate tweet dari topik menggunakan prompt template."""
    prompt = (
        f"Tulis sebuah tweet X yang menarik dan mudah diingat tentang: {topic}. "
        "Mulailah dengan kalimat pembuka yang menarik perhatian, "
        "gunakan kalimat pendek dan lugas, "
        "dan akhiri dengan ajakan bertindak (CTA). "
        "Jaga agar panjangnya di bawah 250 huruf. "
        "Balas HANYA dengan teks tweet-nya saja, tanpa tanda kutip, "
        "tanpa label, tanpa penjelasan tambahan."
    )

    tweet = call_ai(
        system=(
            "Kamu adalah copywriter media sosial profesional. "
            "Buat konten X (Twitter) yang viral, engaging, dan autentik "
            "dalam bahasa Indonesia. "
            "Jangan gunakan hashtag kecuali diminta. "
            "Selalu ikuti instruksi panjang karakter."
        ),
        user=prompt,
    )

    # Bersihkan artefak yang kadang muncul dari LLM
    tweet = tweet.strip('"\'').strip()
    for prefix in ("Tweet:", "tweet:", "Teks:", "Output:", "Jawaban:"):
        if tweet.startswith(prefix):
            tweet = tweet[len(prefix):].strip()

    return tweet


# ---------------------------------------------------------------------------
# X Posting
# ---------------------------------------------------------------------------

def post_to_x(text: str) -> str:
    auth_token = os.environ.get("X_AUTH_TOKEN", "")
    ct0 = os.environ.get("X_CTO", "")

    if not auth_token or not ct0:
        raise EnvironmentError("X_AUTH_TOKEN dan X_CTO harus di-set.")

    client_uuid = str(uuid4())

    headers = {
        "authorization": X_PUBLIC_BEARER,
        "x-csrf-token": ct0,
        "content-type": "application/json",
        "cookie": f"auth_token={auth_token}; ct0={ct0}",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/125.0.0.0 Safari/537.36"
        ),
        "x-twitter-active-user": "yes",
        "x-twitter-auth-type": "OAuth2Session",
        "x-twitter-client-language": "en",
        "x-client-uuid": client_uuid,
        "x-client-transaction-id": client_uuid,
        "referer": "https://x.com/compose/post",
        "origin": "https://x.com",
        "accept": "*/*",
        "accept-language": "en-US,en;q=0.9",
        "accept-encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Google Chrome";v="125", "Chromium";v="125", "Not.A/Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-origin",
    }

    payload = {
        "variables": {
            "tweet_text": text,
            "dark_request": False,
            "media": {"media_entities": [], "possibly_sensitive": False},
            "semantic_annotation_ids": [],
            "disallowed_reply_options": None,
        },
        "features": {
            "communities_web_enable_tweet_community_results_fetch": True,
            "c9s_tweet_anatomy_moderator_badge_enabled": True,
            "responsive_web_edit_tweet_api_enabled": True,
            "graphql_is_translatable_rweb_tweet_is_translatable_enabled": True,
            "view_counts_everywhere_api_enabled": True,
            "longform_notetweets_consumption_enabled": True,
            "responsive_web_twitter_article_tweet_consumption_enabled": True,
            "tweet_awards_web_tipping_enabled": False,
            "creator_subscriptions_quote_tweet_preview_enabled": False,
            "longform_notetweets_rich_text_read_enabled": True,
            "longform_notetweets_inline_media_enabled": True,
            "articles_preview_enabled": True,
            "rweb_video_timestamps_enabled": True,
            "rweb_tipjar_consumption_enabled": True,
            "responsive_web_graphql_exclude_directive_enabled": True,
            "verified_phone_label_enabled": False,
            "freedom_of_speech_not_reach_fetch_enabled": True,
            "standardized_nudges_misinfo": True,
            "tweet_with_visibility_results_prefer_gql_limited_actions_policy_enabled": True,
            "responsive_web_graphql_skip_user_profile_image_extensions_enabled": False,
            "responsive_web_graphql_timeline_navigation_enabled": True,
            "responsive_web_enhance_cards_enabled": False,
            "premium_content_api_read_enabled": False,
        },
        "queryId": "oB-5XsA-erG3bgraARPsVA",
    }

    resp = requests.post(
        X_CREATE_TWEET_URL, json=payload, headers=headers, timeout=30
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"X API error {resp.status_code}: {resp.text[:600]}"
        )

    data = resp.json()

    # Cek error dari X dalam response body (status 200 tapi ada errors)
    if "errors" in data:
        errors = data["errors"]
        for err in errors:
            code = err.get("code")
            msg = err.get("message", "")
            if code == 226:
                raise RuntimeError(
                    f"[Error 226] X mendeteksi aktivitas otomatis.\n"
                    f"Kemungkinan penyebab:\n"
                    f"  1. Cookie X_AUTH_TOKEN / X_CTO sudah expired — perbarui dari browser.\n"
                    f"  2. Akun belum verifikasi nomor HP di x.com/settings/phone.\n"
                    f"  3. Akun terlalu baru atau posting terlalu sering.\n"
                    f"Pesan asli: {msg}"
                )
            elif code == 32:
                raise RuntimeError(
                    f"[Error 32] Autentikasi gagal — X_AUTH_TOKEN atau X_CTO salah/expired.\n"
                    f"Perbarui cookie dari browser dan update GitHub Secrets."
                )
        raise RuntimeError(f"X API errors: {json.dumps(errors)[:400]}")

    try:
        tweet_id = (
            data["data"]["create_tweet"]["tweet_results"]["result"]["rest_id"]
        )
    except (KeyError, TypeError) as exc:
        raise RuntimeError(
            f"Unexpected X response: {exc}\n{json.dumps(data)[:400]}"
        )

    return tweet_id


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def append_log(entry: dict) -> None:
    log: list[dict] = []
    if LOG_FILE.exists():
        with LOG_FILE.open(encoding="utf-8") as f:
            try:
                log = json.load(f)
            except json.JSONDecodeError:
                log = []
    log.append(entry)
    with LOG_FILE.open("w", encoding="utf-8") as f:
        json.dump(log, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    print("[INFO] === Auto-posting dimulai ===")

    # Step 1: AI pilih topik
    print("[INFO] AI sedang memilih topik...")
    topic = pick_topic()
    print(f"[INFO] Topik terpilih: {topic!r}")

    # Step 2: AI generate tweet
    print("[INFO] AI sedang generate tweet...")
    tweet_text = generate_tweet(topic)

    # Pastikan tidak melebihi 250 karakter
    if len(tweet_text) > 250:
        tweet_text = tweet_text[:247] + "..."

    print(f"[INFO] Tweet ({len(tweet_text)} karakter):\n{tweet_text}\n")

    # Step 3: Post ke X
    tweet_id = post_to_x(tweet_text)
    print(f"[OK] Tweet berhasil diposting! ID: {tweet_id}")
    print(f"     https://x.com/i/web/status/{tweet_id}")

    # Step 4: Simpan log
    append_log({
        "id": str(uuid4()),
        "posted_at": datetime.now(timezone.utc).isoformat(),
        "topic": topic,
        "tweet_text": tweet_text,
        "tweet_id": tweet_id,
        "url": f"https://x.com/i/web/status/{tweet_id}",
    })
    print("[INFO] Log disimpan ke posted_log.json")


if __name__ == "__main__":
    main()
