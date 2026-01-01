#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import re
import time
from typing import Dict, List

import aiohttp
import requests

COURSE_IDS = [263363]

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "rEQVrrQXjA0kUmV0OuisJeg2yYZFi90aqgWXIKAp"
CLIENT_SECRET = "I10ib8UG84JkbcTCB8yuX6lv1oWYNbBCu6jWgVHw4tpKP59ObwKJD8wU2ldGWYLdRGscZpZfcQ5KhvhXqtSYqVLJedDZUnLMghYOwxKVPmVu6demCfdlgjPkxYM0Qc0T"

MAX_CONCURRENT_REQUESTS = 10
FAILED_STEPS_FILE = "failed_steps.json"


# ==== Функция для замены слов ====
def replace_words(text: str) -> str:
    replacements = {
        # Астронавт / Космонавт
        "Астронавт": "Космонавт",
        "астронавт": "космонавт",
        "Астронавта": "Космонавта",
        "астронавта": "космонавта",
        # Астрофизик → Астронавт
        "Астрофизик": "Астронавт",
        "астрофизик": "астронавт",
        "Астрофизика": "Астронавта",
        "астрофизика": "астронавта",
        "Астрофизики": "Астронавты",
        "астрофизики": "астронавты",
        "Астрофизиков": "Астронавтов",
        "астрофизиков": "астронавтов",
        "Астрофизику": "Астронавту",
        "астрофизику": "астронавту",
        "Астрофизиком": "Астронавтом",
        "астрофизиком": "астронавтом",
        # Подросток → Тинейджер
        "Подросток": "Тинейджер",
        "подросток": "тинейджер",
        "Подростка": "Тинейджера",
        "подростка": "тинейджера",
        "Подростки": "Тинейджеры",
        "подростки": "тинейджеры",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text


# ==== HTML генерация ====
def options_to_html(options):
    html_content = "<ul>\n"
    for opt in options:
        text = opt.get("text", "")
        if opt.get("is_correct"):
            html_content += f"  <li><b>{text}</b></li>\n"
        else:
            html_content += f"  <li>{text}</li>\n"
    html_content += "</ul>"
    return f'<details><summary>Показать ответ</summary>{html_content}</details>'


def pairs_to_html(pairs):
    html_content = "<ul>\n"
    for pair in pairs:
        first = pair.get("first", "")
        second = pair.get("second", "")
        html_content += f"  <li><b>{first}</b> — {second}</li>\n"
    html_content += "</ul>"
    return f'<details><summary>Показать ответ</summary>{html_content}</details>'


# ==== Асинхронные HTTP функции ====
async def get_access_token(session: aiohttp.ClientSession) -> str:
    async with session.post(
        f"{STEPIC_HOST}/oauth2/token/",
        data={"grant_type": "client_credentials"},
        auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET),
        timeout=30,
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return data["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==== Обновление блока Stepik ====
async def update_step_source(
    session: aiohttp.ClientSession, step_id: int, token: str, semaphore: asyncio.Semaphore, failed_steps: List[int]
):
    headers = mk_headers(token)

    async with semaphore:
        for attempt in range(3):
            try:
                # Получаем блок
                async with session.get(f"{STEPIC_HOST}/api/step-sources/{step_id}", headers=headers, timeout=120) as r:
                    r.raise_for_status()
                    data = (await r.json())["step-sources"][0]

                block = data["block"]

                if block["name"] not in {"choice", "matching", "sorting"}:
                    return

                update = False

                # Заменяем слова в тексте блока
                block["text"] = replace_words(block.get("text", ""))

                # Заменяем слова в вариантах/парах
                if block["name"] in {"choice", "sorting"}:
                    for opt in block["source"]["options"]:
                        opt["text"] = replace_words(opt.get("text", ""))
                    html_output = options_to_html(block["source"]["options"])
                elif block["name"] == "matching":
                    for pair in block["source"]["pairs"]:
                        pair["first"] = replace_words(pair.get("first", ""))
                        pair["second"] = replace_words(pair.get("second", ""))
                    html_output = pairs_to_html(block["source"]["pairs"])
                else:
                    html_output = ""

                # Удаляем мусорные строки
                for garbage in ["<p></p>", "&lt;/&lt;li&gt;", "&lt;/&lt;p&gt;"]:
                    if garbage in block["text"]:
                        block["text"] = block["text"].replace(garbage, "")
                        update = True

                # Добавляем HTML с ответами
                # Перед добавлением HTML
                # Убираем старый блок <details> с ответами, если он есть
                block["text"] = re.sub(r'<details><summary>Показать ответ</summary>.*?</details>', '', block["text"],
                                       flags=re.DOTALL)
                # Теперь безопасно добавляем HTML
                block["text"] += html_output

                data["block"] = block
                data["cost"] = 5
                payload = {"step-source": data}

                # Отправляем на Stepik
                async with session.put(f"{STEPIC_HOST}/api/step-sources/{step_id}", headers=headers, json=payload, timeout=120) as r:
                    r.raise_for_status()
                    print(f"✅ Step {step_id} обновлён")
                    return

            except Exception as e:
                print(f"Ошибка step_id={step_id}, попытка {attempt + 1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(5)
                else:
                    failed_steps.append(step_id)
                    print(f"❌ Превышено количество попыток для step_id={step_id}")


# ==== Синхронное получение шагов курса ====
def get_units_and_steps(token: str, course_id: int) -> List[int]:
    headers = mk_headers(token)
    step_ids = []

    try:
        r = requests.get(f"{STEPIC_HOST}/api/courses/{course_id}", headers=headers, timeout=60)
        r.raise_for_status()
        course = r.json()["courses"][0]

        for section_id in course.get("sections", []):
            try:
                r = requests.get(f"{STEPIC_HOST}/api/sections/{section_id}", headers=headers, timeout=60)
                r.raise_for_status()
                section = r.json()["sections"][0]

                for unit_id in section.get("units", []):
                    try:
                        r = requests.get(f"{STEPIC_HOST}/api/units/{unit_id}", headers=headers, timeout=60)
                        r.raise_for_status()
                        unit = r.json()["units"][0]
                        lesson_id = unit["lesson"]

                        r = requests.get(f"{STEPIC_HOST}/api/lessons/{lesson_id}", headers=headers, timeout=60)
                        r.raise_for_status()
                        lesson = r.json()["lessons"][0]

                        step_ids.extend(lesson.get("steps", []))

                    except Exception as e:
                        print(f"Ошибка unit_id={unit_id}, lesson_id={lesson_id}: {e}")
                        time.sleep(2)
                        continue
            except Exception as e:
                print(f"Ошибка section_id={section_id}: {e}")
                time.sleep(2)
                continue
    except Exception as e:
        print(f"Ошибка при получении курса {course_id}: {e}")

    return step_ids


# ==== Основной запуск ====
async def process_course(session: aiohttp.ClientSession, token: str, course_id: int, semaphore: asyncio.Semaphore, failed_steps: List[int]):
    step_ids = get_units_and_steps(token, course_id)
    tasks = [update_step_source(session, step_id, token, semaphore, failed_steps) for step_id in step_ids]
    await asyncio.gather(*tasks)


async def main():
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)
    failed_steps = []

    async with aiohttp.ClientSession() as session:
        token = await get_access_token(session)
        tasks = [process_course(session, token, course_id, semaphore, failed_steps) for course_id in COURSE_IDS]
        await asyncio.gather(*tasks)

    if failed_steps:
        with open(FAILED_STEPS_FILE, "w", encoding="utf-8") as f:
            json.dump(failed_steps, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Неудачные шаги сохранены в {FAILED_STEPS_FILE}")


if __name__ == "__main__":
    asyncio.run(main())

