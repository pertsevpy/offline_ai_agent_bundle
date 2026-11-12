#!/bin/bash
set -e

BUNDLE_DIR="$(realpath ./offline_ai_agent_bundle)"
PYTHON_VER="3.11" # Версия Python на целевом ПК

mkdir -p "$BUNDLE_DIR"/{wheels,ollama,models,playwright_browsers,app/docs}

echo "=== 1. Проверка и скачивание Python-зависимостей (.whl) ==="
# pip download автоматически пропускает уже скачанные в --dest файлы
pip download \
    --dest "$BUNDLE_DIR/wheels" \
    --only-binary=:all: \
    --python-version "$PYTHON_VER" \
    playwright \
    ollama \
    chromadb \
    pypdf \
    python-docx \
    beautifulsoup4 \
    lxml \
    llama-index-core \
    llama-index-llms-ollama \
    llama-index-embeddings-ollama \
    llama-index-vector-stores-chroma \
    llama-index-readers-file

echo "=== 2. Проверка и скачивание Playwright (Chromium) ==="
export PLAYWRIGHT_BROWSERS_PATH="$BUNDLE_DIR/playwright_browsers"
if ls -d "$PLAYWRIGHT_BROWSERS_PATH"/chromium* >/dev/null 2>&1; then
    echo "[SKIP] Браузер Chromium уже скачан в $PLAYWRIGHT_BROWSERS_PATH"
else
    pip install playwright --quiet
    playwright install chromium
fi

echo "=== 3. Проверка и скачивание Ollama с GitHub Releases ==="
EXISTING_OLLAMA=$(ls "$BUNDLE_DIR/ollama/"ollama-linux-amd64* 2>/dev/null | head -n 1)
NEED_DOWNLOAD_OLLAMA=true

if [ -n "$EXISTING_OLLAMA" ] && [ -f "$EXISTING_OLLAMA" ]; then
    # Проверяем размер файла в байтах (должен быть > 500 МБ = 524288000 байт)
    FILE_SIZE=$(stat -c%s "$EXISTING_OLLAMA" 2>/dev/null || wc -c < "$EXISTING_OLLAMA")
    if [ "$FILE_SIZE" -gt 524288000 ]; then
        echo "[SKIP] Архив Ollama уже скачан и цел: $(basename "$EXISTING_OLLAMA") ($(($FILE_SIZE / 1048576)) МБ)"
        FILENAME=$(basename "$EXISTING_OLLAMA")
        NEED_DOWNLOAD_OLLAMA=false
    else
        echo "[WARN] Найден повреждённый/неполный файл $(basename "$EXISTING_OLLAMA") ($FILE_SIZE байт). Перекачиваем..."
        rm -f "$EXISTING_OLLAMA"
    fi
fi

if [ "$NEED_DOWNLOAD_OLLAMA" = true ]; then
    OLLAMA_URL=$(curl -s https://api.github.com/repos/ollama/ollama/releases/latest \
      | grep -E "browser_download_url.*ollama-linux-amd64\.(tar\.zst|tgz)\"" \
      | head -n 1 \
      | cut -d '"' -f 4)

    if [ -z "$OLLAMA_URL" ]; then
        echo "ОШИБКА: Не удалось получить ссылку на релиз Ollama с GitHub API."
        exit 1
    fi

    FILENAME=$(basename "$OLLAMA_URL")
    echo "Скачиваем: $OLLAMA_URL"
    # Флаг -C - позволяет докачивать файл при обрыве связи
    curl -fL -C - "$OLLAMA_URL" -o "$BUNDLE_DIR/ollama/$FILENAME"
fi

echo "=== 4. Проверка и скачивание весов моделей (LLM + Embeddings) ==="
# Освобождаем порт 11434 на случай зависшего фонового процесса
pkill -f "ollama" 2>/dev/null || true
sleep 2

rm -rf /tmp/ollama_bin
mkdir -p /tmp/ollama_bin

if [[ "$FILENAME" == *.zst ]]; then
    tar --use-compress-program=unzstd -xf "$BUNDLE_DIR/ollama/$FILENAME" -C /tmp/ollama_bin
else
    tar -xzf "$BUNDLE_DIR/ollama/$FILENAME" -C /tmp/ollama_bin
fi

OLLAMA_EXEC=$(find /tmp/ollama_bin -type f -name "ollama" | head -n 1)
if [ -z "$OLLAMA_EXEC" ]; then
    echo "ОШИБКА: Исполняемый файл ollama не найден внутри архива."
    exit 1
fi
chmod +x "$OLLAMA_EXEC"

export OLLAMA_MODELS="$BUNDLE_DIR/models"
"$OLLAMA_EXEC" serve >/dev/null 2>&1 &
OLLAMA_PID=$!
sleep 4

LLM_MODEL="hf.co/bartowski/Qwen2.5-7B-Instruct-GGUF:Q4_K_M"
EMBED_MODEL="hf.co/BAAI/bge-m3-GGUF:Q8_0"

INSTALLED_MODELS=$("$OLLAMA_EXEC" list 2>/dev/null || true)

if echo "$INSTALLED_MODELS" | grep -q "Qwen2.5-7B-Instruct-GGUF"; then
    echo "[SKIP] Модель LLM ($LLM_MODEL) уже скачана."
else
    echo "Скачивание LLM: $LLM_MODEL..."
    "$OLLAMA_EXEC" pull "$LLM_MODEL"
fi

if echo "$INSTALLED_MODELS" | grep -q "bge-m3-GGUF"; then
    echo "[SKIP] Модель эмбеддингов ($EMBED_MODEL) уже скачана."
else
    echo "Скачивание Embeddings: $EMBED_MODEL..."
    "$OLLAMA_EXEC" pull "$EMBED_MODEL"
fi

echo "Итоговый список моделей в бандле:"
"$OLLAMA_EXEC" list

kill $OLLAMA_PID 2>/dev/null || true
rm -rf /tmp/ollama_bin

echo "=== 5. Генерация скриптов установки и запуска ==="
cat << 'EOF' > "$BUNDLE_DIR/install_offline.sh"
#!/bin/bash
set -e

BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
echo "=== Запуск оффлайн-установки в директории: $BASE_DIR ==="

echo "[1/4] Распаковка и установка Ollama..."
OLLAMA_ARCHIVE=$(ls "$BASE_DIR/ollama/"ollama-linux-amd64* 2>/dev/null | head -n 1)

if sudo -n true 2>/dev/null || [ "$EUID" -eq 0 ]; then
    OLLAMA_TARGET="/usr/local"
    SUDO_CMD="sudo"
else
    OLLAMA_TARGET="$BASE_DIR/ollama_bin"
    mkdir -p "$OLLAMA_TARGET"
    SUDO_CMD=""
fi

if [[ "$OLLAMA_ARCHIVE" == *.zst ]]; then
    $SUDO_CMD tar --use-compress-program=unzstd -xf "$OLLAMA_ARCHIVE" -C "$OLLAMA_TARGET"
else
    $SUDO_CMD tar -xzf "$OLLAMA_ARCHIVE" -C "$OLLAMA_TARGET"
fi

if [ ! -f "$OLLAMA_TARGET/bin/ollama" ] && [ -f "$OLLAMA_TARGET/ollama" ]; then
    $SUDO_CMD mkdir -p "$OLLAMA_TARGET/bin"
    $SUDO_CMD ln -sf "$OLLAMA_TARGET/ollama" "$OLLAMA_TARGET/bin/ollama"
fi

echo "[2/4] Создание виртуального окружения Python (venv)..."
python3 -m venv "$BASE_DIR/venv"
source "$BASE_DIR/venv/bin/activate"

echo "[3/4] Оффлайн-установка Python-зависимостей..."
pip install --no-index --find-links="$BASE_DIR/wheels" \
    playwright ollama chromadb pypdf python-docx beautifulsoup4 lxml \
    llama-index-core llama-index-llms-ollama llama-index-embeddings-ollama \
    llama-index-vector-stores-chroma llama-index-readers-file

echo "[4/4] Генерация скриптов окружения и запуска..."
cat << ENV > "$BASE_DIR/run_env.sh"
#!/bin/bash
export OLLAMA_MODELS="$BASE_DIR/models"
export PLAYWRIGHT_BROWSERS_PATH="$BASE_DIR/playwright_browsers"
export PATH="$BASE_DIR/ollama_bin/bin:\$PATH"
source "$BASE_DIR/venv/bin/activate"
ENV
chmod +x "$BASE_DIR/run_env.sh"

cat << 'START' > "$BASE_DIR/start_agent.sh"
#!/bin/bash
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$BASE_DIR/run_env.sh"

pkill -f "ollama" 2>/dev/null || true
sleep 1

echo "Запуск локального сервера Ollama..."
ollama serve > "$BASE_DIR/ollama.log" 2>&1 &
OLLAMA_PID=$!
trap "kill $OLLAMA_PID 2>/dev/null" EXIT

sleep 4
ollama list

echo "Запуск AI-агента..."
mkdir -p "$BASE_DIR/app/docs"
cd "$BASE_DIR/app"
python3 agent.py
START
chmod +x "$BASE_DIR/start_agent.sh"

echo "Установка завершена! Запускайте через: ./start_agent.sh"
EOF
chmod +x "$BUNDLE_DIR/install_offline.sh"

echo "=== 6. Упаковка бандла в offline_ai_agent_bundle.tar ==="
tar -cf offline_ai_agent_bundle.tar -C "$(dirname "$BUNDLE_DIR")" "$(basename "$BUNDLE_DIR")"
echo "Готово! Итоговый архив: $(realpath offline_ai_agent_bundle.tar)"
