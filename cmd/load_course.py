import aiohttp
import asyncio
import json
import re
from typing import Dict
from motor.motor_asyncio import AsyncIOMotorClient

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"

MONGO_URL = "mongodb://localhost:27017"
DB_NAME = "stepik_courses"


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


# === Mongo ===
async def get_db():
    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]
    await db.courses.create_index("id", unique=True)
    await db.modules.create_index("id", unique=True)
    await db.lessons.create_index("id", unique=True)
    await db.steps.create_index("id", unique=True)
    return db


# === Утилиты ===
def safe_name(name: str) -> str:
    return re.sub(r'[\\/*?:"<>|]', "", name).strip().replace("\n", " ")[:100]


async def fetch_json(session, url, headers, sem):
    async with sem:  # ограничиваем количество параллельных запросов
        async with session.get(url, headers=headers) as resp:
            print(f"GET {url} → {resp.status}")
            resp.raise_for_status()
            return await resp.json()


# === Основная функция ===
async def export_course(course_id: int):
    token = await get_access_token()
    headers = mk_headers(token)
    db = await get_db()
    sem = asyncio.Semaphore(10)  # максимум 10 одновременных запросов

    # Очистим старые данные
    print(f"\n🧹 Удаляем старые данные для курса {course_id}...")
    await db.courses.delete_one({"id": course_id})
    await db.modules.delete_many({"course_id": course_id})
    await db.lessons.delete_many({"course_id": course_id})
    await db.steps.delete_many({"course_id": course_id})
    print("♻️ Старые данные удалены.\n")

    async with aiohttp.ClientSession() as session:
        # === Курс ===
        course_data = await fetch_json(session, f"{STEPIC_HOST}/api/courses/{course_id}", headers, sem)
        course = course_data["courses"][0]
        await db.courses.insert_one(course)
        print(f"📘 Курс: {course['title']}")

        # === Модули ===
        for section_id in course.get("sections", []):
            sec_data = await fetch_json(session, f"{STEPIC_HOST}/api/sections/{section_id}", headers, sem)
            section = sec_data["sections"][0]
            section["course_id"] = course_id
            await db.modules.insert_one(section)
            print(f"  📂 Модуль: {section['title']}")

            # === Уроки ===
            for unit_id in section.get("units", []):
                unit_data = await fetch_json(session, f"{STEPIC_HOST}/api/units/{unit_id}", headers, sem)
                unit = unit_data["units"][0]
                lesson_id = unit["lesson"]

                les_data = await fetch_json(session, f"{STEPIC_HOST}/api/lessons/{lesson_id}", headers, sem)
                lesson = les_data["lessons"][0]
                lesson["course_id"] = course_id
                lesson["section_id"] = section_id
                await db.lessons.insert_one(lesson)
                print(f"    📘 Урок: {lesson['title']}")

                # === Асинхронная загрузка шагов ===
                step_ids = lesson.get("steps", [])
                tasks = []

                async def fetch_and_store_step(step_id):
                    step_data = await fetch_json(session, f"{STEPIC_HOST}/api/steps/{step_id}", headers, sem)
                    step = step_data["steps"][0]
                    step["lesson_id"] = lesson_id
                    step["course_id"] = course_id
                    await db.steps.insert_one(step)
                    print(f"      ✅ Шаг {step_id}")

                for sid in step_ids:
                    tasks.append(asyncio.create_task(fetch_and_store_step(sid)))

                await asyncio.gather(*tasks)

    print(f"\n🎯 Курс {course_id} успешно обновлён в MongoDB.")


# === Точка входа ===
if __name__ == "__main__":
    COURSE_IDS = [256069]
    asyncio.run(export_course(COURSE_IDS[0]))
