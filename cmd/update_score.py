#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import html
import re

import aiohttp
import requests
import json
import time
from typing import Dict, Any, List

COURSE_IDS = [
    256658
]

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"
MAX_CONCURRENT_REQUESTS = 10  # ограничение одновременных запросов
FAILED_STEPS_FILE = "failed_steps.json"


# ==== HTML генерация ====
def options_to_html(options):
    html = '<ul>\n'
    for opt in options:
        text = opt.get("text", "")
        if opt.get("is_correct"):
            html += f'  <li><b>{text}</b></li>\n'
        else:
            html += f'  <li>{text}</li>\n'
    html += '</ul>'
    return f'<details><summary>Показать ответ</summary>{html}</details>'


def pairs_to_html(options):
    html = '<ul>\n'
    for opt in options:
        first = opt.get("first", "")
        second = opt.get("second", "")
        html += f'  <li><b>{first}</b> — {second}</li>\n'
    html += '</ul>'
    return f'<details><summary>Показать ответ</summary>{html}</details>'


# ==== Асинхронные HTTP функции ====
async def get_access_token(session: aiohttp.ClientSession) -> str:
    async with session.post(
        f"{STEPIC_HOST}/oauth2/token/",
        data={"grant_type": "client_credentials"},
        auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET),
        timeout=30
    ) as resp:
        resp.raise_for_status()
        data = await resp.json()
        return data["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def update_step_source(session: aiohttp.ClientSession, step_id: int, token: str, semaphore: asyncio.Semaphore, failed_steps: List[int]):
    headers = mk_headers(token)

    async with semaphore:
        for attempt in range(3):
            try:
                async with session.get(f"{STEPIC_HOST}/api/step-sources/{step_id}", headers=headers, timeout=120) as r:
                    r.raise_for_status()
                    data = (await r.json())["step-sources"][0]

                block = data["block"]
                update = False

                if '<details><summary>Показать ответ</summary>' not in block["text"]:
                    html_output = None

                    if '<details><summary>Показать ответ</summary>' not in block["text"]:
                        if block["name"] == "choice":
                            options = block["source"]["options"]
                            html_output = options_to_html(options)

                        elif block["name"] == "matching":
                            pairs = block["source"]["pairs"]
                            html_output = pairs_to_html(pairs)

                        elif block["name"] == "sorting":
                            options = block["source"]["options"]
                            html_output = options_to_html(options)

                        if html_output is not None:
                            update = True

                    if '<p>&nbsp;</p>' in block["text"] or '&lt;/&lt;li&gt;' in block["text"]:
                        block["text"] = re.sub(r'<p>&nbsp;</p>', '', block["text"])
                        block["text"] = re.sub(r'&lt;/&lt;li&gt;', '', block["text"])
                        update = True
                        if html_output is None:
                            html_output = ""

                    if not update:
                        return

                    block["text"] += html_output
                    data["block"] = block
                    data["cost"] = 5
                    payload = {"step-source": data}

                    async with session.put(
                        f"{STEPIC_HOST}/api/step-sources/{step_id}",
                        headers=headers,
                        data=json.dumps(payload),
                        timeout=120
                    ) as r:
                        if r.status == 200:
                            print(f"✅ Step {step_id} обновлён")
                            return
                        else:
                            print(f"❌ Step {step_id}: ошибка {r.status}, {await r.text()}")

                return

            except Exception as e:
                print(f"Ошибка step_id={step_id}, попытка {attempt + 1}: {e}")
                if attempt < 2:
                    await asyncio.sleep(60)
                else:
                    print(f"❌ Превышено количество попыток для step_id={step_id}")
                    failed_steps.append(step_id)


# ==== Синхронное получение уроков и шагов ====
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
                        print(f"Ошибка unit_id={unit_id}, lesson_id={locals().get('lesson_id')}: {e}")
                        time.sleep(5)
                        continue
            except Exception as e:
                print(f"Ошибка section_id={section_id}: {e}")
                time.sleep(5)
                continue

    except Exception as e:
        print(f"Ошибка при получении курса {course_id}: {e}")

    return step_ids


# ==== Основной запуск ====
async def process_course(session: aiohttp.ClientSession, token: str, course_id: int, semaphore: asyncio.Semaphore, failed_steps: List[int]):
    step_ids = get_units_and_steps(token, course_id)  # теперь синхронно
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

# <p>&nbsp;</p>
# &lt;/&lt;li&gt;
