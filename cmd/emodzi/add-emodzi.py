import json
import re

# Загружаем JSON
with open("course_data.json", "r", encoding="utf-8") as f:
    data = json.load(f)

# Эмодзи для модулей
module_emojis = [
    "📘", "🧩", "🧠", "⚡", "🔧", "📊", "🛡️", "🔄", "🗃️", "🌐", "🔁", "⏲️",
    "📈", "⚙️", "📋", "🌍", "☁️", "🧪", "🚨", "🏗️", "🎮", "🖴", "🕵️", "🏁", "🧠"
]

# Ключевые слова и эмодзи для уроков
lesson_emoji_map = {
    "что такое": "❓",
    "введение": "📘",
    "основы": "📚",
    "создание": "🛠️",
    "демон": "👻",
    "очереди": "📥",
    "race condition": "⚠️",
    "блокировки": "🔒",
    "многопроцесс": "🧠",
    "async": "⚡",
    "асинхрон": "⚡",
    "корутины": "🌀",
    "практика": "🧪",
    "квест": "🎯",
    "сравнение": "📊",
    "кейс": "💼",
    "gil": "🛡️",
    "синхронизация": "🔄",
    "структуры данных": "🗃️",
    "веб-запрос": "🌐",
    "реактив": "🔁",
    "таймер": "⏲️",
    "профилирование": "📈",
    "оптимизация": "⚙️",
    "кэширование": "🗂️",
    "распредел": "🌍",
    "gpu": "🎮",
    "ввод-вывод": "🖴",
    "отладка": "🕵️",
    "визуализ": "📊",
    "финальный проект": "🏁",
    "экзамен": "🧠",
    "рефлексия": "🔍",
    "сертификат": "📜",
    "мониторинг": "📡",
    "исключения": "🚫",
    "ошибк": "🚨",
    "pipeline": "🏗️"
}

# Обработка секций и уроков
for i, section in enumerate(data["sections"]):
    emoji = module_emojis[i % len(module_emojis)]

    # Удаляем "Модуль X. " из начала названия
    clean_title = re.sub(r"^Модуль\s*\d+\.\s*", "", section["section_title"]).strip()
    section["section_title"] = f"{emoji} {clean_title}"

    for lesson in section["lessons"]:
        title_lower = lesson["lesson_title"].lower()
        lesson_emoji = "📘"
        for keyword, emoji_lesson in lesson_emoji_map.items():
            if keyword in title_lower:
                lesson_emoji = emoji_lesson
                break
        lesson["lesson_title"] = f"{lesson_emoji} {lesson['lesson_title']}"

# Сохраняем результат
with open("course_cleaned_with_emojis.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print("✅ Названия модулей очищены и украшены эмодзи. Файл сохранён как 'course_cleaned_with_emojis.json'")
