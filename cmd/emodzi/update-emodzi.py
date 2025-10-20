import json
import re
import aiohttp
import asyncio
from typing import Dict

# === Настройки ===
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"
COURSE_ID = 256069  # ваш ID курса
JSON_FILE = "course_cleaned_with_emojis.json"  # путь к файлу


# ==== Авторизация ====
async def get_access_token() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
                f"{STEPIC_HOST}/oauth2/token/",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==== Утилиты ====
async def fetch_json(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        text = await resp.text()
        print(f"GET {url} → {resp.status}")
        resp.raise_for_status()
        return await resp.json()


async def put_json(session, url, payload, headers):
    async with session.put(url, json=payload, headers=headers) as resp:
        text = await resp.text()
        print(f"PUT {url} → {resp.status}, response: {text}")
        if resp.status >= 400:
            raise Exception(f"PUT {url} failed: {resp.status} - {text}")
        return await resp.json()


# ==== Обновление названий секций и уроков ====
async def update_titles_from_json(course_id: int, json_path: str):
    with open(json_path, "r", encoding="utf-8") as f:
        local_data = json.load(f)

    token = await get_access_token()
    headers = mk_headers(token)

    async with aiohttp.ClientSession() as session:
        course_data = await fetch_json(session, f"{STEPIC_HOST}/api/courses/{course_id}", headers)
        section_ids = course_data["courses"][0].get("sections", [])
        print(f"🔢 Всего секций на Stepik: {len(section_ids)}")

        for section_json in local_data["sections"]:
            sec_id = section_json["section_id"]
            new_title = section_json["section_title"]

            print(f"✏️ Обновление секции {sec_id}: {new_title}")
            payload = {
                "section": {
                    "id": sec_id,
                    "course": course_id,
                    "title": new_title
                }
            }
            await put_json(session, f"{STEPIC_HOST}/api/sections/{sec_id}", payload, headers)

            for lesson_json in section_json["lessons"]:
                lesson_id = lesson_json["lesson_id"]
                new_lesson_title = lesson_json["lesson_title"]

                print(f"  └─ 📝 Урок {lesson_id}: {new_lesson_title}")
                payload = {
                    "lesson": {
                        "id": lesson_id,
                        "title": new_lesson_title
                    }
                }
                await put_json(session, f"{STEPIC_HOST}/api/lessons/{lesson_id}", payload, headers)

        print("\n✅ Все названия секций и уроков обновлены.")


# ==== Точка входа ====
async def main():
    await update_titles_from_json(COURSE_ID, JSON_FILE)


if __name__ == "__main__":
    asyncio.run(main())
