from flask import Flask, jsonify, render_template, request, session
from dotenv import load_dotenv
from langchain_core.messages import HumanMessage
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_ollama import OllamaLLM
from langchain_pinecone import PineconeVectorStore
from pinecone import Pinecone
import base64
import urllib.parse
import re
import os

from src.helper import download_hugging_face_embeddings
from src.prompt import prompt_template


app = Flask(__name__)

load_dotenv()
app.secret_key = os.getenv("FLASK_SECRET_KEY", "fitbuddy-dev-secret")

PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
INDEX_NAME = os.getenv("PINECONE_INDEX_NAME", "fitness-chatbot")
LLM_PROVIDER = os.getenv("LLM_PROVIDER", "gemini").lower()
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.1:8b")
RETRIEVAL_K = int(os.getenv("RETRIEVAL_K", "3"))
RELEVANCE_THRESHOLD = float(os.getenv("RELEVANCE_THRESHOLD", "0.45"))
MAX_CHAT_TURNS = int(os.getenv("MAX_CHAT_TURNS", "6"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

prompt = PromptTemplate(
    template=prompt_template,
    input_variables=["chat_history", "context", "question"],
)

_embeddings = None
_docsearch = None
_llm = None


def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = download_hugging_face_embeddings()
    return _embeddings


def get_docsearch():
    global _docsearch
    if _docsearch is None:
        pc = Pinecone(api_key=PINECONE_API_KEY)
        _docsearch = PineconeVectorStore.from_existing_index(
            index_name=INDEX_NAME,
            embedding=get_embeddings(),
        )
    return _docsearch


def get_llm():
    global _llm
    if _llm is None:
        if LLM_PROVIDER == "gemini":
            _llm = ChatGoogleGenerativeAI(
                model=GEMINI_MODEL,
                temperature=0.2,
            )
        else:
            _llm = OllamaLLM(
                model=OLLAMA_MODEL,
                base_url=OLLAMA_BASE_URL,
                temperature=0.2,
                num_predict=80,
                num_ctx=1024,
                keep_alive="10m",
            )
    return _llm

def get_relevant_context(query):
    """Return joined document context only when the match score is strong enough."""
    matches = get_docsearch().similarity_search_with_score(query, k=RETRIEVAL_K)
    relevant_docs = []

    for doc, score in matches:
        if score >= RELEVANCE_THRESHOLD:
            relevant_docs.append(doc.page_content.strip())

    if not relevant_docs:
        return "No relevant PDF context found."

    return "\n\n".join(relevant_docs)


def generate_answer(user_input):
    greeting_response = get_greeting_response(user_input)
    if greeting_response:
        return greeting_response

    context = get_relevant_context(user_input)
    formatted_prompt = prompt.format(
        chat_history=format_chat_history(),
        context=context,
        question=user_input,
    )
    response = get_llm().invoke(formatted_prompt)
    answer = response.content if hasattr(response, "content") else str(response)
    final_answer = sanitize_response_text(ensure_english_response(answer))
    return append_video_links_if_requested(user_input, final_answer)


def generate_answer_with_image(user_input, image_bytes, mime_type):
    context = get_relevant_context(user_input)
    formatted_prompt = prompt.format(
        chat_history=format_chat_history(),
        context=context,
        question=user_input or "Analyze this food image and help the user with fitness and nutrition guidance.",
    )

    if LLM_PROVIDER != "gemini":
        raise ValueError("Image analysis is available only when LLM_PROVIDER is set to gemini.")

    image_base64 = base64.b64encode(image_bytes).decode("utf-8")
    message = HumanMessage(
        content=[
            {"type": "text", "text": formatted_prompt},
            {
                "type": "image_url",
                "image_url": f"data:{mime_type};base64,{image_base64}",
            },
        ]
    )
    response = get_llm().invoke([message])
    answer = response.content if hasattr(response, "content") else str(response)
    final_answer = sanitize_response_text(ensure_english_response(answer))
    return append_video_links_if_requested(user_input, final_answer)


def format_chat_history():
    history = session.get("chat_history", [])
    if not history:
        return "No previous conversation."

    lines = []
    for message in history[-(MAX_CHAT_TURNS * 2):]:
        role = message.get("role", "user").capitalize()
        content = message.get("content", "").strip()
        if content:
            lines.append(f"{role}: {content}")

    return "\n".join(lines) if lines else "No previous conversation."


def update_chat_history(user_input, assistant_reply):
    history = session.get("chat_history", [])
    history.append({"role": "user", "content": user_input})
    history.append({"role": "assistant", "content": assistant_reply})
    session["chat_history"] = history[-(MAX_CHAT_TURNS * 2):]


def ensure_english_response(answer):
    """Force the final user-facing answer to stay in English."""
    if not answer:
        return answer

    has_devanagari = bool(re.search(r"[\u0900-\u097F]", answer))
    if not has_devanagari:
        return answer

    rewrite_prompt = (
        "Rewrite the following response in clear, natural English only. "
        "Keep the meaning, structure, calculations, and recommendations the same. "
        "Do not add extra advice. Remove markdown and decorative symbols.\n\n"
        f"Response:\n{answer}"
    )
    rewritten = get_llm().invoke(rewrite_prompt)
    rewritten_text = rewritten.content if hasattr(rewritten, "content") else str(rewritten)
    return sanitize_response_text(rewritten_text)


def get_greeting_response(user_input):
    normalized = re.sub(r"[^a-zA-Z\s]", "", user_input).strip().lower()
    greeting_phrases = {
        "hi fitbuddy",
        "hello fitbuddy",
        "hey fitbuddy",
        "hi firbuddy",
        "hello firbuddy",
        "hey firbuddy",
    }

    if normalized not in greeting_phrases:
        return None

    user = session.get("user")
    if user and user.get("name"):
        first_name = user["name"].split()[0]
        return f"Hello {first_name}, how can I help you?"

    return "Hello, how can I help you?"


def sanitize_response_text(answer):
    """Remove markdown-style formatting so chat output stays clean plain text."""
    if not answer:
        return answer

    cleaned = answer.replace("**", "")
    cleaned = re.sub(r"^[\*\-\•]\s+", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"`([^`]*)`", r"\1", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
    return cleaned


def append_video_links_if_requested(user_input, answer):
    if "video" not in user_input.lower():
        return answer

    if "youtube.com" in answer.lower() or "youtu.be" in answer.lower():
        return answer

    topics = infer_video_topics(user_input, answer)
    if not topics:
        return answer

    links = []
    for topic in topics[:4]:
        query = urllib.parse.quote_plus(f"{topic} exercise tutorial beginner")
        links.append(f"{topic}: https://www.youtube.com/results?search_query={query}")

    return f"{answer}\n\nSuggested video links:\n" + "\n".join(links)


def infer_video_topics(user_input, answer):
    source_text = f"{user_input}\n{answer}".lower()
    topic_map = {
        "push up": "Push Up",
        "push-up": "Push Up",
        "squat": "Bodyweight Squat",
        "lunges": "Lunges",
        "lunge": "Lunges",
        "plank": "Plank",
        "burpee": "Burpee",
        "jumping jack": "Jumping Jacks",
        "deadlift": "Deadlift",
        "bench press": "Bench Press",
        "shoulder press": "Shoulder Press",
        "lat pulldown": "Lat Pulldown",
        "bicep curl": "Bicep Curl",
        "tricep dip": "Tricep Dip",
        "mountain climber": "Mountain Climbers",
        "surya namaskar": "Surya Namaskar",
        "warm up": "Warm Up Routine",
        "warmup": "Warm Up Routine",
        "cardio": "Beginner Cardio Workout",
        "fat loss": "Beginner Fat Loss Workout",
        "muscle gain": "Beginner Muscle Gain Workout",
        "home workout": "Beginner Home Workout",
    }

    topics = []
    for key, label in topic_map.items():
        if key in source_text and label not in topics:
            topics.append(label)

    return topics


@app.route("/")
def index():
    return render_template("chat.html")


@app.route("/get", methods=["POST"])
def chat():
    user_input = request.form.get("msg", "").strip()
    uploaded_image = request.files.get("image")

    if not user_input and (uploaded_image is None or not uploaded_image.filename):
        return jsonify({"message": "Please enter a valid question."}), 400

    try:
        if uploaded_image and uploaded_image.filename:
            mime_type = uploaded_image.mimetype or "image/jpeg"
            image_bytes = uploaded_image.read()
            answer = generate_answer_with_image(user_input, image_bytes, mime_type)
            history_input = user_input or f"Uploaded image for analysis ({uploaded_image.filename})"
        else:
            answer = generate_answer(user_input)
            history_input = user_input

        update_chat_history(history_input, answer)
        return jsonify({"answer": answer})
    except Exception as exc:
        return jsonify({"message": f"Error: {str(exc)}"}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=FLASK_DEBUG)
