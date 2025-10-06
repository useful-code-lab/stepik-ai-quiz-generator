#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import requests
from typing import Dict, Any, List

COURSE_ID = 255627
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"

NEW_WEIGHT = 10  # баллы для всех шагов


# ==== OAuth ====
def get_access_token() -> str:
    resp = requests.post(
        f"{STEPIC_HOST}/oauth2/token/",
        data={"grant_type": "client_credentials"},
        auth=(CLIENT_ID, CLIENT_SECRET),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


# ==== Обновление баллов шага ====
def patch_step_source(token: str, step_source_id: int, weight: int = 10):
    payload = {
        "step-sources": [
            {
                "id": step_source_id,
                "weight": weight
            }
        ]
    }

    url = f"{STEPIC_HOST}/api/step-sources"
    response = requests.post(
        url,
        headers=mk_headers(token),
        data=json.dumps(payload),
        timeout=30
    )

    if response.status_code == 200:
        print(f"✅ Шаг-источник {step_source_id}: баллы обновлены на {weight}")
        return response.json()
    else:
        print(f"❌ Ошибка {response.status_code}: {response.text}")
        return None


def options_to_html(options):
    """
    Преобразует список вариантов (JSON) в HTML-список.

    options = [
        {"is_correct": True, "text": "Рыбное карри с рисом", "feedback": ""},
        ...
    ]

    Возвращает строку HTML.
    """
    html = '<ul>\n'
    for opt in options:
        text = opt.get("text", "")
        if opt.get("is_correct"):
            html += f'  <li><b>{text}</b></li>\n'
        else:
            html += f'  <li>{text}</li>\n'
    html += '</ul>'

    html = f' <details><summary>Показать ответ</summary>{html}</details>'

    return html


def pairs_to_html(options):
    """
    Преобразует список пар (JSON) в HTML-список с раскрывающимся блоком.

    options = [
        {"first": "Арамболь", "second": "Пляж для уединения и йоги"},
        ...
    ]

    Возвращает строку HTML для Stepik.
    """
    html = '<ul>\n'
    for opt in options:
        first = opt.get("first", "")
        second = opt.get("second", "")
        # Составляем строку "first — second"
        html += f'  <li><b>{first}</b> — {second}</li>\n'
    html += '</ul>'

    # Добавляем раскрывающийся блок с ответом
    html = f'\n\n<details><summary>Показать ответ</summary>{html}</details>'

    return html


def update_step_source(step_id, token, new_text=None):
    # 1️⃣ Получаем текущий step-source
    src_url = f"{STEPIC_HOST}/api/step-sources/{step_id}"
    r = requests.get(src_url, headers=mk_headers(token), timeout=30)
    data = r.json()["step-sources"][0]
    block = data["block"]
    payload = None

    if '<details><summary>Показать ответ</summary>' not in block["text"]:
        html_output = None

        if block["name"] == "choice":
            options = block["source"]["options"]
            json_string = json.dumps(options, ensure_ascii=False, indent=2)
            html_output = options_to_html(options)

        if block["name"] == "matching":
            pairs = block["source"]["pairs"]
            json_string = json.dumps(pairs, ensure_ascii=False, indent=2)
            html_output = pairs_to_html(pairs)

        if block["name"] == "sorting":
            options = block["source"]["options"]
            json_string = json.dumps(options, ensure_ascii=False, indent=2)
            html_output = options_to_html(options)

        if html_output is None:
            return

        print(f"=== Обновляем step-source {step_id} ===")
        block["text"] = block["text"] + html_output
        payload = {"step-source": {"block": block}}

    if payload is None:
        return
    else:
        data["block"] = block
        data["cost"] = 5

    payload = {"step-source": data}

    # 3️⃣ Отправляем PATCH
    patch_url = f"{STEPIC_HOST}/api/step-sources/{step_id}"
    resp = requests.put(patch_url, headers=mk_headers(token), data=json.dumps(payload), timeout=30)

    # 4️⃣ Проверка результата
    if resp.status_code == 200:
        print("✅ Успешно обновлено!")
    else:
        print(f"❌ Ошибка {resp.status_code}: {resp.text}")


# ==== Получение уроков и шагов курса ====
def get_units_and_lessons(token: str, course_id: int) -> List[Dict[str, Any]]:
    url = f"{STEPIC_HOST}/api/courses/{course_id}"
    r = requests.get(url, headers=mk_headers(token), timeout=30)
    r.raise_for_status()
    course = r.json()["courses"][0]

    section_ids = course.get("sections", [])
    if not section_ids:
        return []

    units_and_lessons = []

    for section_id in section_ids:
        url = f"{STEPIC_HOST}/api/sections/{section_id}"
        r = requests.get(url, headers=mk_headers(token), timeout=30)
        r.raise_for_status()
        section = r.json()["sections"][0]
        section_title = section.get("title", "")

        for unit_id in section.get("units", []):
            url = f"{STEPIC_HOST}/api/units/{unit_id}"
            r = requests.get(url, headers=mk_headers(token), timeout=30)
            r.raise_for_status()
            unit = r.json()["units"][0]

            lesson_id = unit["lesson"]

            url = f"{STEPIC_HOST}/api/lessons/{lesson_id}"
            r = requests.get(url, headers=mk_headers(token), timeout=30)
            r.raise_for_status()
            lesson = r.json()["lessons"][0]

            step_ids = lesson["steps"]

            for step_id in step_ids:
                update_step_source(step_id, token, new_text="Какой ответ правильный?")

    return units_and_lessons


# ==== Основной запуск ====
if __name__ == "__main__":
    token = get_access_token()
    lessons = get_units_and_lessons(token, COURSE_ID)

    for lesson in lessons:
        print(f"Обновляем урок: {lesson['lesson_title']} ({lesson['steps_count']} шагов)")
        for step_id in lesson["step_ids"]:
            patch_step_source(token, step_id, NEW_WEIGHT)
