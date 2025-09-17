#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import json
import re
import sys
from pathlib import Path
import time
import requests
from typing import Dict, Any, List
import os
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import requests
import json

TEMPLATE = "prompt_template.txt"

COURSE_ID = 253631

STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "JiICB7TWb4c0VkfDxf6NooJaAZ1p2wDxn7puHnPs"
CLIENT_SECRET = "mqjpR0NjckDjVG6cGxCILh18nkDHJb7D2WLWlTpqYKVoWfCDKZF53MhvlHk7YbgUi1U8L96bEPhMRepW6IiSyvs98qtn7aU7J1DW9LD9jZF0g1HZVI3rHcrphLN8Kkik"

total_text = ""

app = Flask(__name__)
app.secret_key = "super-secret-key"
current_steps = 0


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


def get_steps(token: str, lesson_id: int) -> list:
    url = f"{STEPIC_HOST}/api/steps?lesson={lesson_id}"
    r = requests.get(url, headers=mk_headers(token), timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("steps", [])  # список шагов



import re

def replace_mission_number(json_str: str, new_number: int) -> str:
    pattern = r'(<h3>Миссия )\d+(</h3>)'
    replaced = re.sub(pattern, lambda m: f"{m.group(1)}{new_number}{m.group(2)}", json_str)
    return replaced


# ==== Загрузка шагов из JSON ====
def load_steps_from_json(lesson_id: int, position: int, path: str, token: str) -> None:
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    block = cfg["block"]

    global current_steps

    payload = {"step-source": {
        "lesson": lesson_id,
        "block": block,
        "max_score": 5,
        "position": current_steps + 1
    }
    }

    payload["step-source"]["block"]["text"] = replace_mission_number(payload["step-source"]["block"]["text"], current_steps)

    global total_text
    if position > 999:
        payload["step-source"]["block"]["text"] = total_text

    resp = post_step_source(token, payload)
    new_id = resp.get("step-sources", [{}])[0].get("id")

    total_text = total_text + resp.get("step-sources", [{}])[0].get("block").get("text")
    current_steps = current_steps + 1
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


def merge_json_blocks(input_text: str) -> str:
    """
    Объединяет строки JSON, каждая из которых начинается с {"block":{,
    в одну строку, добавляя перенос строки между объектами.
    """
    lines = input_text.strip().split("\n")
    blocks = [line.strip() for line in lines if line.strip().startswith('{"block":{')]
    return "\n".join(blocks)


import re


def flatten_json_blocks(text: str) -> str:
    """
    Находит все JSON-объекты, начинающиеся с {"block" и заканчивающиеся на Z"},
    убирает все переносы строк и пробелы внутри них,
    и возвращает строку, где каждый JSON в отдельной строке.
    """
    # ищем все куски, которые начинаются с {"block и заканчиваются } (последняя скобка перед кавычкой Z может быть без пробелов)
    blocks = re.findall(r'(\{"block".*?\}Z"\})', text, flags=re.DOTALL)

    # собираем каждый в одну строку, убираем переносы и лишние пробелы
    flattened = []
    for b in blocks:
        one_line = re.sub(r'\s+', ' ', b).strip()
        flattened.append(one_line)

    return "\n".join(flattened)


import json
import re


def extract_json_lines(text: str):
    """
    Парсит текст, где каждая строка — отдельный JSON-объект.
    Возвращает список словарей Python.
    """
    lines = text.splitlines()
    result = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            result.append(obj)
        except json.JSONDecodeError as e:
            print(f"Ошибка парсинга: {e}")
            # иногда экранирование ломает, можно убрать обратные слэши
            try:
                obj = json.loads(line.replace(r'\:', ':').replace(r'\_', '_').replace(r'\[', '[').replace(r'\]', ']'))
                result.append(obj)
            except json.JSONDecodeError as e2:
                print(f"Второй попытка не удалась: {e2}")
                print(f"Проблемный кусок: {line[:100]}...")
    return result


def generate_questions(input_file):
    # Папка, где находятся файлы
    folder = "questions_split"

    # Имя файла, который нужно оставить
    file_to_keep = "1000.txt"

    # Создаём папку, если её нет
    out_dir = Path(folder)
    out_dir.mkdir(exist_ok=True)

    # Удаляем все файлы, кроме file_to_keep
    for filename in os.listdir(folder):
        file_path = os.path.join(folder, filename)
        if os.path.isfile(file_path) and filename != file_to_keep:
            os.remove(file_path)
            print(f"Удален файл: {filename}")

    # Читаем переданный файл
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()

    # Извлекаем JSON объекты
    # content = flatten_json_blocks(content)
    objs = extract_json_lines(content)
    print(f"Найдено {len(objs)} JSON-блоков")

    # Сохраняем каждый блок отдельно
    for idx, data in enumerate(objs, start=1):
        file_name = f"{idx}.json"
        with open(out_dir / file_name, "w", encoding="utf-8") as out_f:
            json.dump(data, out_f, ensure_ascii=False, indent=2)
        print(f"Сохранён файл: {file_name}")

    return out_dir


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

    for section_id in section_ids:
        # --- получаем секцию
        url = f"{STEPIC_HOST}/api/sections/{section_id}"
        r = requests.get(url, headers=mk_headers(token), timeout=30)
        r.raise_for_status()
        section = r.json()["sections"][0]
        section_title = section.get("title", "")  # название модуля берём отсюда

        for unit_id in section.get("units", []):
            # --- получаем unit (он сам по себе не имеет title)
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
                "module_title": section_title,  # берём название модуля из section
                "lesson_id": lesson_id,
                "lesson_title": lesson.get("title", ""),
                "lesson_description": lesson.get("description", ""),
                "steps_count": lesson.get("steps_count", 0),
            })

    return units_and_lessons


# Флаг, что сервер только что запустился
server_started = True


# Флаг, чтобы загрузка данных произошла только один раз
@app.before_request
def load_lessons_once():
    global server_started
    global token

    if server_started:
        # Удаляем данные из сессии при первом запросе после запуска
        session.pop("lessons_list", None)
        server_started = False  # Сбрасываем флаг, чтобы дальше не удалять

    if "lessons_list" not in session:
        token = get_access_token()
        session["lessons_list"] = get_units_and_lessons(token, COURSE_ID)


# ------------------- Шаг 1: Выбор урока -------------------
@app.route("/", methods=["GET", "POST"])
def select_lesson():
    lessons_list = session.get("lessons_list", [])
    current_step = 1
    if request.method == "POST":
        lesson_id = int(request.form["lesson_id"])
        session["current_lesson_id"] = lesson_id
        return redirect(url_for("lesson_form"))
    return render_template("index.html", lessons=lessons_list, step=current_step)


@app.route("/get_prompt")
def get_prompt():
    lesson_id = request.args.get("lesson_id")
    lessons_list = session.get("lessons_list", [])

    lesson = next((l for l in lessons_list if str(l['lesson_id']) == lesson_id), None)
    if lesson:
        # Здесь генерируем промпт динамически
        prompt = render_template(
            TEMPLATE,
            module_title=lesson['module_title'],
            topic=lesson['lesson_title'],
            topic_examples="«Для мам с детьми», «Для стартаперов», «Для новичков в фитнесе»",
        )
        return jsonify({"prompt": prompt})
    return jsonify({"prompt": ""})


@app.route("/save_lesson_text", methods=["POST"])
def save_lesson_text():
    lesson_id = request.args.get("lesson_id")
    text = request.get_data(as_text=True)  # получаем обычный текст
    global token
    global current_steps
    current_steps = len(get_steps(token, int(lesson_id)))
    if not lesson_id or not text:
        return jsonify({"success": False, "error": "Нет lesson_id или текста"}), 400

    try:
        # Папка для сохранения
        output_dir = "output_dir"
        os.makedirs(output_dir, exist_ok=True)

        # Сохраняем текст в файл
        file_path = os.path.join(output_dir, f"{lesson_id}_text.txt")
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(text)

        # Здесь вызываем функцию обработки текста (например, генерацию квестов)
        generate_questions(file_path)  # передаем путь к файлу с текстом

        output_dir = "questions_split"
        files_sorted = sorted(os.listdir(output_dir), key=lambda x: int(re.search(r'(\d+)', x).group(1)))

        # Перебираем с индексом
        for key, file in enumerate(files_sorted, start=1):
            try:
                if file.endswith(".json"):
                    pass
                    load_steps_from_json(int(lesson_id), key, os.path.join(output_dir, file), token)
            except Exception as e:
                pass
        # session["lessons_list"] = get_units_and_lessons(token, COURSE_ID)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ------------------- Запуск -------------------
if __name__ == "__main__":
    app.run(debug=True)


def generate_questions(input_file):
    # Пример функции обработки текста
    print(f"Обрабатываем файл: {input_file}")
    # Тут можно вставить вашу логику для генерации шагов/квестов


# ==== Основной запуск ====
if __name__ == "__main__":
    # ID урока нужно знать заранее (например, 123456)
    LESSON_ID = 1937372
    output_dir = Path("questions_split")

    sys.exit()

    # generate_questions()

    # 2. Получение токена
    token = get_access_token()

    ####################
    course_id = 252535  # <-- сюда вставь id курса

    # unit_ids = get_units_from_course(token, course_id)
    # print("Units:", unit_ids)

    data = get_units_and_lessons(token, course_id)
    for item in data:
        print(f"Unit {item['unit_id']} → Lesson {item['lesson_id']} | {item['lesson_title']}")
    ###################

    generate_questions()

    files_sorted = sorted(os.listdir(output_dir), key=lambda x: int(re.search(r'(\d+)', x).group(1)))

    # Перебираем с индексом
    for key, file in enumerate(files_sorted, start=1):
        try:
            if file.endswith(".json"):
                pass
                load_steps_from_json(LESSON_ID, key, os.path.join(output_dir, file), token)
        except Exception as e:
            pass
        # load_steps_from_json(LESSON_ID, 11, os.path.join(output_dir, "questions_split/1000.json"), token)
