#!/usr/bin/env python
import json
import time

import chromadb
from playwright.sync_api import sync_playwright

import ollama

# ================= НАСТРОЙКИ =================
DB_DIR = "./exam_db"  # Путь к базе знаний ChromaDB
COLLECTION_NAME = "exam_materials"

# Точные имена моделей из `ollama list`
EMBED_MODEL = "bge-m3"
LLM_MODEL = "qwen2.5:7b"

TEST_URL = "http://127.0.0.1:8000/student/programs"
MANUAL_SETUP_TIMEOUT = 300000  # 5 минут на ручной вход и выбор темы
HEADLESS_MODE = False  # False — чтобы войти и выбрать тему вручную
AUTO_CLICK = True  # True — автоматический клик и переход дальше

# CSS-селекторы под платформу
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
            options={"num_ctx": 3072, "num_predict": 10},
        )
        print("Модели загружены в ОЗУ и готовы к работе!")
    except Exception as e:
        print(f"[Предупреждение при прогреве]: {e}")


def get_context_from_db(collection, question_text, options_list=None, top_k=5):
    """Ищет top_k самых подходящих фрагментов текста по вопросу и вариантам ответа."""
    try:
        if options_list:
            options_clean = "; ".join(opt.strip() for opt in options_list if opt.strip())
            search_query = f"{question_text}\nВарианты: {options_clean}"
        else:
            search_query = question_text

        search_query = search_query[:1500]

        response = ollama.embeddings(model=EMBED_MODEL, prompt=search_query)
        results = collection.query(query_embeddings=[response["embedding"]], n_results=top_k)
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
        "Выбери ОДИН правильный вариант ответа"
        if not is_multiple
        else "Выбери ВСЕ правильные варианты ответа (может быть несколько)"
    )

    prompt = f"""Ты — точный экзаменационный ассистент. {task_instruction}, опираясь на приведенный справочный материал (а если вопрос общеизвестный — на точные факты).

Справочный материал:
{context}

Вопрос:
{question_text}

Варианты ответа:
{options_formatted}

Верни ответ строго в формате JSON с двумя полями:
{{
  "reason": "краткое обоснование в 1 предложение",
  "answers": [список целых чисел — номеров правильных вариантов от 1 до {len(options_list)}]
}}"""

    try:
        response = ollama.chat(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            format="json",
            options={"temperature": 0.1, "num_ctx": 4096, "num_predict": 300},
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
    collection = db_client.get_or_create_collection(name=COLLECTION_NAME)

    with sync_playwright() as p:
        print("Запуск браузера...")
        browser = p.chromium.launch(headless=HEADLESS_MODE)
        context = browser.new_context(viewport={"width": 1366, "height": 900})
        page = context.new_page()

        print(f"Открываем портал: {TEST_URL}")
        page.goto(TEST_URL)

        warmup_models()

        print("\n========================================================")
        print("ДЕЙСТВИЯ ПОЛЬЗОВАТЕЛЯ:")
        print("1. Введите логин и пароль в открывшемся окне браузера (если требуется).")
        print("2. Выберите нужную программу и тему в дереве слева.")
        print("3. Нажмите кнопку 'Режим обучения' или 'Начать Экзамен'.")
        print(
            f"Агент автоматически начнет работу, как только появится окно теста (ожидание до {MANUAL_SETUP_TIMEOUT // 1000} сек.)..."
        )
        print("========================================================\n")

        try:
            page.wait_for_selector(
                "#modal_exam_checkbox:checked", state="attached", timeout=MANUAL_SETUP_TIMEOUT
            )
            print("Окно экзамена обнаружено! Перехватываю управление...")
            time.sleep(0.5)
        except Exception:
            print("Время ожидания истекло, окно экзамена так и не было открыто.")
            input("Нажмите Enter для закрытия браузера...")
            browser.close()
            return

        last_question_text = ""

        while True:
            # Проверяем открытый тег <dialog id="alert_confirm" open> с итогом теста
            if page.locator("dialog#alert_confirm[open]").count() > 0:
                result_text = (
                    page.locator("#alert_confirm .modal-box > div:first-child").inner_text().strip()
                )
                print(f"\n[РЕЗУЛЬТАТ ТЕСТА]: {result_text}")
                break

            # Если тест закрыли вручную или он завершился, ждём до 1.5 сек появления окна результата
            if not page.locator("#modal_exam_checkbox").is_checked():
                time.sleep(0.8)
                if page.locator("dialog#alert_confirm[open]").count() > 0:
                    result_text = (
                        page.locator("#alert_confirm .modal-box > div:first-child")
                        .inner_text()
                        .strip()
                    )
                    print(f"\n[РЕЗУЛЬТАТ ТЕСТА]: {result_text}")
                else:
                    print("\nОкно экзамена закрыто.")
                break

            # Ждём отрисовки таблицы с вариантами ответа
            if page.locator(SELECTOR_OPTIONS_LABELS).count() == 0:
                time.sleep(0.2)
                continue

            question_text = extract_clean_question(page)

            # Защита от повторного считывания того же вопроса при переключении
            if not question_text or question_text == last_question_text:
                time.sleep(0.25)
                continue

            last_question_text = question_text
            option_labels = page.locator(SELECTOR_OPTIONS_LABELS).all()
            options_list = [
                el.inner_text().replace("\xa0", " ").replace("\n", " ").strip()
                for el in option_labels
            ]

            is_multiple = (
                page.locator("#react_exam .plain table input[type='checkbox']").count() > 0
            )

            header_loc = page.locator("#react_exam .modal-box > div.flex.justify-between")
            header_info = (
                header_loc.inner_text().replace("\n", " | ") if header_loc.is_visible() else ""
            )

            print(f"================ {header_info} ================")
            print(f"Вопрос: {question_text}")

            rag_context = get_context_from_db(
                collection, question_text, options_list=options_list, top_k=5
            )

            start_time = time.time()
            chosen_nums, reason = ask_qwen(question_text, options_list, rag_context, is_multiple)
            elapsed = round(time.time() - start_time, 1)

            print(f"-> Выбраны варианты: {chosen_nums} (за {elapsed} сек.)")
            print(f"-> Обоснование: {reason}\n")

            if not AUTO_CLICK:
                cmd = input(
                    "Нажмите Enter для клика или введите номера через пробел (q - выход): "
                ).strip()
                if cmd.lower() == "q":
                    break
                elif cmd:
                    chosen_nums = [
                        int(x)
                        for x in cmd.split()
                        if x.isdigit() and 1 <= int(x) <= len(option_labels)
                    ]

            # Кликаем по <label> выбранных вариантов
            for num in chosen_nums:
                idx = num - 1
                if 0 <= idx < len(option_labels):
                    option_labels[idx].click()
                    time.sleep(0.15)

            # Нажимаем кнопку "Следующий вопрос" или "Завершить"
            next_btn = page.locator(SELECTOR_NEXT_BTN)
            if next_btn.is_visible():
                next_btn.click()
                time.sleep(0.5)

                # Если на последнем вопросе открылось окно подтверждения <dialog id="react_confirm" open>
                if page.locator("dialog#react_confirm[open]").count() > 0:
                    confirm_btn = page.locator("#react_confirm button:has-text('Подтвердить')")
                    if confirm_btn.is_visible():
                        confirm_btn.click()
                        time.sleep(0.6)
            else:
                print("Кнопка перехода не найдена. Ожидаем ручного действия...")
                time.sleep(2)

        print("\nРабота агента завершена! Браузер остаётся открытым для просмотра результата.")
        try:
            input("Нажмите Enter в этом окне терминала, когда захотите закрыть браузер...")
        except EOFError:
            page.wait_for_event("close", timeout=0)
        browser.close()


if __name__ == "__main__":
    main()
