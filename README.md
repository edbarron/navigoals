# 🧭 Navigoals – Personal Goal Tracker (CLI + Telegram Bot)

A productivity tool that helps you plan, manage, and track your tasks on a daily, weekly, and monthly basis.  
It features a **command‑line interface (CLI)** and a **Telegram bot** with inline buttons, so you can manage your goals from anywhere.

---

## ✨ Features

- **Task Management** – Add, update (Done/Failed/Moved/Cancelled), delete, and copy tasks – including multi‑select via comma‑separated IDs or `*` for "all".
- **Three Task Lists**:
  - **Daily Tasks** – tasks assigned to specific dates.
  - **Master List** – recurring tasks you perform frequently.
  - **Waiting List** – tasks without a specific deadline yet.
- **Efficiency Tracking** – Automatically calculates how effectively you complete tasks.
- **Reports & Analytics** – Daily, weekly, and monthly reports with completion metrics.
- **Telegram Bot Interface** – Full bot with inline buttons, accessible from your phone or desktop. Includes a main menu snapshot (yesterday/today/tomorrow, grouped by category) and a `/restart` command to recover the bot remotely.
- **Docker Support** – Run the bot continuously with Docker Compose (auto‑restart).
- **SQLite Persistence** – All tasks are stored locally; no data loss between sessions.

---

## 🛠️ Tech Stack

- Python 3.10+
- SQLite (local database)
- `tabulate` (table formatting for CLI)
- `python-telegram-bot` (Telegram bot interface)
- Docker & Docker Compose (optional, for bot hosting)

---

## 📦 Installation

### 1. Clone the repository
```bash
git clone https://github.com/edbarron/navigoals.git
cd navigoals
```

### 2. Set up a virtual environment (optional but recommended)
```bash
python3 -m venv venv
source venv/bin/activate   # On Windows: venv\Scripts\activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Initialise the database
```bash
python initialize_db.py
```

---

## 🖥️ Option A – Run the CLI locally

```bash
python main.py
```

The CLI offers:
- **Manage Tasks** – Add, update, delete, copy.
- **View Reports** – Daily, weekly, monthly efficiency reports.
- **Watch Lists** – View Master List, Waiting List, or tasks by date.

---

## 🤖 Option B – Run the Telegram Bot

The bot is **single‑user by design** – it only responds to one Telegram chat ID (set by you).  
To share Navigoals with others, they should clone the repo and run their own instance.

### 1. Create your bot
- Message [@BotFather](https://t.me/BotFather) on Telegram.
- Run `/newbot` and save the token.

### 2. Get your chat ID
- Message [@userinfobot](https://t.me/userinfobot) – it replies with your numeric ID instantly.

### 3. Set up environment variables
```bash
cp .env.example .env
```
Edit `.env` and fill in:
```env
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_numeric_chat_id
```

### 4. Run the bot (two options)

**Locally (without Docker):**
```bash
python bot.py
```

**With Docker Compose (recommended for 24/7 operation):**
```bash
docker compose up -d --build navigoals-bot
```

The bot runs in **long‑polling mode** – no public domain, HTTPS, or open port required. It just needs outbound internet access.

### 5. Start using the bot
Open your bot on Telegram and send `/start`.  
The bot provides inline buttons for all features. If it becomes unresponsive, send `/restart` to force a clean restart (Docker's `restart: unless-stopped` policy will bring it back up).

---

## 🧭 Telegram Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Show the main menu (snapshot of today/yesterday/tomorrow, grouped by category). |
| `/restart` | Exit the bot cleanly – useful if it becomes unresponsive. |

All other actions (Add/Update/Delete/Copy tasks, Reports, Watch Lists) are accessible via inline buttons.

---

## 📁 File Structure

```
navigoals/
├── main.py                # CLI core program
├── bot.py                 # Telegram bot interface
├── db_utils.py            # Database operations (add, update, delete, fetch)
├── utils.py               # Helper functions (time selection, efficiency, formatting)
├── initialize_db.py       # Database initialisation (runs schema.sql)
├── schema.sql             # Database schema (single source of truth)
├── .env                   # Environment variables (not tracked – contains tokens)
├── .env.example           # Example env file (copy to .env)
├── docker-compose.yml     # Docker services (bot + optional CLI)
├── Dockerfile             # Docker image definition
├── .dockerignore          # Files to exclude from Docker image
├── requirements.txt       # Python dependencies
├── navigoals.db           # SQLite database (auto‑generated)
└── README.md              # This file
```

---

## 📊 How It Works

1. **Daily Tasks** – Each task is assigned to a specific date. You can add, update, delete, or copy tasks between dates.
2. **Master List** – Stores long‑term or recurring tasks. You can copy them to specific days when needed.
3. **Waiting List** – Holds tasks that don't have a deadline yet. Copy them to a day when you're ready to work on them.
4. **Efficiency Tracking** – For each day, the bot calculates what percentage of tasks were completed (Done vs Failed/Moved/Cancelled).
5. **Reports** – View efficiency over a day, week, or month to track your productivity trends.

---

## 🧪 Testing

- Run the CLI with a small number of tasks first to familiarise yourself with the workflow.
- Use the Telegram bot in a private chat to test all features.

---

## 🔮 Future Improvements

- Optional multi‑user support (add a `user_id` column and scope all queries by chat/user).
- Notifications for upcoming tasks.
- Export reports to CSV or Excel.

---

## 📄 License

MIT – free to use, modify, and distribute.

---

## 🙏 Acknowledgements

Developed as the final project for Harvard's CS50 course.  
Special thanks to Professor David Malan and the CS50 staff.
