import os
import json
import re
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import base64

# ============== Настройки ==============
BASE_DIR = "courses"  # Путь к директории с курсами
FB2_DIR = "fb2s"  # Путь для сохранения сгенерированных FB2 файлов
ALLOWED_TYPES = {"choice", "matching", "sorting"}  # Типы шагов
STOP_AFTER_FIRST_COURSE = False  # Остановить после первого курса

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================

def add_cover_to_fb2(fb2_root, course_name):
    """Добавление текстовой обложки с названием курса в FB2"""
    title_info = fb2_root.find("title-info")
    coverpage = ET.SubElement(title_info, "coverpage")
    cover_text = ET.SubElement(coverpage, "p")
    cover_text.text = f"📘 {course_name}"  # Эмодзи обложки

def load_json(path):
    """Загружаем JSON файл с обработкой ошибок."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Ошибка при загрузке JSON файла: {path}. Ошибка: {e}")
        return {}

def simplify_name(name: str) -> str:
    """Удаляем ведущий 0 из названия модуля/урока."""
    match = re.match(r"0*(\d+)(.*)", name)
    if match:
        return f"{int(match.group(1))}{match.group(2)}".strip()
    return name

def image_to_base64(image_path):
    """Конвертирует изображение в base64."""
    with open(image_path, "rb") as img_file:
        return base64.b64encode(img_file.read()).decode('utf-8')

def parse_step_text(html_text: str, block_source=None) -> str:
    """Обработка текста в формате HTML для вставки в FB2."""
    soup = BeautifulSoup(html_text or "", "html.parser")

    # Убираем заголовки h2/h3
    for tag in soup.find_all(["h2", "h3"]):
        tag.decompose()

    # Убираем лишние <br>
    for br in soup.find_all("br"):
        br.unwrap()

    # Убираем теги <details> и <summary> (не поддерживаются в FB2)
    for details in soup.find_all("details"):
        details.decompose()

    # Обработка подсказок <em>, преобразуем в блок <blockquote>
    for em in soup.find_all("em"):
        text = em.get_text(" ", strip=True)
        if "подсказка" in text.lower():
            parent_p = em.find_parent("p")
            if parent_p:
                block = soup.new_tag("blockquote")
                block['class'] = ['hint']
                header = soup.new_tag("p")
                header.string = "💡 Подсказка:"  # Эмодзи для подсказки
                block.append(header)
                hint_text = parent_p.get_text(" ", strip=True).replace("Подсказка:", "").strip()
                hint_p = soup.new_tag("p")
                hint_p.string = hint_text
                block.append(hint_p)
                parent_p.insert_before(block)
                parent_p.decompose()

    # Преобразуем оставшиеся элементы в текст
    for tag in soup.find_all(True):
        if tag.name in ['b', 'strong']:
            tag.insert_before(soup.new_tag('p', string=f"**{tag.get_text(strip=True)}**"))
        elif tag.name == 'i':
            tag.insert_before(soup.new_tag('p', string=f"*{tag.get_text(strip=True)}*"))
        tag.unwrap()  # Убираем тег, оставляем только текст

    return str(soup)

def create_fb2_header(course_name):
    """Создание заголовка для FB2"""
    fb2_root = ET.Element("FictionBook")
    title_info = ET.SubElement(fb2_root, "title-info")
    title = ET.SubElement(title_info, "book-title")
    title.text = course_name
    author = ET.SubElement(title_info, "author")
    name = ET.SubElement(author, "name")
    name.text = "Алексей Курс"
    return fb2_root

def create_section(title, content, image_path=None):
    """Создание секции в FB2 (модуль/урок), добавляем изображение, если есть."""
    section = ET.Element("section")

    # Добавление заголовка
    title_elem = ET.SubElement(section, "title")
    title_elem.text = title

    # Добавление контента
    p = ET.SubElement(section, "p")
    p.text = content

    # Если путь к изображению передан, добавляем изображение
    if image_path and os.path.exists(image_path):
        image_base64 = image_to_base64(image_path)
        image_tag = ET.SubElement(section, "image",
                                  attrib={"l": "image/jpeg", "src": f"data:image/jpeg;base64,{image_base64}"})

    return section

def create_question_section(question_text, answers):
    """Создание секции для вопроса с ответами"""
    question_section = ET.Element("section")

    # Вопрос
    question = ET.SubElement(question_section, "p")
    question.text = f"**Вопрос:** {question_text}"

    # Ответы
    for answer in answers:
        answer_elem = ET.SubElement(question_section, "p")
        answer_elem.text = f"Ответ: {answer}"

    return question_section

def generate_course_fb2(course_dir):
    """Генерация FB2 курса с изображениями и вопросами"""
    course_name = os.path.basename(course_dir)
    fb2_root = create_fb2_header(course_name)

    # Добавление текстовой обложки
    add_cover_to_fb2(fb2_root, course_name)

    # body: Основной контент книги
    body = ET.SubElement(fb2_root, "body")

    modules = sorted(
        [m for m in os.listdir(course_dir) if os.path.isdir(os.path.join(course_dir, m))],
        key=lambda x: int(x.split('-')[0].lstrip('0')) if '-' in x else int(re.sub(r'\D', '', x) or 0)
    )

    for module_name in modules:
        module_path = os.path.join(course_dir, module_name)
        simple_module_name = simplify_name(module_name)

        section_content = f"Модуль {simple_module_name}"
        section = create_section(f"Модуль {simple_module_name}", section_content)
        body.append(section)

        lessons = sorted(
            [l for l in os.listdir(module_path) if os.path.isdir(os.path.join(module_path, l))],
            key=lambda x: int(x.split('-')[0].lstrip('0')) if '-' in x else int(re.sub(r'\D', '', x) or 0)
        )

        for lesson_name in lessons:
            lesson_path = os.path.join(module_path, lesson_name)
            simple_lesson_name = simplify_name(lesson_name)

            lesson_content = f"Урок {simple_lesson_name}"
            lesson_section = create_section(f"Урок {simple_lesson_name}", lesson_content)

            # Пример: добавляем изображение, если оно существует
            image_path = os.path.join(lesson_path, "image.jpg")  # или другой путь к изображению
            body.append(create_section(f"Урок {simple_lesson_name}", lesson_content, image_path=image_path))

            step_files = sorted([s for s in os.listdir(lesson_path) if s.endswith(".json")])

            for step_file in step_files:
                step_data = load_json(os.path.join(lesson_path, step_file))
                block = step_data.get("block", {})
                step_type = block.get("name")
                if step_type in ALLOWED_TYPES:
                    text = block.get("text", "")
                    if text:
                        formatted_text = parse_step_text(text, block_source=block)
                        step_section = create_section(f"Миссия", formatted_text)
                        body.append(step_section)

                # Включение вопросов с вариантами
                questions = block.get("questions", [])
                for question in questions:
                    question_text = question.get("question_text", "")
                    answers = question.get("answers", [])
                    question_section = create_question_section(question_text, answers)
                    body.append(question_section)

    return fb2_root

def save_fb2(fb2_root, output_path):
    """Сохранение FB2 файла"""
    tree = ET.ElementTree(fb2_root)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)

# ===================== ОСНОВНОЙ БЛОК =====================
if __name__ == "__main__":
    if not os.path.exists(FB2_DIR):
        os.makedirs(FB2_DIR)

    courses = sorted([
        c for c in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, c))
    ])

    for i, course_name in enumerate(courses):
        course_path = os.path.join(BASE_DIR, course_name)
        fb2_root = generate_course_fb2(course_path)
        fb2_path = os.path.join(FB2_DIR, f"{course_name}.fb2")
        save_fb2(fb2_root, fb2_path)
        print(f"✅ FB2 создан: {fb2_path}")
        if STOP_AFTER_FIRST_COURSE:
            print("⚠️ Остановлено после генерации первого курса")
            break
