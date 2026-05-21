# Fitness Chatbot

This project is a Flask-based fitness chatbot that uses:

- Pinecone for vector storage
- Hugging Face embeddings for retrieval
- Gemini or Ollama for LLM inference
- Browser voice input/output for hands-free chat

## Setup

```bash
conda create -n fchatbot python=3.10 -y
conda activate fchatbot
pip install -r requirements.txt
```

## Environment Variables

Create a `.env` file with:

```env
PINECONE_API_KEY=your_pinecone_api_key
PINECONE_INDEX_NAME=fitness-chatbot
LLM_PROVIDER=gemini
GEMINI_MODEL=gemini-2.5-flash
GOOGLE_API_KEY=your_google_api_key
FLASK_SECRET_KEY=replace_with_a_secure_secret
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=llama3.1:8b
FLASK_DEBUG=false
```

`LLM_PROVIDER=gemini` is the recommended default for faster responses on low-spec machines.

If you want to keep using Ollama instead, set:

```env
LLM_PROVIDER=ollama
```

## Gemini Setup

1. Create a Gemini API key from [Google AI Studio](https://aistudio.google.com/).
2. Add it to `.env` as `GOOGLE_API_KEY`.
3. Keep `LLM_PROVIDER=gemini`.

Recommended model:

```env
GEMINI_MODEL=gemini-2.5-flash
```

## Chatbot Behavior

- Uses your PDF context when it finds relevant fitness information there
- Falls back to general fitness guidance when the question is outside the PDF
- Can help with BMI explanations, diet charts, Indian meal ideas, workouts, and common fitness questions
- Supports browser-based voice input and spoken responses on supported browsers
- Replies in English even if the user speaks or types in Hindi or Hinglish
- Can analyze uploaded food images and provide estimated nutrition values

## Ollama Setup

Install Ollama from [https://ollama.com](https://ollama.com), then pull a model:

```bash
ollama pull llama3.1:8b
```

You can also use smaller models like:

```bash
ollama pull qwen2.5:7b
ollama pull mistral
```

## Index Documents

Put your PDF files inside the `data/` folder, then run:

```bash
python store_index.py
```

## Start the App

```bash
python app.py
```

Open `http://127.0.0.1:5000` in your browser.
