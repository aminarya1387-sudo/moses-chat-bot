# Moses AI Chatbot

A Telegram assistant that remembers its users, searches the web, reports the news and generates images.

## Overview

Moses is a conversational assistant that lives in Telegram. What sets it apart from a simple wrapper around a language model is memory: it extracts facts about each user from the conversation, stores them with an importance score, and brings the relevant ones back in later chats.

It can also search the web and summarize the results, collect headlines from several news sources and write a full report on any one of them, and generate images from a text prompt.

## Features

- **Long-term memory.** Facts about each user are extracted, categorized and scored from one to ten for importance.
- **Semantic recall.** Past messages are embedded and stored in a vector database, so the bot finds related memories by meaning.
- **Web search.** Searches the web and returns a written summary of the results.
- **News reports.** Collects headlines from three international sources and writes a full report on the one the user taps.
- **Image generation.** Creates an image from a text description inside the chat.
- **Right to be forgotten.** One command deletes everything stored about the user, from both the database and the vector store.

## Engineering notes

- **Three memory layers working together.** Recent conversation history, structured facts in SQLite and semantic vectors in ChromaDB are merged into one context before each reply.
- **Fully asynchronous.** Database access through aiosqlite and network calls through an async HTTP client, so one slow request never blocks other users.
- **Degrades gracefully.** If the vector libraries are missing, the bot detects it at startup and keeps working with the other two layers.
- **Modular services.** Memory, web search, news, image generation and the model client are separate modules behind small interfaces.
- **Configuration outside the code.** Name, creator, description, version, model and keys come from environment variables.

## Architecture

| Layer | What it does |
| --- | --- |
| Telegram | Command handlers, inline keyboards, message handler |
| Orchestrator | Builds the prompt from system prompt, memory context and tools |
| Services | Memory manager, web search, news manager, image generator |
| Model | Gemini API client, sync and async |
| Storage | SQLite for facts and history, ChromaDB for vectors |

## Tech stack

- **Bot:** Python, python-telegram-bot 20, asyncio
- **AI:** Gemini API, Sentence embeddings, ChromaDB
- **Data and tools:** SQLite + aiosqlite, httpx, BeautifulSoup

## Run locally

Requires Python 3.10+.

```bash
pip install -r requirements.txt
```

Create a `.env` file with `TELEGRAM_BOT_TOKEN` and `GEMINI_API_KEY` (optional: `GEMINI_MODEL`, `BOT_NAME`, `BOT_CREATOR`), then:

```bash
python bot.py
```

## Author

Built by Amin.
