# Rahil-ob53-telegram-bot 🤖🎮

A high-performance **Free Fire Likes Telegram Bot** engineered with Python (`pyTelegramBotAPI`) and Flask, featuring an automated account session/token auto-refresh engine powered by the GitHub API. 

## 🌟 Key Features

* **Instant Likes Dispatch**: Send automated virtual likes directly to any Free Fire user ID (UID).
* **Robust Multi-Region Core**: Supports all pre-defined game servers (regions).
* **Automated Token Recovery**: Real-time JWT auto-refreshing via Garena's API with PyGithub synchronization.
* **Intelligent Webhook Router**: Integrated dynamic URL binding for both development environments and production servers like Render.
* **Owner Analytics Dashboard**: Track daily remaining API limit counts across all bot consumers dynamically using `/remain`.

---

## 📂 Repository File Structure

* **`main.py`**: The central bot engine managing Telegram commands (`/start`, `/like`, `/remain`, `/help`), Webhook/Polling workers, and Flask routes.
* **`token_refresh.py`**: Multi-layer JWT validation agent that automatically checks credentials, logs in, refreshes sessions, and pushes dynamic updates back to your GitHub repository safely.
* **`requirements.txt`**: Declares required Python package extensions (`pyTelegramBotAPI`, `requests`, `Flask`, `PyGithub`).
* **`README.md`**: Architectural manual and instructions.

---

## ⚙️ Setup & Deployment

1. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
