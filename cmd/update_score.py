#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import time
import requests
from typing import Dict, Any, List

COURSE_ID = 251814
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "JiICB7TWb4c0VkfDxf6NooJaAZ1p2wDxn7puHnPs"
CLIENT_SECRET = "mqjpR0NjckDjVG6cGxCILh18nkDHJb7D2WLWlTpqYKVoWfCDKZF53MhvlHk7YbgUi1U8L96bEPhMRepW6IiSyvs98qtn7aU7J1DW9LD9jZF0g1HZVI3rHcrphLN8Kkik"

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
            steps = r.json().get("steps", [])

            step_ids = [step["id"] for step in steps]

            units_and_lessons.append({
                "unit_id": unit_id,
                "module_title": section_title,
                "lesson_id": lesson_id,
                "lesson_title": lesson.get("title", ""),
                "lesson_description": lesson.get("description", ""),
                "steps_count": lesson.get("steps_count", 0),
                "step_ids": step_ids
            })

    return units_and_lessons

# ==== Основной запуск ====
if __name__ == "__main__":
    token = get_access_token()
    lessons = get_units_and_lessons(token, COURSE_ID)

    for lesson in lessons:
        print(f"Обновляем урок: {lesson['lesson_title']} ({lesson['steps_count']} шагов)")
        for step_id in lesson["step_ids"]:
            patch_step_source(token, step_id, NEW_WEIGHT)
