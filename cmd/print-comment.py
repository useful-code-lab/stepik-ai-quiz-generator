import aiohttp
import asyncio
import json
from pathlib import Path
from typing import Dict, Any, List

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"

JSON_FILE = Path("course_comments.json")


# ==== Авторизация ====
async def get_access_token() -> str:
    async with aiohttp.ClientSession() as session:
        async with session.post(
            f"{STEPIC_HOST}/oauth2/token/",
            data={"grant_type": "client_credentials"},
            auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET),
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def fetch_json(session: aiohttp.ClientSession, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with session.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.json()


# ==== Логика обхода ====
async def fetch_course_comments(session: aiohttp.ClientSession, course_id: int, headers: Dict[str, str]) -> List[str]:
    comments: List[str] = []

    # 1. Берём курс → sections
    course_url = f"{STEPIC_HOST}/api/courses/{course_id}"
    course_data = await fetch_json(session, course_url, headers)
    sections_ids = list(course_data["courses"][0].get("sections") or [])

    # 2. Для каждой секции → units
    for sec_id in sections_ids:
        sec_url = f"{STEPIC_HOST}/api/sections/{sec_id}"
        sec_data = await fetch_json(session, sec_url, headers)
        units_ids = list(sec_data["sections"][0].get("units") or [])

        for unit_id in units_ids:
            unit_url = f"{STEPIC_HOST}/api/units/{unit_id}"
            unit_data = await fetch_json(session, unit_url, headers)
            lesson_id = unit_data["units"][0].get("lesson")
            if not lesson_id:
                continue

            # 3. Берём урок → steps
            lesson_url = f"{STEPIC_HOST}/api/lessons/{lesson_id}"
            lesson_data = await fetch_json(session, lesson_url, headers)
            step_ids = list(lesson_data["lessons"][0].get("steps") or [])

            for step_id in step_ids:
                step_url = f"{STEPIC_HOST}/api/steps/{step_id}"
                step_data = await fetch_json(session, step_url, headers)

                # 4. У шага есть discussion_thread
                thread_id = step_data["steps"][0].get("discussion_thread")
                if not thread_id:
                    continue

                # 5. Тянем комментарии постранично
                page = 1
                while True:
                    comments_url = f"{STEPIC_HOST}/api/comments?discussion={thread_id}&page={page}"
                    comments_data = await fetch_json(session, comments_url, headers)
                    comments_list = comments_data.get("comments") or []
                    for c in comments_list:
                        txt = c.get("text", "").strip()
                        if txt:
                            comments.append(txt)
                    if not comments_data.get("meta", {}).get("has_next"):
                        break
                    page += 1

    return comments


# ==== Основной запуск ====
async def main():
    token = await get_access_token()
    headers = mk_headers(token)

    # Тут можно вставить список курсов из 1-course.xml или вручную
    course_ids = [251835]
    results = {}

    async with aiohttp.ClientSession() as session:
        for course_id in course_ids:
            try:
                comments = await fetch_course_comments(session, course_id, headers)
                if comments:  # сохраняем только если есть комментарии
                    results[course_id] = comments
                    print(f"Курс {course_id}: {len(comments)} комментариев")
                else:
                    print(f"Курс {course_id}: комментариев нет")
            except Exception as e:
                print(f"Ошибка при курсе {course_id}: {e}")

    JSON_FILE.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Комментарии сохранены в {JSON_FILE}")


if __name__ == "__main__":
    asyncio.run(main())
