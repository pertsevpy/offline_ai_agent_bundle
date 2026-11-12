import os
import re
from pathlib import Path
import chromadb
import ollama
from pypdf import PdfReader
from docx import Document

# ================= НАСТРОЙКИ =================
DOCS_DIR = "./docs"                  # Папка с исходными документами (.pdf, .docx, .txt)
DB_DIR = "./exam_db"                 # Папка для сохранения векторной базы
COLLECTION_NAME = "exam_materials"   # Имя коллекции (должно совпадать с agent.py)

# Укажите точное имя модели эмбеддингов из `ollama list`
EMBED_MODEL = "hf.co/BAAI/bge-m3-GGUF:Q8_0"  # или "bge-m3"

CHUNK_SIZE = 1000                    # Размер фрагмента текста в символах
CHUNK_OVERLAP = 200                  # Перекрытие между фрагментами (чтобы не терять смысл на стыках)
REBUILD_DB = True                    # True = пересоздать базу с нуля; False = дописать новые файлы
# =============================================


def extract_text_from_txt(file_path: Path) -> str:
    for encoding in ("utf-8", "cp1251", "latin-1"):
        try:
            return file_path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return ""


def extract_text_from_pdf(file_path: Path) -> str:
    reader = PdfReader(str(file_path))
    pages_text = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages_text.append(text)
    return "\n".join(pages_text)


def extract_text_from_docx(file_path: Path) -> str:
    doc = Document(str(file_path))
    parts = [p.text for p in doc.paragraphs if p.text.strip()]
    # Также извлекаем текст из таблиц, так как в нормативных актах там часто бывают важные данные
    for table in doc.tables:
        for row in table.rows:
            row_text = " | ".join(cell.text.strip() for cell in row.cells if cell.text.strip())
            if row_text:
                parts.append(row_text)
    return "\n".join(parts)


def clean_text(text: str) -> str:
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def split_into_chunks(text: str, chunk_size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    """Разбивает текст на фрагменты с перекрытием, стараясь резать по границам предложений/абзацев."""
    if not text:
        return []

    chunks = []
    start = 0
    text_len = len(text)

    while start < text_len:
        end = start + chunk_size
        if end < text_len:
            # Ищем ближайший перенос строки или точку, чтобы не рвать слово пополам
            split_pos = max(
                text.rfind("\n", start + chunk_size // 2, end),
                text.rfind(". ", start + chunk_size // 2, end)
            )
            if split_pos != -1:
                end = split_pos + 1

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        if end >= text_len:
            break
        start = max(end - overlap, start + 1)

    return chunks


def main():
    docs_path = Path(DOCS_DIR)
    if not docs_path.exists():
        docs_path.mkdir(parents=True, exist_ok=True)
        print(f"Создана папка {DOCS_DIR}. Поместите туда .pdf, .docx или .txt файлы и перезапустите скрипт.")
        return

    supported_exts = {".pdf", ".docx", ".txt"}
    files = [f for f in docs_path.rglob("*") if f.is_file() and f.suffix.lower() in supported_exts]

    if not files:
        print(f"В папке {DOCS_DIR} не найдено файлов форматов {supported_exts}.")
        return

    print(f"Найдено документов для индексации: {len(files)}")
    db_client = chromadb.PersistentClient(path=DB_DIR)

    if REBUILD_DB:
        try:
            db_client.delete_collection(name=COLLECTION_NAME)
            print(f"Старая коллекция '{COLLECTION_NAME}' очищена.")
        except Exception:
            pass

    collection = db_client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"}
    )

    total_chunks = 0

    for file_idx, file_path in enumerate(files, start=1):
        ext = file_path.suffix.lower()
        print(f"[{file_idx}/{len(files)}] Обработка: {file_path.name}...", end=" ", flush=True)

        try:
            if ext == ".pdf":
                raw_text = extract_text_from_pdf(file_path)
            elif ext == ".docx":
                raw_text = extract_text_from_docx(file_path)
            else:
                raw_text = extract_text_from_txt(file_path)
        except Exception as e:
            print(f"ОШИБКА чтения: {e}")
            continue

        cleaned = clean_text(raw_text)
        chunks = split_into_chunks(cleaned)

        if not chunks:
            print("пропущен (пустой текст).")
            continue

        ids = []
        embeddings = []
        documents = []
        metadatas = []

        for chunk_idx, chunk in enumerate(chunks):
            # Добавляем название источника в начало фрагмента для точного поиска по номеру ФЗ/ПП
            enriched_chunk = f"[Источник: {file_path.name}]\n{chunk}"
            resp = ollama.embeddings(model=EMBED_MODEL, prompt=enriched_chunk)

            ids.append(f"{file_path.stem}_{file_idx}_{chunk_idx}")
            embeddings.append(resp["embedding"])
            documents.append(enriched_chunk)
            metadatas.append({"source": file_path.name, "chunk": chunk_idx})

        collection.add(
            ids=ids,
            embeddings=embeddings,
            documents=documents,
            metadatas=metadatas
        )

        total_chunks += len(chunks)
        print(f"OK ({len(chunks)} фрагм.)")

    print("\n========================================================")
    print(f"Индексация завершена! Всего сохранено фрагментов: {total_chunks}")
    print(f"База знаний готова в директории: {os.path.abspath(DB_DIR)}")
    print("========================================================")


if __name__ == "__main__":
    main()
