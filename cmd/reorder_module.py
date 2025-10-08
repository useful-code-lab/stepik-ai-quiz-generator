import aiohttp
import asyncio
import re
from typing import Dict, List

# === Настройки ===
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"
COURSE_ID = 256069  # ваш ID курса


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


def extract_module_number(title: str) -> int:
    match = re.search(r"Модуль\s+(\d+)", title)
    return int(match.group(1)) if match else 0


# ==== Основная функция ====
async def reorder_sections(course_id: int):
    token = await get_access_token()
    headers = mk_headers(token)

    async with aiohttp.ClientSession() as session:
        # Получение ID секций курса
        course_data = await fetch_json(session, f"{STEPIC_HOST}/api/courses/{course_id}", headers)
        course = course_data["courses"][0]
        section_ids = course.get("sections", [])
        print(f"🔢 Найдено секций: {len(section_ids)}")

        sections = []
        for section_id in section_ids:
            sec_data = await fetch_json(session, f"{STEPIC_HOST}/api/sections/{section_id}", headers)
            section = sec_data["sections"][0]
            sections.append(section)

        # Сортировка секций по номеру модуля в названии
        sorted_sections = sorted(sections, key=lambda s: extract_module_number(s.get("title", "")))

        print("\n🔃 Новое упорядочивание модулей:")
        for new_pos, section in enumerate(sorted_sections, start=1):
            sid = section["id"]
            title = section["title"]
            old_pos = section.get("position", "❓")

            print(f"  🔁 {title}: {old_pos} → {new_pos}")

            # Обновляем только если позиция изменилась
            if old_pos != new_pos:
                payload = {
                    "section": {
                        "id": sid,
                        "course": course_id,
                        "title": title,
                        "description": section.get("description", ""),
                        "position": new_pos
                    }
                }

                url = f"{STEPIC_HOST}/api/sections/{sid}"
                await put_json(session, url, payload, headers)

        print("\n✅ Переупорядочивание завершено.")


# ==== Точка входа ====
async def main():
    await reorder_sections(COURSE_ID)


if __name__ == "__main__":
    asyncio.run(main())
