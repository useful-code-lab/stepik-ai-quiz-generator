import aiohttp
import asyncio
import json
import re
import os
from typing import Dict

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"

SAVE_DIR = "courses"   # куда сохраняем всё


# === Авторизация ===
async def get_access_token() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{STEPIC_HOST}/oauth2/token/",
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)
        ) as resp:
            resp.raise_for_status()
            return (await resp.json())["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


# === Утилиты ===
def safe_name(name: str) -> str:
    """убираем лишние символы для имени файла/папки"""
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace("\n", " ")[:100]


async def fetch_json(session, url, headers, sem):
    async with sem:  # ограничиваем количество параллельных запросов
        async with session.get(url, headers=headers) as resp:
            print(f"GET {url} → {resp.status}")
            resp.raise_for_status()
            return await resp.json()


def save_json_to_file(data: dict, path: str):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


async def download_file(session, url, path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    async with session.get(url) as resp:
        resp.raise_for_status()
        with open(path, "wb") as f:
            f.write(await resp.read())
    print(f"💾 Скачан файл: {path}")


# === Основная функция для курса ===
async def export_course(course_id: int, session, headers, sem):
    try:
        # === Курс ===
        course_data = await fetch_json(session, f"{STEPIC_HOST}/api/courses/{course_id}", headers, sem)
        course = course_data["courses"][0]
        course_title = safe_name(course["title"])
        print(f"\n📘 Курс: {course_title} (id={course_id})")

        course_dir = os.path.join(SAVE_DIR, course_title)
        os.makedirs(course_dir, exist_ok=True)

        # сохраняем метаданные курса
        save_json_to_file(course, os.path.join(course_dir, "course.json"))

        # сохраняем обложку
        cover_url = course.get("cover")
        if cover_url:
            ext = os.path.splitext(cover_url)[1] or ".jpg"
            cover_path = os.path.join(course_dir, f"cover{ext}")
            await download_file(session, cover_url, cover_path)
        else:
            print("⚠️ У курса нет обложки")

        # === Модули ===
        for section_id in course.get("sections", []):
            sec_data = await fetch_json(session, f"{STEPIC_HOST}/api/sections/{section_id}", headers, sem)
            section = sec_data["sections"][0]
            sec_title = safe_name(section["title"])
            print(f"  📂 Модуль: {sec_title}")

            sec_dir = os.path.join(course_dir, sec_title)
            os.makedirs(sec_dir, exist_ok=True)
            save_json_to_file(section, os.path.join(sec_dir, "module.json"))

            # === Уроки ===
            for unit_id in section.get("units", []):
                unit_data = await fetch_json(session, f"{STEPIC_HOST}/api/units/{unit_id}", headers, sem)
                unit = unit_data["units"][0]
                lesson_id = unit["lesson"]

                les_data = await fetch_json(session, f"{STEPIC_HOST}/api/lessons/{lesson_id}", headers, sem)
                lesson = les_data["lessons"][0]
                les_title = safe_name(lesson["title"])
                print(f"    📘 Урок: {les_title}")

                les_dir = os.path.join(sec_dir, les_title)
                os.makedirs(les_dir, exist_ok=True)
                save_json_to_file(lesson, os.path.join(les_dir, "lesson.json"))

                # === Шаги ===
                step_ids = lesson.get("steps", [])
                tasks = []

                async def fetch_and_save_step(step_id, les_dir=les_dir):
                    step_data = await fetch_json(session, f"{STEPIC_HOST}/api/steps/{step_id}", headers, sem)
                    step = step_data["steps"][0]
                    save_json_to_file(step, os.path.join(les_dir, f"step_{step_id}.json"))
                    print(f"      ✅ Шаг {step_id} сохранён")

                for sid in step_ids:
                    tasks.append(asyncio.create_task(fetch_and_save_step(sid)))

                await asyncio.gather(*tasks)

        print(f"🎯 Курс {course_title} сохранён.")
    except Exception as e:
        print(f"❌ Ошибка при обработке курса {course_id}: {e}")


# === Точка входа ===
async def main():
    COURSE_IDS = [
        250336, 251675, 251711, 251831, 251833, 251834, 251835, 251924,
        251953, 252037, 252068, 252535, 252572, 252646, 252647, 252874,
        252927, 253010, 253470, 253487, 253488, 253489, 253490, 253491,
        253493, 253614, 253631, 253692, 253935, 254045, 254321, 254324,
        254325, 254326, 254432, 254446, 254584, 255077, 255396, 255397,
        255398, 255399, 255400, 255401, 255403, 255404, 255405, 255406,
        255408, 255409, 255410, 255411, 255412, 255458, 255500, 255587,
        255614, 255790, 256212, 256313, 256362, 256452, 256519, 256741, 256742
    ]

    token = await get_access_token()
    headers = mk_headers(token)
    sem = asyncio.Semaphore(10)

    async with aiohttp.ClientSession() as session:
        for cid in COURSE_IDS:
            await export_course(cid, session, headers, sem)


if __name__ == "__main__":
    asyncio.run(main())
