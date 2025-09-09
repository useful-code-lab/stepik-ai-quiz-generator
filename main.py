#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
from pathlib import Path
import time
import requests
from typing import Dict, Any, List
import os
from flask import Flask, render_template, request, redirect, url_for, session
import requests
import json

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "JiICB7TWb4c0VkfDxf6NooJaAZ1p2wDxn7puHnPs"
CLIENT_SECRET = "mqjpR0NjckDjVG6cGxCILh18nkDHJb7D2WLWlTpqYKVoWfCDKZF53MhvlHk7YbgUi1U8L96bEPhMRepW6IiSyvs98qtn7aU7J1DW9LD9jZF0g1HZVI3rHcrphLN8Kkik"

total_text = ""

app = Flask(__name__)
app.secret_key = "super-secret-key"

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


# ==== Запрос в Stepik ====
def post_step_source(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    print("Отправляем payload:", json.dumps(payload, ensure_ascii=False, indent=2))

    url = f"{STEPIC_HOST}/api/step-sources"
    r = requests.post(url, headers=mk_headers(token), data=json.dumps(payload), timeout=60)
    if r.status_code == 429:
        time.sleep(1.5)
        r = requests.post(url, headers=mk_headers(token), data=json.dumps(payload), timeout=60)
    print(r.text)
    r.raise_for_status()

    return r.json()


# ==== Загрузка шагов из JSON ====
def load_steps_from_json(lesson_id: int, position: int, path: str, token: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    block = cfg["block"]

    payload = {"step-source": {
        "lesson": lesson_id,
        "block": block
    }
    }
    global total_text
    if position > 10:
        payload["step-source"]["block"]["text"] = total_text

    resp = post_step_source(token, payload)
    new_id = resp.get("step-sources", [{}])[0].get("id")

    'text'
    total_text = total_text + resp.get("step-sources", [{}])[0].get("block").get("text")

    print(f"✓ [{path}] Создан шаг {position + 1}, id={new_id}")


import json
from pathlib import Path


def extract_json_objects(text: str):
    """Идём по строке, находим '{', пробуем raw_decode с этой позиции.
    Если получилось — забираем объект и прыгаем на конец; если нет — сдвигаемся на запрос.txt символ.
    """
    dec = json.JSONDecoder()
    i = 0
    n = len(text)
    objects = []
    while i < n:
        j = text.find('{', i)
        if j == -1:
            break
        try:
            obj, end = dec.raw_decode(text, j)  # парсит полноценно со всеми вложенными скобками/строками
            objects.append(obj)
            i = end
        except json.JSONDecodeError:
            i = j + 1
    return objects


def generate_questions():
    # Папка, где находятся файлы
    folder = "questions_split"

    # Имя файла, который нужно оставить
    file_to_keep = "1000.txt"

    # Перебираем все файлы в папке
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        # Проверяем, что это файл и он не тот, который нужно оставить
        if os.path.isfile(file_path) and filename != file_to_keep:
            os.remove(file_path)
            print(f"Удален файл: {filename}")

    input_file = "questions_all.json"
    out_dir = Path(folder)
    out_dir.mkdir(exist_ok=True)

    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    objs = extract_json_objects(content)
    print(f"Найдено {len(objs)} JSON-блоков")

    for idx, data in enumerate(objs, start=1):
        file_name = f"{idx}.json"
        with open(out_dir / file_name, "w", encoding="utf-8") as out_f:
            json.dump(data, out_f, ensure_ascii=False, indent=2)
        print(f"Сохранён файл: {file_name}")

    # если дальше используете out_dir:
    return out_dir



def get_units_from_course(token: str, course_id: int) -> List[int]:
    """
    Получает список всех unit_id для заданного курса.
    """
    # 1. Берём сам курс
    url = f"{STEPIC_HOST}/api/courses/{course_id}"
    r = requests.get(url, headers=mk_headers(token), timeout=30)
    r.raise_for_status()
    course = r.json()["courses"][0]

    section_ids = course.get("sections", [])
    if not section_ids:
        return []

    # 2. Собираем все unit_id из каждой секции
    units = []
    for sid in section_ids:
        url = f"{STEPIC_HOST}/api/sections/{sid}"
        r = requests.get(url, headers=mk_headers(token), timeout=30)
        r.raise_for_status()
        section = r.json()["sections"][0]  # здесь всегда один объект
        units.extend(section.get("units", []))

    return units



# ==== Запрос в Stepik (пример POST) ====
def post_step_source(token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    print("Отправляем payload:", json.dumps(payload, ensure_ascii=False, indent=2))
    url = f"{STEPIC_HOST}/api/step-sources"
    r = requests.post(url, headers=mk_headers(token), data=json.dumps(payload), timeout=60)
    if r.status_code == 429:
        time.sleep(1.5)
        r = requests.post(url, headers=mk_headers(token), data=json.dumps(payload), timeout=60)
    print(r.text)
    r.raise_for_status()
    return r.json()


def get_units_and_lessons(token: str, course_id: int) -> List[Dict[str, Any]]:
    """
    Возвращает список unit_id вместе с уроками.
    [
      {
        "unit_id": int,
        "lesson_id": int,
        "lesson_title": str,
        "lesson_description": str
      },
      ...
    ]
    """
    # 1. Берём сам курс
    url = f"{STEPIC_HOST}/api/courses/{course_id}"
    r = requests.get(url, headers=mk_headers(token), timeout=30)
    r.raise_for_status()
    course = r.json()["courses"][0]

    section_ids = course.get("sections", [])
    if not section_ids:
        return []

    # 2. Обходим все секции и сразу вытягиваем уроки
    units_and_lessons = []
    for sid in section_ids:
        url = f"{STEPIC_HOST}/api/sections/{sid}"
        r = requests.get(url, headers=mk_headers(token), timeout=30)
        r.raise_for_status()
        section = r.json()["sections"][0]

        for unit_id in section.get("units", []):
            # --- получаем unit
            url = f"{STEPIC_HOST}/api/units/{unit_id}"
            r = requests.get(url, headers=mk_headers(token), timeout=30)
            r.raise_for_status()
            unit = r.json()["units"][0]

            lesson_id = unit["lesson"]

            # --- получаем lesson
            url = f"{STEPIC_HOST}/api/lessons/{lesson_id}"
            r = requests.get(url, headers=mk_headers(token), timeout=30)
            r.raise_for_status()
            lesson = r.json()["lessons"][0]

            units_and_lessons.append({
                "unit_id": unit_id,
                "lesson_id": lesson_id,
                "lesson_title": lesson.get("title", ""),
                "lesson_description": lesson.get("description", "")
            })

    return units_and_lessons

# ==== Основной запуск ====
if __name__ == "__main__":
    # ID урока нужно знать заранее (например, 123456)
    LESSON_ID = 1937372
    output_dir = Path("questions_split")



    #generate_questions()

    # 2. Получение токена
    token = get_access_token()

    ####################
    course_id = 252535  # <-- сюда вставь id курса

    #unit_ids = get_units_from_course(token, course_id)
   # print("Units:", unit_ids)

    data = get_units_and_lessons(token, course_id)
    for item in data:
        print(f"Unit {item['unit_id']} → Lesson {item['lesson_id']} | {item['lesson_title']}")
    ###################

    files_sorted = sorted(os.listdir(output_dir), key=lambda x: int(re.search(r'(\d+)', x).group(1)))

    # Перебираем с индексом
    for key, file in enumerate(files_sorted, start=1):
        try:
            if file.endswith(".json"):
                pass
                #load_steps_from_json(LESSON_ID, key, os.path.join(output_dir, file), token)
        except Exception as e:
            pass
        # load_steps_from_json(LESSON_ID, 11, os.path.join(output_dir, "questions_split/1000.json"), token)
