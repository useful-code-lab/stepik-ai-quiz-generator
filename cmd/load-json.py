import aiohttp
import asyncio
import json
from typing import Dict

# === Настройки ===
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"
COURSE_ID = 257520


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


# ==== Универсальный загрузчик JSON ====
async def fetch_json(session, url, headers):
    async with session.get(url, headers=headers) as resp:
        print(f"GET {url} → {resp.status}")
        resp.raise_for_status()
        return await resp.json()


# ==== Основная функция ====
async def export_course_structure(course_id: int):
    token = await get_access_token()
    headers = mk_headers(token)

    async with aiohttp.ClientSession() as session:
        # === Курс ===
        course_data = await fetch_json(session, f"{STEPIC_HOST}/api/courses/{course_id}", headers)
        course = course_data["courses"][0]
        section_ids = course.get("sections", [])
        print(f"🔍 Найдено секций: {len(section_ids)}")

        course_result = {
            "id": course_id,
            "title": course.get("title", ""),
            "slug": course.get("slug", ""),
            "summary": course.get("summary", ""),
            "sections": []
        }

        # === Секции ===
        for section_id in section_ids:
            sec_data = await fetch_json(session, f"{STEPIC_HOST}/api/sections/{section_id}", headers)
            section = sec_data["sections"][0]
            unit_ids = section.get("units", [])
            lessons_data = []

            # === Юниты / Уроки ===
            for unit_id in unit_ids:
                unit_data = await fetch_json(session, f"{STEPIC_HOST}/api/units/{unit_id}", headers)
                unit = unit_data["units"][0]
                lesson_id = unit.get("lesson")

                if lesson_id:
                    lesson_data = await fetch_json(session, f"{STEPIC_HOST}/api/lessons/{lesson_id}", headers)
                    lesson = lesson_data["lessons"][0]

                    lessons_data.append({
                        "lesson_id": lesson_id,
                        "lesson_title": lesson.get("title", f"Без названия ({lesson_id})"),
                        "unit_id": unit_id,
                    })

            section_entry = {
                "section_id": section_id,
                "section_title": section.get("title", ""),
                "lessons": lessons_data
            }

            course_result["sections"].append(section_entry)

        # === Сохранение JSON ===
        filename = f"course_{course_id}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(course_result, f, ensure_ascii=False, indent=2)

        print(f"✅ Курс {course_id} сохранён в {filename}")


# ==== Точка входа ====
async def main():
    await export_course_structure(COURSE_ID)


if __name__ == "__main__":
    asyncio.run(main())
