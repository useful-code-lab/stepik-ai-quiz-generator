#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
import re
import shutil
from pathlib import Path
from typing import Dict, Any, List

import aiohttp
import requests
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# ==== Настройки ====
TEMPLATE = "prompt_template_conflict.txt"
COURSE_ID = 254191
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "hXxRvtSiQQS55BXZBAXkx0D5UZZHu1mcn0s3cbNn"
CLIENT_SECRET = "waJh174Kr7rx4GlmYC4u8hCpkpoAE3Fh729mfjTygOkCMMY2eQDLBG8r0vwSsKcnUWOOJIzoXo3wlWIYZXFfXvOsucdQSKJubE8WuTNsv66YCUnKYY6VUXMzuh4xgtEd"

app = Flask(__name__)
app.secret_key = "super-secret-key"

# ==== Глобальные кэши ====
LESSONS_CACHE: List[Dict[str, Any]] = []
ACCESS_TOKEN: str = ""
CACHE_LOADED: bool = False
CACHE_FILE = "lessons_cache.json"


# ==== Вспомогательные функции ====
async def get_access_token() -> str:
    async with aiohttp.ClientSession() as session_http:
        async with session_http.post(
                f"{STEPIC_HOST}/oauth2/token/",
                data={"grant_type": "client_credentials"},
                auth=aiohttp.BasicAuth(CLIENT_ID, CLIENT_SECRET)
        ) as resp:
            resp.raise_for_status()
            data = await resp.json()
            return data["access_token"]


def mk_headers(token: str) -> Dict[str, str]:
    return {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}


async def fetch_json(session_http: aiohttp.ClientSession, url: str, headers: Dict[str, str]) -> Dict[str, Any]:
    async with session_http.get(url, headers=headers) as r:
        r.raise_for_status()
        return await r.json()


async def get_units_and_lessons(token: str, course_id: int) -> List[Dict[str, Any]]:
    headers = mk_headers(token)
    async with aiohttp.ClientSession() as session_http:
        course_data = await fetch_json(session_http, f"{STEPIC_HOST}/api/courses/{course_id}", headers)
        course = course_data["courses"][0]
        section_ids = course.get("sections", [])
        units_and_lessons = []

        for section_id in section_ids:
            section_data = await fetch_json(session_http, f"{STEPIC_HOST}/api/sections/{section_id}", headers)
            section = section_data["sections"][0]
            section_title = section.get("title", "")

            for unit_id in section.get("units", []):
                unit_data = await fetch_json(session_http, f"{STEPIC_HOST}/api/units/{unit_id}", headers)
                unit = unit_data["units"][0]
                lesson_id = unit["lesson"]

                lesson_data = await fetch_json(session_http, f"{STEPIC_HOST}/api/lessons/{lesson_id}", headers)
                lesson = lesson_data["lessons"][0]

                units_and_lessons.append({
                    "unit_id": unit_id,
                    "module_title": section_title,
                    "lesson_id": lesson_id,
                    "lesson_title": lesson.get("title", ""),
                    "lesson_description": lesson.get("description", ""),
                    "steps_count": lesson.get("steps_count", 0),
                })
        return units_and_lessons


import json
import aiohttp
from typing import Dict, Any


async def post_step_source(session_http: aiohttp.ClientSession, token: str, payload: Dict[str, Any], file_name: str) -> \
        Dict[str, Any] | None:
    headers = mk_headers(token)
    url = f"{STEPIC_HOST}/api/step-sources"
    global current_steps
    try:
        async with session_http.post(url, headers=headers, json=payload) as r:
            if r.status == 429:
                # Повтор через 1.5 секунды
                await asyncio.sleep(1.5)
                async with session_http.post(url, headers=headers, json=payload) as r2:
                    text = await r2.text()
                    if r2.status != 200:
                        print("\n" + "-" * 60)
                        print(f"[WARNING] Ошибка при повторной попытке загрузки файла: {file_name}")
                        print(f"Статус: {r2.status}, ответ: {text}")
                        print("-" * 60 + "\n")
                        return None
                    return await r2.json()

            text = await r.text()
            if r.status != 201:
                print("\n" + "-" * 60)
                print(f"[WARNING] Ошибка при загрузке файла: {file_name}")
                print(f"Статус: {r.status}, ответ: {text}")
                print(json.dumps(payload, ensure_ascii=False, indent=2))
                print("-" * 60 + "\n")
                return None

            current_steps = current_steps + 1

            return await r.json()

    except aiohttp.ClientResponseError as e:
        print("\n" + "-" * 60)
        print(f"[WARNING] ClientResponseError для файла {file_name}: {e.status}, сообщение: {e.message}")
        print("-" * 60 + "\n")
        return None
    except Exception as e:
        print("\n" + "-" * 60)
        print(f"[WARNING] Неожиданная ошибка при загрузке файла {file_name}: {e}")
        print("-" * 60 + "\n")
        return None


def replace_mission_number(text: str, new_number: int) -> str:
    return re.sub(r'(<h3>Миссия )\d+(</h3>)', lambda m: f"{m.group(1)}{new_number}{m.group(2)}", text)


import json

import json
import re


def extract_json_blocks(text: str):
    """
    Из текста извлекает все блоки {"block": ...} и парсит их как JSON-массив.
    Если не удаётся, пробует построчно.
    """
    text = text.strip()
    if not text:
        return []

    result = []

    # 1. Попытка найти все блоки {"block": ...} с помощью регулярки
    # Берем '{' + любые символы + '"block"' + любые символы + '}' с жадным захватом до закрывающей скобки
    pattern = r'(\{"block":.*?Z"\})'
    matches = re.findall(pattern, text, flags=re.DOTALL)

    if matches:
        # Собираем все найденные блоки в массив JSON
        json_array_str = '[' + ','.join(matches) + ']'
        try:
            return json.loads(json_array_str)
        except json.JSONDecodeError as e:
            print(f"Ошибка при парсинге массива блоков: {e}")

    # 2. Если не получилось — fallback на построчный разбор (твоя старая логика)
    lines = text.splitlines()
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            result.append(obj)
        except json.JSONDecodeError as e:
            # попытка с заменой экранирования
            try:
                clean_line = (line
                              .replace(r'\:', ':')
                              .replace(r'\_', '_')
                              .replace(r'\[', '[')
                              .replace(r'\]', ']')
                              .replace(r'\"', '"'))
                obj = json.loads(clean_line)
                result.append(obj)
            except json.JSONDecodeError:
                continue
    return result


def generate_questions_from_file(input_file: str, output_dir: Path) -> List[Path]:
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()
    objs = extract_json_blocks(content)
    shutil.rmtree(output_dir, ignore_errors=True)
    output_dir.mkdir(exist_ok=True)
    saved_files = []
    for idx, obj in enumerate(objs, start=1):
        file_path = output_dir / f"{idx}.json"
        with open(file_path, "w", encoding="utf-8") as f_out:
            json.dump(obj, f_out, ensure_ascii=False, indent=2)
        saved_files.append(file_path)
    return saved_files


@app.before_request
def load_cache_once():
    global CACHE_LOADED, ACCESS_TOKEN, LESSONS_CACHE
    ACCESS_TOKEN = asyncio.run(get_access_token())
    if not CACHE_LOADED:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                LESSONS_CACHE = json.load(f)
            CACHE_LOADED = True
            print(f"Кэш загружен из файла: {len(LESSONS_CACHE)} уроков")
        else:
            LESSONS_CACHE = asyncio.run(get_units_and_lessons(ACCESS_TOKEN, COURSE_ID))
            with open(CACHE_FILE, "w", encoding="utf-8") as f:
                json.dump(LESSONS_CACHE, f, ensure_ascii=False, indent=2)
            CACHE_LOADED = True
            print(f"Кэш загружен и сохранён: {len(LESSONS_CACHE)} уроков")


# ==== Flask routes ====
@app.route("/", methods=["GET", "POST"])
def select_lesson():
    lessons_list = LESSONS_CACHE
    if request.method == "POST":
        lesson_id = int(request.form["lesson_id"])
        session["current_lesson_id"] = lesson_id
        return redirect(url_for("lesson_form"))
    return render_template("index.html", lessons=lessons_list)


@app.route("/get_prompt")
def get_prompt():
    lesson_id = request.args.get("lesson_id")
    lesson = next((l for l in LESSONS_CACHE if str(l['lesson_id']) == lesson_id), None)
    if lesson:
        prompt = render_template(
            TEMPLATE,
            module_title=lesson['module_title'],
            topic=lesson['lesson_title'],
            topic_examples="«Для мам с детьми», «Для стартаперов», «Для новичков в фитнесе»",
        )
        return jsonify({"prompt": prompt})
    return jsonify({"prompt": ""})


# Полные шаблоны блоков для Stepik (без пустых id и time)
BLOCK_TEMPLATES = {
    "choice": {
        "block": {
            "name": "choice",
            "text": "",
            "video": None,
            "options": {"is_multiple_choice": False},
            "is_deprecated": False,
            "source": {
                "is_multiple_choice": False,
                "is_always_correct": False,
                "sample_size": 4,
                "preserve_order": False,
                "is_html_enabled": True,
                "is_options_feedback": False,
                "options": []
            }
        },
        "has_review": False,
    },
    "sorting": {
        "block": {
            "name": "sorting",
            "text": "",
            "video": None,
            "options": {},
            "is_deprecated": False,
            "source": {"is_html_enabled": True, "options": []}
        },
        "has_review": False,
    },
    "matching": {
        "block": {
            "name": "matching",
            "text": "",
            "video": None,
            "options": {},
            "is_deprecated": False,
            "source": {"preserve_firsts_order": True, "is_html_enabled": True, "pairs": []}
        },
        "has_review": False,
    }
}


def fill_template(block_data):
    """
    Заполняем шаблон блоком, заменяя текст, options/pairs и position,
    сохраняя остальные данные из шаблона, и подставляя данные из block_data, если они есть.
    """
    block_type = block_data["name"]
    template = json.loads(json.dumps(BLOCK_TEMPLATES[block_type]))  # создаём глубокую копию

    # Основной текст
    template["block"]["text"] = block_data.get("text", template["block"]["text"])
    template["block"]["video"] = block_data.get("video", template["block"]["video"])
    template["block"]["is_deprecated"] = block_data.get("is_deprecated", template["block"]["is_deprecated"])
    template["block"]["options"] = block_data.get("options", template["block"].get("options", {}))

    # Source: обновляем только существующие поля, если они есть
    if "source" in block_data:
        for key, value in block_data["source"].items():
            template["block"]["source"][key] = value

    # Пары для matching
    if "pairs" in block_data.get("source", {}):
        template["block"]["source"]["pairs"] = block_data["source"]["pairs"]

    # Опции для choice/sorting
    if "options" in block_data.get("source", {}):
        template["block"]["source"]["options"] = block_data["source"]["options"]

    if block_type == "choice":
        for opt in block_data["source"]["options"]:
            if "feedback" not in opt:
                opt["feedback"] = ""

    # Дополнительно
    template["has_review"] = block_data.get("has_review", template.get("has_review", False))

    if block_type == "sorting":
        options_list = block_data["source"].get("options", [])
        for i, opt in enumerate(options_list):
            if isinstance(opt, str):
                options_list[i] = {"text": opt}  # преобразуем только строки
        template["block"]["source"]["options"] = options_list

    return template


def get_steps(token: str, lesson_id: int) -> list:
    url = f"{STEPIC_HOST}/api/steps?lesson={lesson_id}"
    r = requests.get(url, headers=mk_headers(token), timeout=60)
    r.raise_for_status()
    data = r.json()
    return data.get("steps", [])  # список шагов


current_steps = 0


@app.route("/save_lesson_text", methods=["POST"])
def save_lesson_text():
    lesson_id = request.args.get("lesson_id")
    text = request.get_data(as_text=True)
    token = ACCESS_TOKEN
    global current_steps

    steps = get_steps(token, int(lesson_id))
    current_steps = len(steps) if steps[0]["block"]["name"] == "text" else len(steps) + 1

    if not lesson_id or not text:
        return jsonify({"success": False, "error": "Нет lesson_id или текста"}), 400

    output_dir = "output_dir"

    # Сохраняем текст в файл
    file_path = os.path.join(output_dir, f"{lesson_id}_text.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    output_dir = Path("questions_split")
    saved_files = generate_questions_from_file(file_path, output_dir)

    async def post_all_steps(saved_files, lesson_id, token):
        global current_steps
        async with aiohttp.ClientSession() as session_http:
            for idx, file_path in enumerate(saved_files, start=1):
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        step_json = json.load(f)

                    block_data = step_json.get("block", {})
                    full_payload = fill_template(block_data)

                    # Проверка обязательных данных
                    block_type = full_payload["block"]["name"]
                    block_text = full_payload["block"].get("text", "").strip()

                    if not block_text:
                        print(f"[WARNING] Пропущен шаг {current_steps}: отсутствует текст для блока '{block_type}'")
                        continue  # пропускаем

                    if block_type in ("choice", "sorting"):
                        options = full_payload["block"]["source"].get("options", [])
                        if not options or not isinstance(options, list):
                            print(f"[WARNING] Пропущен шаг {current_steps}: отсутствуют опции для блока '{block_type}'")
                            continue  # пропускаем

                    if block_type == "matching":
                        pairs = full_payload["block"]["source"].get("pairs", [])
                        if not pairs or not isinstance(pairs, list):
                            print(f"[WARNING] Пропущен шаг {current_steps}: отсутствуют пары для блока 'matching'")
                            continue  # пропускаем

                    if current_steps > 19:
                        continue  # лимит на 20 шагов

                    # Заменяем номер миссии в тексте, если нужно
                    full_payload["block"]["text"] = replace_mission_number(full_payload["block"]["text"], current_steps)

                    payload = {
                        "step-source": {
                            "lesson": int(lesson_id),
                            **full_payload,
                            "max_score": 5,
                            "position": current_steps + 1
                        }
                    }


                    await post_step_source(session_http, token, payload, file_path)

                except Exception as e:
                    # Логируем ошибку и продолжаем цикл
                    print(f"[ERROR] Ошибка при обработке файла '{file_path}' (шаг {idx}): {e}")
                    continue

    asyncio.run(post_all_steps(saved_files, lesson_id, token))

    return jsonify({"success": True})


if __name__ == "__main__":
    app.run(debug=True)
