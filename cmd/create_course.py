import json
import requests
import sys
import time

# === НАСТРОЙКИ ===
STEPIC_CLIENT_ID = "rEQVrrQXjA0kUmV0OuisJeg2yYZFi90aqgWXIKAp"
STEPIC_CLIENT_SECRET = "I10ib8UG84JkbcTCB8yuX6lv1oWYNbBCu6jWgVHw4tpKP59ObwKJD8wU2ldGWYLdRGscZpZfcQ5KhvhXqtSYqVLJedDZUnLMghYOwxKVPmVu6demCfdlgjPkxYM0Qc0T"
COURSE_ID = 260699  # <-- ID курса на Stepik
JSON_FILE = "course.json"
API_BASE = "https://stepik.org/api"


# === АВТОРИЗАЦИЯ ===
def get_token(client_id, client_secret):
    resp = requests.post(
        "https://stepik.org/oauth2/token/",
        data={
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_secret": client_secret
        }
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# === ВСПОМОГАТЕЛЬНАЯ ФУНКЦИЯ ДЛЯ POST ===
def stepik_post(endpoint, data, token, retries=3):
    headers = {"Authorization": f"Bearer {token}"}
    for attempt in range(retries):
        resp = requests.post(f"{API_BASE}/{endpoint}", json=data, headers=headers)
        if resp.ok:
            return resp.json()
        else:
            print(f"⚠️ Ошибка при POST {endpoint}: {resp.status_code} {resp.text}")
            time.sleep(3)
    resp.raise_for_status()


# === СОЗДАНИЕ МОДУЛЯ (С УЧЁТОМ ПОРЯДКА) ===
def create_module(course_id, module_data, token, position):
    payload = {
        "section": {
            "course": course_id,
            "title": module_data["title"],
            "description": module_data.get("description", ""),
            "position": position
        }
    }
    resp = stepik_post("sections", payload, token)
    return resp["sections"][0]["id"]


# === СОЗДАНИЕ УРОКА (С УЧЁТОМ ПОРЯДКА) ===
def create_lesson(section_id, lesson_title, token, position):
    # создаём урок
    payload = {
        "lesson": {
            "title": lesson_title,
            "is_public": False
        }
    }
    resp = stepik_post("lessons", payload, token)
    lesson_id = resp["lessons"][0]["id"]

    # создаём unit (привязка к секции)
    unit_data = {
        "unit": {
            "section": section_id,
            "lesson": lesson_id,
            "position": position
        }
    }
    stepik_post("units", unit_data, token)
    return lesson_id


# === ОСНОВНОЙ СЦЕНАРИЙ ===
def main():
    with open(JSON_FILE, "r", encoding="utf-8") as f:
        modules = json.load(f)

    token = get_token(STEPIC_CLIENT_ID, STEPIC_CLIENT_SECRET)
    print("✅ Авторизация успешна!")

    print(f"📘 Добавляем модули и уроки в курс ID={COURSE_ID}")

    for module_index, module in enumerate(modules, start=1):
        section_id = create_module(COURSE_ID, module, token, module_index)
        print(f"📂 Модуль {module_index} создан: {module['title']} (ID={section_id})")

        for lesson_index, lesson_title in enumerate(module.get("lessons", []), start=1):
            lesson_id = create_lesson(section_id, lesson_title, token, lesson_index)
            print(f"   🧩 Урок {lesson_index}: {lesson_title} (ID={lesson_id})")

    print("✅ Все модули и уроки успешно созданы по порядку!")


if __name__ == "__main__":
    if len(sys.argv) > 2:
        COURSE_ID = int(sys.argv[1])
        JSON_FILE = sys.argv[2]
    elif len(sys.argv) > 1:
        JSON_FILE = sys.argv[1]

    main()
