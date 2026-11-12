import json
import time
import chromadb
import ollama
from playwright.sync_api import sync_playwright

# ================= НАСТРОЙКИ =================
DB_DIR = "./exam_db"                 # Путь к базе знаний ChromaDB
COLLECTION_NAME = "exam_materials"

# Укажите точные имена моделей из `ollama list`
EMBED_MODEL = "hf.co/BAAI/bge-m3-GGUF:Q8_0"                     # или "bge-m3"
LLM_MODEL = "hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"   # или "qwen3:1.7b"

TEST_URL = "http://адрес-вашего-сайта/student/programs"  # Впишите точный URL портала
MANUAL_SETUP_TIMEOUT = 300000        # 5 минут на ручной вход и выбор темы
HEADLESS_MODE = False                # False — чтобы войти и выбрать тему вручную
AUTO_CLICK = True                    # True — автоматический клик и переход дальше

# CSS-селекторы под вашу платформу (проверено по HTML)
SELECTOR_MODAL = "#react_exam"
SELECTOR_OPTIONS_LABELS = "#react_exam .plain table label"
SELECTOR_NEXT_BTN = "#react_exam .modal-box > div.flex:last-child button"
# =============================================


def warmup_models():
    """Заранее загружает модели в ОЗУ, чтобы не тратить секунды таймера на первом вопросе."""
    print("Прогрев нейросетей в оперативной памяти (займет 5-15 сек.)...")
    try:
        ollama.embeddings(model=EMBED_MODEL, prompt="прогрев")
        ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": "Ответь цифрой 1"}],
            options={"num_ctx": 3072, "num_predict": 10}
        )
        print("Модели загружены в ОЗУ и готовы к работе!")
    except Exception as e:
        print(f"[Предупреждение при прогреве]: {e}")


def get_context_from_db(collection, question_text, top_k=3):
    """Ищет top_k самых подходящих фрагментов текста из нормативных документов."""
    try:
        response = ollama.embeddings(model=EMBED_MODEL, prompt=question_text)
        results = collection.query(
            query_embeddings=[response["embedding"]],
            n_results=top_k
        )
        docs = results.get("documents", [])
        if docs and len(docs) > 0 and len(docs[0]) > 0:
            return "\n---\n".join(docs[0])
    except Exception as e:
        print(f"[Ошибка поиска в ChromaDB]: {e}")
    return "Контекст в базе не найден."


def ask_qwen(question_text, options_list, context, is_multiple=False):
    """Отправляет вопрос и контекст в LLM и получает номера правильных ответов."""
    options_formatted = "\n".join([f"{i + 1}. {opt}" for i, opt in enumerate(options_list)])
    
    task_instruction = (
        "Выбери ОДИН правильный вариант ответа" if not is_multiple 
        else "Выбери ВСЕ правильные варианты ответа (может быть несколько)"
    )

    prompt = f"""Ты — точный юридический и экзаменационный ассистент. {task_instruction}, опираясь строго на приведенный ниже справочный материал.

Справочный материал:
{context}

Вопрос:
{question_text}

Варианты ответа:
{options_formatted}

Верни ответ строго в формате JSON с двумя полями:
{{
  "reason": "краткое обоснование в 1 предложение со ссылкой на норму из текста",
  "answers": [список целых чисел — номеров правильных вариантов от 1 до {len(options_list)}]
}}"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={
                "temperature": 0.1,
                "num_ctx": 4096,
                "num_predict": 300
            }
        )
        raw_content = response["message"]["content"].strip()
        data = json.loads(raw_content)
        answers = [int(x) for x in data.get("answers", []) if str(x).isdigit()]
        if not answers:
            return [1], "Нейросеть вернула пустой список, выбран 1-й вариант."
        return answers, data.get("reason", "Без обоснования.")
    except Exception as e:
        print(f"[Ошибка парсинга ответа нейросети]: {e}")
        return [1], "Ошибка формата JSON, выбран первый вариант по умолчанию."


def extract_clean_question(page):
    """Извлекает чистый текст вопроса из div.plain без таблицы с вариантами ответов."""
    return page.evaluate("""() => {
        const container = document.querySelector('#react_exam .plain');
        if (!container) return '';
        const clone = container.cloneNode(true);
        const table = clone.querySelector('table');
        if (table) table.remove();
        return clone.innerText
            .replace(/\\u00a0/g, ' ')
            .replace(/\\s+/g, ' ')
            .trim();
    }""")


def main():
    print("Подключение к локальной базе знаний...")
    db_client = chromadb.PersistentClient(path=DB_DIR)
    collection = db_client.get_collection(name=COLLECTION_NAME)

    with sync_playwright() as p:
        print("Запуск браузера...")
        # Если на целевом ПК установлен Яндекс Браузер и нужен он, раскомментируйте executable_path:
        browser = p.chromium.launch(
            # executable_path="/usr/bin/yandex-browser",
            headless=HEADLESS_MODE
        )
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        print(f"Открываем портал: {TEST_URL}")
        page.goto(TEST_URL)

        # Прогреваем модели, пока пользователь авторизуется
        warmup_models()

        print("\n========================================================")
        print("ДЕЙСТВИЯ ПОЛЬЗОВАТЕЛЯ:")
        print("1. Введите логин и пароль в открывшемся окне браузера.")
        print("2. Выберите нужную программу и тему в дереве слева.")
        print("3. Нажмите кнопку 'Режим обучения' или 'Начать Экзамен'.")
        print(f"Агент автоматически начнет работу, как только появится окно теста (ожидание до {MANUAL_SETUP_TIMEOUT // 1000} сек.)...")
        print("========================================================\n")

        try:
            page.wait_for_selector(SELECTOR_MODAL, state="visible", timeout=MANUAL_SETUP_TIMEOUT)
            print("Окно экзамена обнаружено! Перехватываю управление...\n")
        except Exception:
            print("Время ожидания истекло, окно экзамена так и не было открыто.")
            browser.close()
            return

        last_question_text = ""

        while True:
            # Проверяем, не появилось ли финальное диалоговое окно с результатом (alert_confirm)
            if page.locator("#alert_confirm").is_visible():
                result_text = page.locator("#alert_confirm .modal-box > div:first-child").inner_text().strip()
                print(f"\n[РЕЗУЛЬТАТ ТЕСТА]: {result_text}")
                break

            # Проверяем, открыто ли еще модальное окно экзамена
            if not page.locator(SELECTOR_MODAL).is_visible():
                print("\nОкно экзамена закрыто. Тест завершен!")
                break

            # Ждем, пока внутри .plain отрендерится таблица с вариантами
            if page.locator(SELECTOR_OPTIONS_LABELS).count() == 0:
                time.sleep(0.2)
                continue

            question_text = extract_clean_question(page)

            # Защита от повторного считывания того же вопроса во время анимации перехода
            if not question_text or question_text == last_question_text:
                time.sleep(0.25)
                continue

            last_question_text = question_text
            option_labels = page.locator(SELECTOR_OPTIONS_LABELS).all()
            options_list = [
                el.inner_text().replace("\xa0", " ").replace("\n", " ").strip()
                for el in option_labels
            ]

            is_multiple = page.locator("#react_exam .plain table input[type='checkbox']").count() > 0

            header_loc = page.locator("#react_exam .modal-box > div.flex.justify-between")
            header_info = header_loc.inner_text().replace("\n", " | ") if header_loc.is_visible() else ""

            print(f"================ {header_info} ================")
            print(f"Вопрос: {question_text}")

            rag_context = get_context_from_db(collection, question_text, top_k=3)

            start_time = time.time()
            chosen_nums, reason = ask_qwen(question_text, options_list, rag_context, is_multiple)
            elapsed = round(time.time() - start_time, 1)

            print(f"-> Выбраны варианты: {chosen_nums} (за {elapsed} сек.)")
            print(f"-> Обоснование: {reason}\n")

            if not AUTO_CLICK:
                cmd = input("Нажмите Enter для клика или введите номера через пробел (q - выход): ").strip()
                if cmd.lower() == 'q':
                    break
                elif cmd:
                    chosen_nums = [int(x) for x in cmd.split() if x.isdigit() and 1 <= int(x) <= len(option_labels)]

            # Кликаем по <label> выбранных вариантов
            for num in chosen_nums:
                idx = num - 1
                if 0 <= idx < len(option_labels):
                    option_labels[idx].click()
                    time.sleep(0.15)

            # Нажимаем кнопку "Следующий вопрос" (или завершение)
            next_btn = page.locator(SELECTOR_NEXT_BTN)
            if next_btn.is_visible():
                next_btn.click()
                time.sleep(0.6)

                # Если на последнем вопросе всплыло окно подтверждения #react_confirm — подтверждаем
                confirm_btn = page.locator("#react_confirm button:has-text('Подтвердить')")
                if confirm_btn.is_visible():
                    confirm_btn.click()
                    time.sleep(0.5)
            else:
                print("Кнопка перехода не найдена. Ожидаем ручного действия...")
                time.sleep(2)

        print("Работа агента завершена! Окно браузера останется открытым на 15 секунд...")
        time.sleep(15)
        browser.close()


if __name__ == "__main__":
    main()
