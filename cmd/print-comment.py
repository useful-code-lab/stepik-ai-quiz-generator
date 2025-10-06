import re

# Путь к файлу
filename = "1-course.xml"

# Чтение файла
with open(filename, "r", encoding="utf-8") as f:
    content = f.read()

# Регулярное выражение для поиска href="/course/123456"
pattern = r'href="/course/(\d+)"'

# Находим все совпадения
course_ids = re.findall(pattern, content)

# Преобразуем в числа (если нужно)
course_ids = [int(cid) for cid in course_ids]

unique_course_ids = sorted(set(course_ids))

# Вывод в формате массива Python
print(unique_course_ids)
