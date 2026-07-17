import os
os.environ["USE_TF"] = "0"

import re
import pickle
import numpy as np
import faiss

from typing import Any, Text, Dict, List
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import SlotSet #added for followup

from PyPDF2 import PdfReader
from docx import Document
from sentence_transformers import SentenceTransformer
from openai import OpenAI


BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(os.path.abspath(__file__))
    )
)

os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "600"
os.environ["HF_HUB_ETAG_TIMEOUT"] = "600"
os.environ["HF_HUB_ENABLE_HF_TRANSFER"] = "0"
os.environ["HF_HOME"] = os.path.join(BASE_DIR, "local_models", "hf_home")
os.environ["TRANSFORMERS_CACHE"] = os.path.join(BASE_DIR, "local_models", "transformers_cache")
os.environ["SENTENCE_TRANSFORMERS_HOME"] = os.path.join(BASE_DIR, "local_models", "sentence_transformers")


DOC_FOLDER = os.path.join(BASE_DIR, "documents")
MODEL_FOLDER = os.path.join(BASE_DIR, "local_models")
DB_FOLDER = os.path.join(BASE_DIR, "vector_store")

EMBEDDING_MODEL_NAME = "paraphrase-MiniLM-L3-v2"
OPENAI_MODEL = "gpt-4.1-mini"

INDEX_FILE = os.path.join(DB_FOLDER, "vector_db.index")
CHUNKS_FILE = os.path.join(DB_FOLDER, "chunks.pkl")

client = OpenAI()


# print("RAG BASE_DIR:", BASE_DIR)
# print("RAG DOC_FOLDER:", DOC_FOLDER)
# print("RAG MODEL_FOLDER:", MODEL_FOLDER)
# print("RAG DB_FOLDER:", DB_FOLDER)


def load_embedding_model():
    path = os.path.join(MODEL_FOLDER, "embedding_model")
    return SentenceTransformer(
        EMBEDDING_MODEL_NAME,
        cache_folder=path
    )


def read_pdf(path):
    text = ""
    reader = PdfReader(path)

    for page in reader.pages:
        page_text = page.extract_text() or ""
        text += page_text + "\n\n"

    # print("Extracted text length from PDF:", len(text))

    return text


def read_docx(path):
    doc = Document(path)
    text = ""

    for para in doc.paragraphs:
        text += para.text + "\n"

    return text


def clean_text(text):
    text = re.sub(r"\.{3,}", " ", text)
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s+-\s+", "-", text)
    return text.strip()


def is_bad_chunk(chunk):
    lower_text = chunk.lower().strip()

    if "revision history" in lower_text:
        return True

    if lower_text.startswith("ver no.") or lower_text.startswith("draft original document"):
        return True

    if len(chunk.split()) < 5:
        return True

    return False


def split_into_chunks(text, chunk_size=120, overlap=30):
    words = text.split()
    chunks = []

    # print("Total words in document:", len(words))

    if len(words) == 0:
        return chunks

    start = 0

    while start < len(words):
        end = start + chunk_size
        chunk = " ".join(words[start:end])
        chunk = clean_text(chunk)

        if chunk:
            if not is_bad_chunk(chunk):
                chunks.append(chunk)
            else:
                # print("Skipped bad chunk:", chunk[:100])
                pass

        start += chunk_size - overlap

    return chunks


def load_documents():
    chunks = []

    if not os.path.exists(DOC_FOLDER):
        os.makedirs(DOC_FOLDER)
        # print("documents folder created:", DOC_FOLDER)
        return chunks

    # print("Files in documents:", os.listdir(DOC_FOLDER))

    for filename in os.listdir(DOC_FOLDER):
        path = os.path.join(DOC_FOLDER, filename)

        try:
            # print("Reading file:", filename)

            if filename.lower().endswith(".pdf"):
                text = read_pdf(path)
            elif filename.lower().endswith(".docx"):
                text = read_docx(path)
            else:
                continue

            text = clean_text(text)
            file_chunks = split_into_chunks(text)

            # print("Chunks from", filename, ":", len(file_chunks))

            for chunk in file_chunks:
                chunks.append({
                    "file": filename,
                    "text": chunk
                })

        except Exception as e:
            print("Error reading", filename, ":", e)

    # print("Total chunks created:", len(chunks))
    return chunks


embedding_model = load_embedding_model()


def create_vector_db(chunks):
    texts = [chunk["text"] for chunk in chunks]

    embeddings = embedding_model.encode(texts)
    embeddings = np.array(embeddings).astype("float32")

    faiss.normalize_L2(embeddings)

    dimension = embeddings.shape[1]
    index = faiss.IndexFlatIP(dimension)

    index.add(embeddings)

    return index


def save_vector_db(index, chunks):
    if not os.path.exists(DB_FOLDER):
        os.makedirs(DB_FOLDER)

    faiss.write_index(index, INDEX_FILE)

    with open(CHUNKS_FILE, "wb") as f:
        pickle.dump(chunks, f)

    # print("Vector DB saved:")
    # print("Index:", INDEX_FILE, os.path.exists(INDEX_FILE))
    # print("Chunks:", CHUNKS_FILE, os.path.exists(CHUNKS_FILE))


def load_vector_db():
    index = faiss.read_index(INDEX_FILE)

    with open(CHUNKS_FILE, "rb") as f:
        chunks = pickle.load(f)

    # print("Loaded vector DB. Chunks:", len(chunks))
    return index, chunks


def build_or_load_vector_db():
    # print("RAG INDEX_FILE:", INDEX_FILE)
    # print("RAG CHUNKS_FILE:", CHUNKS_FILE)

    if os.path.exists(INDEX_FILE) and os.path.exists(CHUNKS_FILE):
        print("Loading existing vector database...")
        return load_vector_db()

    print("Creating new vector database...")

    chunks = load_documents()

    if not chunks:
        print("No chunks created. Check documents folder and PDF/DOCX content.")
        return None, []

    index = create_vector_db(chunks)
    save_vector_db(index, chunks)

    return index, chunks


def rag_rebuild_vector_db():
    if os.path.exists(INDEX_FILE):
        os.remove(INDEX_FILE)

    if os.path.exists(CHUNKS_FILE):
        os.remove(CHUNKS_FILE)

    return build_or_load_vector_db()


rag_index, rag_chunks = build_or_load_vector_db()


def retrieve_chunks(question, index, chunks, top_k=8, final_k=4):
    question_embedding = embedding_model.encode([question])
    question_embedding = np.array(question_embedding).astype("float32")

    faiss.normalize_L2(question_embedding)

    scores, indexes = index.search(question_embedding, top_k)

    results = []

    for score, idx in zip(scores[0], indexes[0]):
        if idx < len(chunks) and score > 0.20:
            chunk = chunks[idx]
            results.append({
                "score": float(score),
                "file": chunk["file"],
                "text": chunk["text"]
            })

    return results[:final_k]


def build_context(retrieved_chunks):
    context_parts = []

    for i, chunk in enumerate(retrieved_chunks, 1):
        context_parts.append(
            "Source {} [{}]:\n{}".format(
                i,
                chunk["file"],
                chunk["text"]
            )
        )

    return "\n\n".join(context_parts)


def generate_answer(question, retrieved_chunks):
    try:
        if not retrieved_chunks:
            return {
                "answer": "I could not find this information in the documents.",
                "source": None
            }

        context = build_context(retrieved_chunks)

        response = client.responses.create(
            model=OPENAI_MODEL,
            input=[
                {
                    "role": "system",
                    "content": (
                        "You are an internal company policy assistant. "
                        "Answer only using the provided policy context. "
                        "If the answer is not available in the context, say: "
                        "'I could not find this information in the documents.' "
                        "Keep the answer clear, concise, and professional. "
                        "Do not make assumptions."
                    )
                },
                {
                    "role": "user",
                    "content": (
                        "Context:\n{}\n\nQuestion:\n{}".format(
                            context,
                            question
                        )
                    )
                }
            ],
            temperature=0.2,
            max_output_tokens=300
        )

        answer = response.output_text.strip()

        sources = []

        for chunk in retrieved_chunks:
            if chunk["file"] not in sources:
                sources.append(chunk["file"])

        return {
            "answer": answer,
            "source": ", ".join(sources)
        }

    except Exception as e:
        print("OpenAI Generation Error:", str(e))

        return {
            "answer": "The AI service encountered an issue while generating the answer.",
            "source": None
        }


def get_rag_answer(question):
    global rag_index
    global rag_chunks

    if rag_index is None or not rag_chunks:
        return "I could not find any policy documents. Please add documents and rebuild the RAG database."

    retrieved_chunks = retrieve_chunks(
        question,
        rag_index,
        rag_chunks,
        top_k=8,
        final_k=4
    )

    result = generate_answer(question, retrieved_chunks)

    if result["source"]:
        return "{}\n\nSource: {}".format(
            result["answer"],
            result["source"]
        )

    return result["answer"]

# ****************************************** folloups for testing ******************************************
# class ActionRagAnswer(Action):

#     def name(self) -> Text:
#         return "action_rag_answer"

#     def run(
#         self,
#         dispatcher: CollectingDispatcher,
#         tracker: Tracker,
#         domain: Dict[Text, Any]
#     ) -> List[Dict[Text, Any]]:

#         user_question = tracker.latest_message.get("text")

#         answer = get_rag_answer(user_question)

#         dispatcher.utter_message(text=answer)

#         return []


class ActionRagAnswer(Action):

    def name(self) -> Text:
        return "action_rag_answer"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        print("Running ActionRagAnswer...")

        user_question = tracker.latest_message.get("text") or ""
        user_question_clean = user_question.strip()

        last_rag_question = tracker.get_slot("last_rag_question")
        last_policy_name = tracker.get_slot("last_policy_name")

        current_policy_name = next(
            tracker.get_latest_entity_values("policy_name"),
            None
        )

        if current_policy_name:
            last_policy_name = current_policy_name

        followup_words = [
            "what about",
            "how about",
            "and",
            "also",
            "what is the limit",
            "what is the approval",
            "who approves",
            "explain more",
            "tell me more",
            "give more details",
            "what are the rules",
            "is it allowed",
            "can i claim",
            "what documents",
            "within how many days",
            "what happens if",
        ]

        lower_question = user_question_clean.lower()

        is_followup = (
            last_rag_question
            and (
                len(user_question_clean.split()) <= 8
                or any(word in lower_question for word in followup_words)
            )
        )

        if is_followup:
            if last_policy_name:
                final_question = (
                    f"Previous policy/topic: {last_policy_name}. "
                    f"Previous question: {last_rag_question}. "
                    f"Follow-up question: {user_question_clean}"
                )
            else:
                final_question = (
                    f"Previous question: {last_rag_question}. "
                    f"Follow-up question: {user_question_clean}"
                )
        else:
            final_question = user_question_clean

        answer = get_rag_answer(final_question)

        dispatcher.utter_message(text=answer)

        return [
            SlotSet("last_rag_question", final_question),
            SlotSet("last_policy_name", last_policy_name),
        ]
    
# ****************************************** end of folloups for testing *****************************************




class ActionRagRebuild(Action):

    def name(self) -> Text:
        return "action_rag_rebuild"

    def run(
        self,
        dispatcher: CollectingDispatcher,
        tracker: Tracker,
        domain: Dict[Text, Any]
    ) -> List[Dict[Text, Any]]:

        print("Running ActionRagRebuild...")

        global rag_index
        global rag_chunks

        rag_index, rag_chunks = rag_rebuild_vector_db()

        dispatcher.utter_message(
            text="RAG vector database has been rebuilt successfully."
        )

        return []