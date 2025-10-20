import os
import json
from bs4 import BeautifulSoup
from weasyprint import HTML, CSS

BASE_DIR = "courses"
PDF_DIR = "pdfs"
ALLOWED_TYPES = {"choice", "matching", "sorting"}
STOP_AFTER_FIRST_COURSE = False

# ===================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ =====================
def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)

def simplify_name(name: str) -> str:
    """Удаляем ведущий 0 из названия модуля/урока"""
    import re
    match = re.match(r"0*(\d+)(.*)", name)
    if match:
        return f"{int(match.group(1))}{match.group(2)}".strip()
    return name

# ==== Генерация HTML для ответов (все видимо) ====
def options_to_html(options):
    html = '<ul>\n'
    for opt in options:
        text = opt.get("text", "")
        if opt.get("is_correct"):
            html += f'  <li><b>{text}</b></li>\n'
        else:
            html += f'  <li>{text}</li>\n'
    html += '</ul>'
    return f'<p class="answer-title">Ответ:</p>{html}'

def pairs_to_html(pairs):
    html = '<ul>\n'
    for pair in pairs:
        first = pair.get("first", "")
        second = pair.get("second", "")
        html += f'  <li><b>{first}</b> — {second}</li>\n'
    html += '</ul>'
    return f'<p class="answer-title">Ответ:</p>{html}'

def parse_step_text(html_text: str, block_source=None) -> str:
    soup = BeautifulSoup(html_text, "html.parser")

    # Заголовки миссий
    for h3 in soup.find_all("h3"):
        h3.name = "p"
        h3['class'] = ['mission-title']

    # Подсказки <em>
    for em in soup.find_all("em"):
        text = em.get_text(" ", strip=True)
        if "подсказка" in text.lower():
            parent_p = em.find_parent("p")
            if parent_p:
                block = soup.new_tag("blockquote")
                block['class'] = ['hint']
                header = soup.new_tag("p")
                header.string = "💡 Подсказка:"
                block.append(header)
                hint_text = parent_p.get_text(" ", strip=True).replace("Подсказка:", "").strip()
                hint_p = soup.new_tag("p")
                hint_p.string = hint_text
                block.append(hint_p)
                parent_p.insert_before(block)
                parent_p.decompose()

    # Варианты и ответ
    if block_source:
        source = block_source.get("source", {})
        if block_source["name"] == "choice":
            options = source.get("options", [])

            # 1) В текст задания — все варианты
            all_options_html = "<ul>\n"
            for opt in options:
                all_options_html += f"  <li>{opt.get('text','')}</li>\n"
            all_options_html += "</ul>"
            soup.append(BeautifulSoup(all_options_html, "html.parser"))

            # 2) В ответе — только правильный вариант
            answer_html = "<ul>\n"
            for opt in options:
                if opt.get("is_correct"):
                    answer_html += f"  <li><b>{opt['text']}</b></li>\n"
            answer_html += "</ul>"
            answer_html = f'<p class="answer-title">Ответ:</p>{answer_html}'

            answer_soup = BeautifulSoup(answer_html, "html.parser")
            # вставляем после подсказки, если есть, иначе в конец
            hints = soup.find_all("blockquote", class_="hint")
            if hints:
                hints[-1].insert_after(answer_soup)
            else:
                soup.append(answer_soup)

        elif block_source["name"] == "matching":
            pairs = source.get("pairs", [])
            answer_html = pairs_to_html(pairs)
            soup.append(BeautifulSoup(answer_html, "html.parser"))

        elif block_source["name"] == "sorting":
            options = source.get("options", [])
            answer_html = options_to_html(options)
            soup.append(BeautifulSoup(answer_html, "html.parser"))

    # <li> — жирная часть до тире
    for li in soup.find_all("li"):
        text = li.get_text(" ", strip=True)
        if "—" in text:
            bold, normal = text.split("—", 1)
            li.clear()
            b_tag = soup.new_tag("b")
            b_tag.string = bold.strip()
            li.append(b_tag)
            li.append(f" — {normal.strip()}")
        else:
            li.string = text

    return str(soup)


# ===================== ГЕНЕРАЦИЯ HTML КУРСА =====================
def generate_course_html(course_dir):
    course_name = os.path.basename(course_dir)
    html_parts = []

    # Обложка
    cover_path = os.path.join(course_dir, "cover.png")
    if os.path.exists(cover_path):
        abs_cover = "file://" + os.path.abspath(cover_path)
        html_parts.append(f"""
        <div style="text-align:center;margin-bottom:25px;">
            <img src="{abs_cover}" alt="Обложка курса"
                 style="max-width:500px;height:auto;border-radius:14px;
                 box-shadow:0 5px 20px rgba(0,0,0,0.25);">
        </div>
        """)

    html_parts.append(f"<h1>📘 {course_name}</h1>")

    # Модули
    modules = sorted([m for m in os.listdir(course_dir)
                      if os.path.isdir(os.path.join(course_dir, m))],
                     key=lambda x: int(x.split('-')[0].lstrip('0')))
    for module_name in modules:
        module_path = os.path.join(course_dir, module_name)
        simple_module_name = simplify_name(module_name)
        html_parts.append(f"<h2>📂 Модуль {simple_module_name}</h2>")

        lessons = sorted([l for l in os.listdir(module_path)
                          if os.path.isdir(os.path.join(module_path, l))],
                         key=lambda x: int(x.split('-')[0].lstrip('0')))
        for lesson_name in lessons:
            lesson_path = os.path.join(module_path, lesson_name)
            simple_lesson_name = simplify_name(lesson_name)
            html_parts.append(f"<h3>📘 Урок {simple_lesson_name}</h3>")

            step_files = sorted([s for s in os.listdir(lesson_path) if s.endswith(".json")])
            for step_idx, step_file in enumerate(step_files, start=1):
                step_data = load_json(os.path.join(lesson_path, step_file))
                block = step_data.get("block", {})
                step_type = block.get("name")
                if step_type not in ALLOWED_TYPES:
                    continue
                text = block.get("text", "")
                if not text:
                    continue
                formatted_text = parse_step_text(text, block_source=block)
                html_parts.append(f"<h4>💡 Шаг {step_idx:02d}:</h4>{formatted_text}")

    return "\n".join(html_parts)

# ===================== СОЗДАНИЕ PDF =====================
def create_pdf_from_html(course_dir, pdf_dir):
    if not os.path.exists(pdf_dir):
        os.makedirs(pdf_dir)

    html_content = generate_course_html(course_dir)
    pdf_path = os.path.join(pdf_dir, f"{os.path.basename(course_dir)}.pdf")

    css = CSS(string="""
        @page { size: A4; margin: 25mm 20mm 25mm 20mm; }
        body { font-family: 'DejaVu Sans', sans-serif; font-size: 12pt; line-height: 1.6; color:#222; background:#fff; }
        h1 { text-align:center; color:#1A5276; font-size:22pt; margin-bottom:20px; border-bottom:2px solid #1A5276; padding-bottom:5px; }
        h2 { color:#117A65; margin-top:25px; font-size:16pt; }
        h3 { color:#CA6F1E; margin-top:15px; font-size:14pt; }
        h4 { color:#884EA0; font-size:13pt; margin-top:10px; }
        p { margin:5px 0; }
        p.mission-title { font-weight:bold; color:#2E4053; margin-top:8px; }
        p.answer-title { font-weight:bold; color:#B03A2E; margin-top:8px; }
        ul { margin-top:3px; margin-bottom:10px; }
        li { margin:3px 0; }
        b { color:#000; }
        blockquote.hint { font-style:italic; background:#FBFCFC; border-left:4px solid #5DADE2; padding:8px 12px; margin:12px 0; color:#2C3E50; }
        img { display:block; margin:15px auto; max-width:90%; height:auto; border-radius:10px; box-shadow:0 2px 15px rgba(0,0,0,0.2); }
        span { display:none; }
    """)

    HTML(string=html_content).write_pdf(pdf_path, stylesheets=[css])
    print(f"✅ PDF создан: {pdf_path}")

# ===================== ОСНОВНОЙ БЛОК =====================
if __name__ == "__main__":
    if not os.path.exists(PDF_DIR):
        os.makedirs(PDF_DIR)

    TARGET_SUBSTRING = "Продвинутое искусство составления резюме"

    courses = sorted([
        c for c in os.listdir(BASE_DIR)
        if os.path.isdir(os.path.join(BASE_DIR, c)) and TARGET_SUBSTRING in c
    ])

    for i, course_name in enumerate(courses):
        create_pdf_from_html(os.path.join(BASE_DIR, course_name), PDF_DIR)
        if STOP_AFTER_FIRST_COURSE:
            print("⚠️ Остановлено после генерации первого курса")
            break
