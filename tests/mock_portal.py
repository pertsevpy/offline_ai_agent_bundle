import json
from pathlib import Path
from flask import Flask, render_template_string, request, jsonify

app = Flask(__name__)
QUESTIONS_FILE = Path(__file__).parent / "questions.json"


def load_questions_bank() -> dict:
    with open(QUESTIONS_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


HTML_TEMPLATE = """<!DOCTYPE html>
<html data-theme="light" lang="ru">
<head>
  <meta charset="utf-8">
  <title>Мок-портал тестирования</title>
  <link href="https://cdn.jsdelivr.net/npm/daisyui@4.12.10/dist/full.min.css" rel="stylesheet" type="text/css" />
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    .navbar-main {
      display: grid;
      grid-template-columns: 80px 240px 1fr auto;
      gap: 10px;
      padding: 10px 20px;
      align-items: center;
    }
    .tree {
      border-right: 2px solid #e5e7eb;
      padding: 12px;
      overflow-y: auto;
      background: #fafafa;
      user-select: none;
    }
    .tree_item {
      padding: 5px 8px;
      border-radius: 4px;
      cursor: pointer;
      display: flex;
      align-items: center;
    }
    .tree_item:hover { background-color: #f3f4f6; }
    .tree_item.selected { background-color: #fee2e2; font-weight: 600; }
    .left_div { display: flex; align-items: center; gap: 6px; }
    .button.down::before { content: "▼"; font-size: 10px; color: #6b7280; }
    .button.right::before { content: "▶"; font-size: 10px; color: #6b7280; }
    .gutter { width: 4px; background: #e5e7eb; }
    .form_container { flex: 1; padding: 24px; }
    #react_exam.modal-open { opacity: 1; pointer-events: auto; visibility: visible; }
    #react_exam .modal-box { max-width: 56rem; width: 90%; }
  </style>
</head>
<body class="">
  <div class="text-white m-0 p-0" data-theme="light" style="background-color: #4d0000;">
    <div class="my-0 mx-auto navbar-main" style="max-width:1920px">
      <div class="image-nic">
        <div class="w-16 h-20 border border-yellow-500/50 flex items-center justify-center text-xs text-center font-bold">
          УЦ<br>ТЕСТ
        </div>
      </div>
      <div class="address text-xs leading-relaxed">
        <div>101000, г. Примерск,</div>
        <div>ул. Тестовая, д. 1</div>
        <div>+7 (000) 000-00-00</div>
      </div>
      <div>
        <div class="text-2xl mt-1">Мок-портал тестирования</div>
        <div class="text-lg opacity-90">программы обучения дополнительного профессионального образования</div>
        <div class="navbar" style="padding:0; min-height:0">
          <ul class="menu menu-horizontal px-0 text-sm">
            <li><a href="#">Инструкция</a></li>
            <li style="color:yellow"><a href="/student/programs">Программы обучения</a></li>
            <li><a href="#">Сообщения</a></li>
            <li><a href="#">Удостоверения</a></li>
          </ul>
        </div>
      </div>
      <div class="login">
        <span class="px-3 py-1 bg-black/20 rounded text-sm">test_user</span>
      </div>
    </div>
  </div>

  <div class="flex mx-auto" id="react" style="max-width:1920px">
    <div id="react_app" class="w-full flex" style="height: calc(100vh - 135px);">
      
      <div class="tree" style="width: 32%;">
        <div class="tree_item selectable">
          <div class="left_div"><div class="button down"></div><div class="caption">Программы обучения</div></div>
        </div>
        <div class="pl-3">
          <div class="tree_item selectable">
            <div class="left_div"><div class="button down"></div><div class="caption text-red-700">Общеобразовательный модуль</div></div>
          </div>
          <div class="pl-3">
            <div class="tree_item selectable">
              <div class="left_div"><div class="button down"></div><div class="caption">Обучение/Экзамены</div></div>
            </div>
            <div class="pl-3">
              <div class="tree_item selectable topic-node selected" data-topic="geography" onclick="selectTopic(this, 'geography', 'РАЗДЕЛ 1. ГЕОГРАФИЯ И ЕСТЕСТВОЗНАНИЕ')">
                <div class="left_div"><div class="button"></div><div class="caption text-red-700">РАЗДЕЛ 1. ГЕОГРАФИЯ И ЕСТЕСТВОЗНАНИЕ</div></div>
              </div>
              <div class="tree_item selectable topic-node" data-topic="informatics" onclick="selectTopic(this, 'informatics', 'РАЗДЕЛ 2. ОСНОВЫ ИНФОРМАТИКИ И СЕТЕЙ')">
                <div class="left_div"><div class="button"></div><div class="caption text-red-700">РАЗДЕЛ 2. ОСНОВЫ ИНФОРМАТИКИ И СЕТЕЙ</div></div>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div class="gutter"></div>

      <div class="form_container overflow-y-auto relative">
        <div class="mb-4 text-sm text-gray-600">
          Выбранный раздел: <strong id="selected-topic-title" class="text-gray-900">РАЗДЕЛ 1. ГЕОГРАФИЯ И ЕСТЕСТВОЗНАНИЕ</strong>
        </div>
        <form onsubmit="return false;">
          <button class="btn btn-outline btn-header mt-3 w-80" event="exam_test" type="button" onclick="startExam('training')">
            Режим обучения
          </button>
          <br>
          <button class="btn btn-outline btn-header mt-4 w-80" event="exam_start" type="button" onclick="startExam('exam')">
            Начать Экзамен
          </button>
        </form>
      </div>
    </div>

    <dialog id="react_confirm" class="modal">
      <div class="modal-box">
        <div class="modal-action-center text-center">
          <div id="react_confirm_text" class="text-lg font-medium">Вы действительно хотите завершить тестирование?</div>
          <br>
          <button type="button" class="btn btn-primary" onclick="finishExamConfirmed()">Подтвердить</button>&nbsp;
          <button type="button" class="btn" onclick="document.getElementById('react_confirm').close()">Отмена</button>
        </div>
      </div>
    </dialog>

    <dialog id="alert_confirm" class="modal">
      <div class="modal-box">
        <div id="alert_confirm_text" class="text-lg font-semibold mb-4"></div>
        <div class="modal-action">
          <button type="button" class="btn" onclick="closeResultModal()">Продолжить</button>
        </div>
      </div>
    </dialog>

    <input type="checkbox" id="modal_exam_checkbox" class="modal-toggle">
    <div id="react_exam" class="modal" role="dialog">
      <div class="modal-box flex flex-col relative">
        <button type="button" class="btn btn-sm btn-circle btn-ghost absolute right-2 top-2" onclick="abortExam()">✕</button>
        
        <div class="flex justify-between">
          <div id="exam_progress" class="text-xl mb-8">Вопрос 1 из 3</div>
          <div id="exam_timer" class="text-l mb-8 pr-8">Оставшееся время: 45 сек.</div>
        </div>

        <div class="mb-8">
          <div class="plain" id="exam_plain_container"></div>
        </div>

        <div class="flex">
          <button id="exam_next_btn" type="button" class="btn mt-4" onclick="handleNextClick()">Следующий вопрос</button>
        </div>
      </div>
    </div>
  </div>

  <script>
    let currentTopic = "geography";
    let questions = [];
    let currentIdx = 0;
    let userAnswers = {};
    let timerInterval = null;
    let secondsLeft = 45;

    function selectTopic(el, topicKey, title) {
      document.querySelectorAll('.topic-node').forEach(n => n.classList.remove('selected'));
      el.classList.add('selected');
      currentTopic = topicKey;
      document.getElementById('selected-topic-title').innerText = title;
    }

    async function startExam(mode) {
      const res = await fetch(`/api/questions?topic=${currentTopic}`);
      questions = await res.json();
      currentIdx = 0;
      userAnswers = {};

      document.getElementById('modal_exam_checkbox').checked = true;
      document.getElementById('react_exam').classList.add('modal-open');
      renderQuestion();
    }

    function startTimer() {
      clearInterval(timerInterval);
      secondsLeft = 45;
      document.getElementById('exam_timer').innerText = `Оставшееся время: ${secondsLeft} сек.`;
      timerInterval = setInterval(() => {
        secondsLeft--;
        document.getElementById('exam_timer').innerText = `Оставшееся время: ${secondsLeft} сек.`;
        if (secondsLeft <= 0) {
          clearInterval(timerInterval);
          handleNextClick(true);
        }
      }, 1000);
    }

    function renderQuestion() {
      const q = questions[currentIdx];
      document.getElementById('exam_progress').innerText = `Вопрос ${currentIdx + 1} из ${questions.length}`;
      
      const nextBtn = document.getElementById('exam_next_btn');
      nextBtn.innerText = (currentIdx === questions.length - 1) ? "Завершить" : "Следующий вопрос";

      const inputType = q.type === "checkbox" ? "checkbox" : "radio";
      const inputClass = q.type === "checkbox" ? "checkbox checkbox-md" : "radio radio-md";

      let rowsHtml = q.options.map(opt => `
        <tr>
          <td>
            <input class="${inputClass}" id="exam_program_answer__${opt.id}" name="exam_program_question__${q.id}" type="${inputType}" value="${opt.id}">
          </td>
          <td>
            <label for="exam_program_answer__${opt.id}" style="cursor:pointer;">
              <p align="left">
                <span style="font-family: georgia, palatino, serif; font-size: 14pt;">
                  ${opt.text}
                </span>
              </p>
            </label>
          </td>
        </tr>
      `).join('');

      document.getElementById('exam_plain_container').innerHTML = `
        <p><span style="font-family: 'trebuchet ms', geneva, sans-serif; font-size: 14pt;">${q.text}</span></p>
        <table cellpadding="5" class="mt-5">
          <tbody>${rowsHtml}</tbody>
        </table>
      `;

      startTimer();
    }

    function collectCurrentAnswer() {
      const q = questions[currentIdx];
      const checked = Array.from(document.querySelectorAll(`input[name="exam_program_question__${q.id}"]:checked`))
        .map(el => parseInt(el.value));
      userAnswers[q.id] = checked;
    }

    function handleNextClick(force = false) {
      collectCurrentAnswer();
      if (currentIdx < questions.length - 1) {
        currentIdx++;
        setTimeout(renderQuestion, 150);
      } else {
        if (force) {
          finishExamConfirmed();
        } else {
          document.getElementById('react_confirm').showModal();
        }
      }
    }

    async function finishExamConfirmed() {
      clearInterval(timerInterval);
      document.getElementById('react_confirm').close();
      document.getElementById('modal_exam_checkbox').checked = false;
      document.getElementById('react_exam').classList.remove('modal-open');

      const res = await fetch('/api/submit', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({ topic: currentTopic, answers: userAnswers })
      });
      const result = await res.json();

      document.getElementById('alert_confirm_text').innerText =
        `Тестирование завершено! Правильных ответов: ${result.correct_count} из ${result.total} (${result.percent}%). Оценка: ${result.passed ? 'СДАНО' : 'НЕ СДАНО'}.`;
      document.getElementById('alert_confirm').showModal();
    }

    function closeResultModal() {
      document.getElementById('alert_confirm').close();
    }

    function abortExam() {
      clearInterval(timerInterval);
      document.getElementById('modal_exam_checkbox').checked = false;
      document.getElementById('react_exam').classList.remove('modal-open');
    }
  </script>
</body>
</html>
"""


@app.route("/student/programs")
def index():
    return render_template_string(HTML_TEMPLATE)


@app.route("/api/questions")
def get_questions():
    bank = load_questions_bank()
    topic = request.args.get("topic", "geography")
    qs = bank.get(topic, bank.get("geography", []))
    sanitized = [
        {"id": q["id"], "type": q["type"], "text": q["text"], "options": q["options"]}
        for q in qs
    ]
    return jsonify(sanitized)


@app.route("/api/submit", methods=["POST"])
def submit_exam():
    bank = load_questions_bank()
    data = request.json
    topic = data.get("topic", "geography")
    user_answers = data.get("answers", {})
    qs = bank.get(topic, [])

    correct_count = 0
    for q in qs:
        expected = sorted(q["correct"])
        actual = sorted(user_answers.get(str(q["id"]), []))
        if expected == actual:
            correct_count += 1

    total = len(qs)
    percent = round((correct_count / total) * 100) if total else 0
    return jsonify({
        "correct_count": correct_count,
        "total": total,
        "percent": percent,
        "passed": percent >= 80
    })


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
