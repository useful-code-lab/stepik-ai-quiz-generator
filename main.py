#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Dict, Any, List

import aiohttp
from flask import Flask, render_template, request, redirect, url_for, session, jsonify

# ==== Настройки ====
TEMPLATE = "prompt_template_typescript.txt"
COURSE_ID = 253972
STEPIC_HOST = "https://stepik.org"
CLIENT_ID = "JiICB7TWb4c0VkfDxf6NooJaAZ1p2wDxn7puHnPs"
CLIENT_SECRET = "mqjpR0NjckDjVG6cGxCILh18nkDHJb7D2WLWlTpqYKVoWfCDKZF53MhvlHk7YbgUi1U8L96bEPhMRepW6IiSyvs98qtn7aU7J1DW9LD9jZF0g1HZVI3rHcrphLN8Kkik"

app = Flask(__name__)
app.secret_key = "super-secret-key"

# ==== Глобальные кэши ====
LESSONS_CACHE: List[Dict[str, Any]] = []
ACCESS_TOKEN: str = ""
CACHE_LOADED: bool = False

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

async def post_step_source(session_http: aiohttp.ClientSession, token: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    headers = mk_headers(token)
    async with session_http.post(f"{STEPIC_HOST}/api/step-sources", headers=headers, json=payload) as r:
        if r.status == 429:
            await asyncio.sleep(1.5)
            async with session_http.post(f"{STEPIC_HOST}/api/step-sources", headers=headers, json=payload) as r2:
                r2.raise_for_status()
                return await r2.json()
        r.raise_for_status()
        return await r.json()

def replace_mission_number(text: str, new_number: int) -> str:
    return re.sub(r'(<h3>Миссия )\d+(</h3>)', lambda m: f"{m.group(1)}{new_number}{m.group(2)}", text)

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

def generate_questions_from_file(input_file: str, output_dir: Path) -> List[Path]:
    with open(input_file, "r", encoding="utf-8") as f:
        content = f.read()
    objs = extract_json_lines(content)
    output_dir.mkdir(exist_ok=True)
    saved_files = []
    for idx, obj in enumerate(objs, start=1):
        file_path = output_dir / f"{idx}.json"
        with open(file_path, "w", encoding="utf-8") as f_out:
            json.dump(obj, f_out, ensure_ascii=False, indent=2)
        saved_files.append(file_path)
    return saved_files

# ==== Загрузка кэша при первом запросе ====
@app.before_request
def load_cache_once():
    global CACHE_LOADED, ACCESS_TOKEN, LESSONS_CACHE
    if not CACHE_LOADED:
        print("Загрузка токена и уроков...")
        ACCESS_TOKEN = asyncio.run(get_access_token())
        LESSONS_CACHE = asyncio.run(get_units_and_lessons(ACCESS_TOKEN, COURSE_ID))
        CACHE_LOADED = True
        print(f"Кэш уроков загружен: {len(LESSONS_CACHE)} уроков")

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

@app.route("/save_lesson_text", methods=["POST"])
def save_lesson_text():
    lesson_id = request.args.get("lesson_id")
    text = request.get_data(as_text=True)
    token = ACCESS_TOKEN
    if not lesson_id or not text:
        return jsonify({"success": False, "error": "Нет lesson_id или текста"}), 400

    output_dir = "output_dir"

    # Сохраняем текст в файл
    file_path = os.path.join(output_dir, f"{lesson_id}_text.txt")
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(text)

    output_dir = Path("questions_split")
    saved_files = generate_questions_from_file(file_path, output_dir)

    async def post_all_steps():
        async with aiohttp.ClientSession() as session_http:
            for idx, file_path in enumerate(saved_files, start=1):
                with open(file_path, "r", encoding="utf-8") as f:
                    payload = {"step-source": {"lesson": int(lesson_id), "block": json.load(f)["block"], "max_score": 5, "position": idx}}
                    payload["step-source"]["block"]["text"] = replace_mission_number(payload["step-source"]["block"]["text"], idx)
                    await post_step_source(session_http, token, payload)

    asyncio.run(post_all_steps())

    return jsonify({"success": True})

if __name__ == "__main__":
    app.run(debug=True)
