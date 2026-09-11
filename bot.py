"""
Navigoals Telegram bot.

A single-user Telegram front-end for the same db_utils/utils logic used by
main.py (the CLI). It only responds to the chat ID in TELEGRAM_CHAT_ID.

Required environment variables:
    TELEGRAM_BOT_TOKEN  - token from @BotFather
    TELEGRAM_CHAT_ID    - your numeric Telegram chat ID (from @userinfobot)
"""

import datetime
import logging
import os
import re

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

from db_utils import (
    add_task,
    delete_daily_task,
    delete_task,
    get_master_list,
    get_tasks_by_date,
    get_tasks_by_range,
    get_waiting_list,
    update_task_status,
)
from utils import calculate_efficiency, status_label

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
_raw_chat_id = os.environ.get("TELEGRAM_CHAT_ID")
AUTHORIZED_CHAT_ID = int(_raw_chat_id) if _raw_chat_id else None

CATEGORIES = {
    "work": "Work 💼",
    "study": "Study 📘",
    "social": "Social 👥",
    "personal": "Personal 🏠",
}

STATUS_CHOICES = {
    "done": "Done ✅",
    "failed": "Failed ❌",
    "moved": "Moved 📦",
    "cancelled": "Cancelled 🚫",
}

STATUS_ICON = {
    "pending": "⏳",
    "done": "✅",
    "failed": "❌",
    "moved": "📦",
    "cancelled": "🚫",
}

DAY_DIVIDER = "━━━━━━━━━━━━━━━━━━━"

TABLE_LABELS = {
    "tasks": "Daily Tasks",
    "master_list": "Master List",
    "waiting_list": "Waiting List",
}


# --------------------------------------------------------------------------
# Auth guard
# --------------------------------------------------------------------------

async def _authorized(update: Update) -> bool:
    """Return True if the update comes from the allowed chat; otherwise ignore it."""
    chat_id = update.effective_chat.id if update.effective_chat else None
    if AUTHORIZED_CHAT_ID is None:
        logger.warning("TELEGRAM_CHAT_ID not set — refusing all requests.")
        return False
    if chat_id != AUTHORIZED_CHAT_ID:
        logger.warning("Ignored message from unauthorized chat_id=%s", chat_id)
        return False
    return True


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def _today():
    return datetime.date.today()


def _strip_ansi(text: str) -> str:
    """Remove terminal ANSI color codes (e.g. from calculate_efficiency's 'emoji'
    field). Those codes contain unescaped '[' characters, which Telegram's
    Markdown parser reads as a broken link and rejects the whole message."""
    return re.sub(r"\x1b\[[0-9;]*m", "", text)


def _code_safe(text: str) -> str:
    """Neutralize backticks so user text can't break a ``` code block."""
    return text.replace("`", "'")


def _code(text: str) -> str:
    """Render arbitrary user text as an inline code span — safe under Markdown
    parse mode regardless of underscores, asterisks, or brackets in the text."""
    return f"`{_code_safe(text)}`"


def _fmt_task_rows(tasks, with_status=True):
    """Plain-text list of task rows (id kept, since these are used in
    Watch Lists, Reports, and the Update/Delete/Copy selection prompts)."""
    if not tasks:
        return "_No tasks._"
    lines = []
    for t in tasks:
        name = _code_safe(t[1])
        if with_status:
            # (daily_id, name, category, status)
            lines.append(f"{t[0]}. {name} — {t[2]} — {status_label(t[3])}")
        else:
            # (id, name, category)
            lines.append(f"{t[0]}. {name} — {t[2]}")
    return "\n".join(lines)


CATEGORY_ORDER = list(CATEGORIES.values())  # Work, Study, Social, Personal


def _fmt_grouped_tasks(tasks):
    """Main-menu-only display: tasks grouped under category headers, no IDs
    (nothing is selected from here), no code block — meant to read as a
    clean list rather than a table."""
    if not tasks:
        return "No goals 📥"

    groups = {}
    for t in tasks:
        groups.setdefault(t[2], []).append(t)

    ordered_cats = list(CATEGORY_ORDER) + [c for c in groups if c not in CATEGORY_ORDER]

    blocks = []
    for cat in ordered_cats:
        items = groups.get(cat)
        if not items:
            continue
        rows = "\n".join(
            f"{STATUS_ICON.get(t[3], '•')} {_code_safe(t[1])}" for t in items
        )
        blocks.append(f"*{cat}*\n{rows}")

    return "\n\n".join(blocks)


def _parse_selection(text, valid_ids):
    """Parse '1,3,5' or '*' into a list of ids present in valid_ids.
    Returns None if the input is invalid or matches nothing."""
    text = text.strip()
    valid_set = set(valid_ids)
    if text == "*":
        return list(valid_ids)
    try:
        ids = [int(x.strip()) for x in text.split(",") if x.strip()]
    except ValueError:
        return None
    selected = [i for i in ids if i in valid_set]
    return selected if selected else None


async def _send_or_edit(update: Update, text: str, keyboard=None):
    """Reply with a new message if triggered by text, or edit if from a button tap.
    Always degrades gracefully: if Markdown parsing fails for any reason, falls
    back to plain text rather than leaving the user with no response at all."""
    markup = InlineKeyboardMarkup(keyboard) if keyboard else None

    if update.callback_query:
        try:
            await update.callback_query.edit_message_text(
                text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN
            )
            return
        except BadRequest as e:
            if "Message is not modified" in str(e):
                return
            logger.warning("edit_message_text failed (%s) — sending a new message instead.", e)
        target = update.callback_query.message.reply_text
    else:
        target = update.message.reply_text

    try:
        await target(text, reply_markup=markup, parse_mode=ParseMode.MARKDOWN)
    except BadRequest as e:
        logger.warning("Markdown send failed (%s) — falling back to plain text.", e)
        await target(text, reply_markup=markup)


# --------------------------------------------------------------------------
# Main menu
# --------------------------------------------------------------------------

async def show_main_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()

    lines = ["🌟 *Navigoals* 🌟\n"]
    days = [(-1, "Yesterday"), (0, "Today"), (1, "Tomorrow")]
    for i, (delta, label) in enumerate(days):
        day = _today() + datetime.timedelta(days=delta)
        day_str = day.isoformat()
        tasks = get_tasks_by_date(day_str)
        lines.append(f"📅 *{label}* ({day_str})")
        if tasks:
            if delta <= 0:
                metrics = calculate_efficiency(tasks)
                lines.append(f"Efficiency: {metrics['efficiency']:.0f}% {_strip_ansi(metrics['emoji'])}")
            else:
                lines.append(f"Planned: {len(tasks)} task(s)")
            lines.append(_fmt_grouped_tasks(tasks))
        else:
            lines.append("No goals 📥")
        if i < len(days) - 1:
            lines.append("")
            lines.append(DAY_DIVIDER)
        lines.append("")

    keyboard = [
        [InlineKeyboardButton("📝 Manage Tasks", callback_data="manage")],
        [InlineKeyboardButton("📊 View Reports", callback_data="reports")],
        [InlineKeyboardButton("👁️ Watch Lists", callback_data="watch")],
    ]
    await _send_or_edit(update, "\n".join(lines), keyboard)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _authorized(update):
        return
    await show_main_menu(update, context)


async def cmd_restart(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _authorized(update):
        return
    await update.message.reply_text("🔄 Restarting the bot... give it a few seconds and send /start.")
    logger.info("Restart requested via /restart — exiting so Docker restarts the container.")
    os._exit(1)


# --------------------------------------------------------------------------
# Manage Tasks menu
# --------------------------------------------------------------------------

async def show_manage_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("➕ Add Task", callback_data="add:start")],
        [InlineKeyboardButton("✏️ Update Task(s)", callback_data="update:start")],
        [InlineKeyboardButton("🗑️ Delete Task(s)", callback_data="delete:start")],
        [InlineKeyboardButton("📋 Copy Task(s)", callback_data="copy:start")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main")],
    ]
    await _send_or_edit(update, "📝 *Task Management*", keyboard)


def _selection_prompt(tasks, with_status=True):
    return (
        f"{_fmt_task_rows(tasks, with_status=with_status)}\n\n"
        "Send the IDs you want, comma-separated (e.g. `1,3`), or `*` for all."
    )


# ---- Add task flow --------------------------------------------------------

async def add_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Daily Tasks", callback_data="add:list:daily")],
        [InlineKeyboardButton("📚 Master List", callback_data="add:list:master")],
        [InlineKeyboardButton("⏳ Waiting List", callback_data="add:list:waiting")],
        [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
    ]
    await _send_or_edit(update, "➕ *Add Task*\nWhere should this task go?", keyboard)


async def add_list_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, list_type: str):
    context.user_data["add_list"] = list_type
    context.user_data["awaiting"] = "add_task_name"
    await _send_or_edit(update, "Send me the task name as a text message.")


async def add_task_name_received(update: Update, context: ContextTypes.DEFAULT_TYPE, name: str):
    context.user_data["add_name"] = name
    context.user_data["awaiting"] = None
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"add:cat:{key}")]
        for key, label in CATEGORIES.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="manage")])
    await _send_or_edit(update, f"Category for {_code(name)}:", keyboard)


async def add_category_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, cat_key: str):
    category = CATEGORIES[cat_key]
    context.user_data["add_category"] = category
    list_type = context.user_data.get("add_list")

    if list_type == "daily":
        keyboard = [
            [InlineKeyboardButton("Today", callback_data="add:date:today")],
            [InlineKeyboardButton("Tomorrow", callback_data="add:date:tomorrow")],
            [InlineKeyboardButton("✏️ Custom date", callback_data="add:date:custom")],
        ]
        await _send_or_edit(update, "When should this task be scheduled?", keyboard)
        return

    name = context.user_data.get("add_name")
    add_task(name, category, list_type=list_type)
    label = "Master List" if list_type == "master" else "Waiting List"
    await _send_or_edit(
        update,
        f"✅ {_code(name)} added to the {label}.",
        [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main")]],
    )


async def add_date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    if choice == "custom":
        context.user_data["awaiting"] = "add_custom_date"
        await _send_or_edit(update, "Send the date as `YYYY-MM-DD`.")
        return

    day = _today() if choice == "today" else _today() + datetime.timedelta(days=1)
    await _finish_add_daily(update, context, day.isoformat())


async def add_custom_date_received(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        datetime.datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD and try again.")
        return
    context.user_data["awaiting"] = None
    await _finish_add_daily(update, context, text)


async def _finish_add_daily(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str):
    name = context.user_data.get("add_name")
    category = context.user_data.get("add_category")
    add_task(name, category, date_str, list_type="daily")
    await _send_or_edit(
        update,
        f"✅ {_code(name)} added for {date_str}.",
        [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main")]],
    )


# ---- Update task flow (multi-select) ---------------------------------------

async def update_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("Today", callback_data="update:day:today")],
        [InlineKeyboardButton("Yesterday", callback_data="update:day:yesterday")],
        [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
    ]
    await _send_or_edit(update, "✏️ *Update Task(s)*\nWhich day?", keyboard)


async def update_day_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    day = _today() if choice == "today" else _today() - datetime.timedelta(days=1)
    date_str = day.isoformat()
    tasks = get_tasks_by_date(date_str)
    if not tasks:
        await _send_or_edit(
            update, "No tasks for that day.", [[InlineKeyboardButton("⬅️ Back", callback_data="manage")]]
        )
        return

    context.user_data["update_date"] = date_str
    context.user_data["awaiting"] = "update_select_ids"
    await _send_or_edit(update, f"Tasks for {date_str}:\n\n{_selection_prompt(tasks)}")


async def update_ids_received(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    date_str = context.user_data.get("update_date")
    tasks = get_tasks_by_date(date_str)
    valid_ids = [t[0] for t in tasks]
    selected = _parse_selection(text, valid_ids)
    if not selected:
        await update.message.reply_text(
            "❌ No valid IDs found in that input. Try again (e.g. `1,3` or `*`)."
        )
        return

    context.user_data["update_ids"] = selected
    context.user_data["awaiting"] = None
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"update:status:{key}")]
        for key, label in STATUS_CHOICES.items()
    ]
    keyboard.append([InlineKeyboardButton("⬅️ Back", callback_data="manage")])
    await update.message.reply_text(
        f"Selected {len(selected)} task(s). New status for all of them?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def update_status_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, status_key: str):
    date_str = context.user_data.get("update_date")
    ids = context.user_data.get("update_ids", [])
    for daily_id in ids:
        update_task_status(daily_id, status_key, date_str)
    await _send_or_edit(
        update,
        f"✅ {len(ids)} task(s) on {date_str} set to {STATUS_CHOICES[status_key]}.",
        [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main")]],
    )


# ---- Delete task flow (multi-select) ---------------------------------------

async def delete_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Daily Tasks", callback_data="delete:src:tasks")],
        [InlineKeyboardButton("📚 Master List", callback_data="delete:src:master_list")],
        [InlineKeyboardButton("⏳ Waiting List", callback_data="delete:src:waiting_list")],
        [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
    ]
    await _send_or_edit(update, "🗑️ *Delete Task(s)*\nWhere from?", keyboard)


async def delete_src_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, table: str):
    if table == "tasks":
        keyboard = [
            [InlineKeyboardButton("Today", callback_data="delete:day:today")],
            [InlineKeyboardButton("Yesterday", callback_data="delete:day:yesterday")],
            [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
        ]
        await _send_or_edit(update, "Which day?", keyboard)
        return

    tasks = get_master_list() if table == "master_list" else get_waiting_list()
    if not tasks:
        await _send_or_edit(
            update, f"No tasks in the {TABLE_LABELS[table]}.", [[InlineKeyboardButton("⬅️ Back", callback_data="manage")]]
        )
        return

    context.user_data["delete_table"] = table
    context.user_data["delete_date"] = None
    context.user_data["awaiting"] = "delete_select_ids"
    await _send_or_edit(
        update, f"{TABLE_LABELS[table]}:\n\n{_selection_prompt(tasks, with_status=False)}"
    )


async def delete_day_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    day = _today() if choice == "today" else _today() - datetime.timedelta(days=1)
    date_str = day.isoformat()
    tasks = get_tasks_by_date(date_str)
    if not tasks:
        await _send_or_edit(
            update, "No tasks for that day.", [[InlineKeyboardButton("⬅️ Back", callback_data="manage")]]
        )
        return

    context.user_data["delete_table"] = "tasks"
    context.user_data["delete_date"] = date_str
    context.user_data["awaiting"] = "delete_select_ids"
    await _send_or_edit(update, f"Tasks for {date_str}:\n\n{_selection_prompt(tasks)}")


async def delete_ids_received(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    table = context.user_data.get("delete_table")
    date_str = context.user_data.get("delete_date")

    if table == "tasks":
        tasks = get_tasks_by_date(date_str)
    elif table == "master_list":
        tasks = get_master_list()
    else:
        tasks = get_waiting_list()

    valid_ids = [t[0] for t in tasks]
    selected = _parse_selection(text, valid_ids)
    if not selected:
        await update.message.reply_text(
            "❌ No valid IDs found in that input. Try again (e.g. `1,3` or `*`)."
        )
        return

    context.user_data["delete_ids"] = selected
    context.user_data["awaiting"] = None
    keyboard = [
        [
            InlineKeyboardButton("✅ Yes, delete", callback_data="delete:confirm"),
            InlineKeyboardButton("❌ Cancel", callback_data="manage"),
        ]
    ]
    await update.message.reply_text(
        f"Delete {len(selected)} task(s) from {TABLE_LABELS[table]}? This can't be undone.",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def delete_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    table = context.user_data.get("delete_table")
    date_str = context.user_data.get("delete_date")
    ids = context.user_data.get("delete_ids", [])

    for task_id in ids:
        if table == "tasks":
            delete_daily_task(task_id, date_str)
        else:
            delete_task(task_id, table=table)

    await _send_or_edit(
        update, f"✅ {len(ids)} task(s) deleted.", [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main")]]
    )


# ---- Copy task flow (multi-select, any list -> a daily date, source untouched) --

async def copy_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    keyboard = [
        [InlineKeyboardButton("📅 Daily Tasks", callback_data="copy:src:tasks")],
        [InlineKeyboardButton("📚 Master List", callback_data="copy:src:master_list")],
        [InlineKeyboardButton("⏳ Waiting List", callback_data="copy:src:waiting_list")],
        [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
    ]
    await _send_or_edit(update, "📋 *Copy Task(s)*\nCopy from where?", keyboard)


async def copy_src_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, table: str):
    context.user_data["copy_source_table"] = table

    if table == "tasks":
        keyboard = [
            [InlineKeyboardButton("Today", callback_data="copy:day:today")],
            [InlineKeyboardButton("Yesterday", callback_data="copy:day:yesterday")],
            [InlineKeyboardButton("⬅️ Back", callback_data="manage")],
        ]
        await _send_or_edit(update, "Copy from which day?", keyboard)
        return

    tasks = get_master_list() if table == "master_list" else get_waiting_list()
    if not tasks:
        await _send_or_edit(
            update, f"No tasks in the {TABLE_LABELS[table]}.", [[InlineKeyboardButton("⬅️ Back", callback_data="manage")]]
        )
        return

    context.user_data["copy_source_date"] = None
    context.user_data["awaiting"] = "copy_select_ids"
    await _send_or_edit(
        update, f"{TABLE_LABELS[table]}:\n\n{_selection_prompt(tasks, with_status=False)}"
    )


async def copy_day_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    day = _today() if choice == "today" else _today() - datetime.timedelta(days=1)
    date_str = day.isoformat()
    tasks = get_tasks_by_date(date_str)
    if not tasks:
        await _send_or_edit(
            update, "No tasks for that day.", [[InlineKeyboardButton("⬅️ Back", callback_data="manage")]]
        )
        return

    context.user_data["copy_source_table"] = "tasks"
    context.user_data["copy_source_date"] = date_str
    context.user_data["awaiting"] = "copy_select_ids"
    await _send_or_edit(update, f"Tasks for {date_str}:\n\n{_selection_prompt(tasks)}")


async def copy_ids_received(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    table = context.user_data.get("copy_source_table")
    date_str = context.user_data.get("copy_source_date")

    if table == "tasks":
        tasks = get_tasks_by_date(date_str)
    elif table == "master_list":
        tasks = get_master_list()
    else:
        tasks = get_waiting_list()

    valid_ids = [t[0] for t in tasks]
    selected_ids = _parse_selection(text, valid_ids)
    if not selected_ids:
        await update.message.reply_text(
            "❌ No valid IDs found in that input. Try again (e.g. `1,3` or `*`)."
        )
        return

    # Store (name, category) pairs — we don't need the source id/status once copied.
    selected_pairs = [(t[1], t[2]) for t in tasks if t[0] in selected_ids]
    context.user_data["copy_tasks"] = selected_pairs
    context.user_data["awaiting"] = None

    keyboard = [
        [InlineKeyboardButton("Today", callback_data="copy:date:today")],
        [InlineKeyboardButton("Tomorrow", callback_data="copy:date:tomorrow")],
        [InlineKeyboardButton("✏️ Custom date", callback_data="copy:date:custom")],
    ]
    await update.message.reply_text(
        f"Copying {len(selected_pairs)} task(s). Copy them to which date?",
        reply_markup=InlineKeyboardMarkup(keyboard),
    )


async def copy_date_chosen(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    if choice == "custom":
        context.user_data["awaiting"] = "copy_custom_date"
        await _send_or_edit(update, "Send the destination date as `YYYY-MM-DD`.")
        return

    day = _today() if choice == "today" else _today() + datetime.timedelta(days=1)
    await _finish_copy(update, context, day.isoformat())


async def copy_custom_date_received(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str):
    try:
        datetime.datetime.strptime(text, "%Y-%m-%d")
    except ValueError:
        await update.message.reply_text("❌ Invalid date format. Use YYYY-MM-DD and try again.")
        return
    context.user_data["awaiting"] = None
    await _finish_copy(update, context, text)


async def _finish_copy(update: Update, context: ContextTypes.DEFAULT_TYPE, date_str: str):
    pairs = context.user_data.get("copy_tasks", [])
    for name, category in pairs:
        add_task(name, category, date_str, list_type="daily")
    await _send_or_edit(
        update,
        f"✅ {len(pairs)} task(s) copied to {date_str}.",
        [[InlineKeyboardButton("⬅️ Main Menu", callback_data="main")]],
    )


# --------------------------------------------------------------------------
# Reports menu
# --------------------------------------------------------------------------

async def show_reports_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("📆 Daily", callback_data="reports:daily")],
        [InlineKeyboardButton("🗓️ Weekly (current week)", callback_data="reports:weekly")],
        [InlineKeyboardButton("📅 Monthly (current month)", callback_data="reports:monthly")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main")],
    ]
    await _send_or_edit(update, "📊 *Reports*", keyboard)


async def _send_report(update: Update, title: str, tasks):
    if not tasks:
        await _send_or_edit(
            update, f"{title}\nNo tasks found.", [[InlineKeyboardButton("⬅️ Back", callback_data="reports")]]
        )
        return
    metrics = calculate_efficiency(tasks)
    text = (
        f"{title}\n\n"
        f"Total: {metrics['total_tasks']}  |  Completed: {metrics['completed_tasks']}  |  "
        f"Failed: {metrics['failed_tasks']}  |  Moved/Cancelled: {metrics['moved_or_cancelled']}\n"
        f"Efficiency: {metrics['efficiency']:.1f}%\n\n"
        + _fmt_task_rows(tasks)
    )
    await _send_or_edit(update, text, [[InlineKeyboardButton("⬅️ Back", callback_data="reports")]])


async def reports_daily(update: Update, context: ContextTypes.DEFAULT_TYPE):
    date_str = _today().isoformat()
    tasks = get_tasks_by_date(date_str)
    await _send_report(update, f"📆 Daily Report ({date_str})", tasks)


async def reports_weekly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = _today()
    start = today - datetime.timedelta(days=today.weekday())
    end = start + datetime.timedelta(days=6)
    tasks = get_tasks_by_range(start.isoformat(), end.isoformat())
    await _send_report(update, f"🗓️ Weekly Report ({start} to {end})", tasks)


async def reports_monthly(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = _today()
    start = today.replace(day=1)
    end = (start + datetime.timedelta(days=31)).replace(day=1) - datetime.timedelta(days=1)
    tasks = get_tasks_by_range(start.isoformat(), end.isoformat())
    await _send_report(update, f"📅 Monthly Report ({start} to {end})", tasks)


# --------------------------------------------------------------------------
# Watch Lists menu
# --------------------------------------------------------------------------

async def show_watch_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    keyboard = [
        [InlineKeyboardButton("Today", callback_data="watch:day:today")],
        [InlineKeyboardButton("Tomorrow", callback_data="watch:day:tomorrow")],
        [InlineKeyboardButton("Yesterday", callback_data="watch:day:yesterday")],
        [InlineKeyboardButton("📚 Master List", callback_data="watch:master")],
        [InlineKeyboardButton("⏳ Waiting List", callback_data="watch:waiting")],
        [InlineKeyboardButton("⬅️ Back", callback_data="main")],
    ]
    await _send_or_edit(update, "👁️ *Watch Lists*", keyboard)


async def watch_day(update: Update, context: ContextTypes.DEFAULT_TYPE, choice: str):
    offset = {"today": 0, "tomorrow": 1, "yesterday": -1}[choice]
    date_str = (_today() + datetime.timedelta(days=offset)).isoformat()
    tasks = get_tasks_by_date(date_str)
    await _send_or_edit(
        update,
        f"Tasks for {date_str}:\n\n{_fmt_task_rows(tasks)}",
        [[InlineKeyboardButton("⬅️ Back", callback_data="watch")]],
    )


async def watch_master(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_master_list()
    await _send_or_edit(
        update,
        f"📚 Master List:\n\n{_fmt_task_rows(tasks, with_status=False)}",
        [[InlineKeyboardButton("⬅️ Back", callback_data="watch")]],
    )


async def watch_waiting(update: Update, context: ContextTypes.DEFAULT_TYPE):
    tasks = get_waiting_list()
    await _send_or_edit(
        update,
        f"⏳ Waiting List:\n\n{_fmt_task_rows(tasks, with_status=False)}",
        [[InlineKeyboardButton("⬅️ Back", callback_data="watch")]],
    )


# --------------------------------------------------------------------------
# Central dispatchers
# --------------------------------------------------------------------------

async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _authorized(update):
        return
    query = update.callback_query
    await query.answer()
    data = query.data
    parts = data.split(":")
    head = parts[0]

    if data == "main":
        await show_main_menu(update, context)
    elif data == "manage":
        await show_manage_menu(update, context)
    elif data == "reports":
        await show_reports_menu(update, context)
    elif data == "watch":
        await show_watch_menu(update, context)

    elif data == "add:start":
        await add_start(update, context)
    elif head == "add" and parts[1] == "list":
        await add_list_chosen(update, context, parts[2])
    elif head == "add" and parts[1] == "cat":
        await add_category_chosen(update, context, parts[2])
    elif head == "add" and parts[1] == "date":
        await add_date_chosen(update, context, parts[2])

    elif data == "update:start":
        await update_start(update, context)
    elif head == "update" and parts[1] == "day":
        await update_day_chosen(update, context, parts[2])
    elif head == "update" and parts[1] == "status":
        await update_status_chosen(update, context, parts[2])

    elif data == "delete:start":
        await delete_start(update, context)
    elif head == "delete" and parts[1] == "src":
        await delete_src_chosen(update, context, parts[2])
    elif head == "delete" and parts[1] == "day":
        await delete_day_chosen(update, context, parts[2])
    elif data == "delete:confirm":
        await delete_confirm(update, context)

    elif data == "copy:start":
        await copy_start(update, context)
    elif head == "copy" and parts[1] == "src":
        await copy_src_chosen(update, context, parts[2])
    elif head == "copy" and parts[1] == "day":
        await copy_day_chosen(update, context, parts[2])
    elif head == "copy" and parts[1] == "date":
        await copy_date_chosen(update, context, parts[2])

    elif data == "reports:daily":
        await reports_daily(update, context)
    elif data == "reports:weekly":
        await reports_weekly(update, context)
    elif data == "reports:monthly":
        await reports_monthly(update, context)

    elif head == "watch" and parts[1] == "day":
        await watch_day(update, context, parts[2])
    elif data == "watch:master":
        await watch_master(update, context)
    elif data == "watch:waiting":
        await watch_waiting(update, context)


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await _authorized(update):
        return
    awaiting = context.user_data.get("awaiting")
    text = update.message.text.strip()

    if awaiting == "add_task_name":
        await add_task_name_received(update, context, text)
    elif awaiting == "add_custom_date":
        await add_custom_date_received(update, context, text)
    elif awaiting == "update_select_ids":
        await update_ids_received(update, context, text)
    elif awaiting == "delete_select_ids":
        await delete_ids_received(update, context, text)
    elif awaiting == "copy_select_ids":
        await copy_ids_received(update, context, text)
    elif awaiting == "copy_custom_date":
        await copy_custom_date_received(update, context, text)
    else:
        await update.message.reply_text(
            "I wasn't expecting a message right now — use /start to open the menu."
        )


async def on_error(update, context):
    logger.error("Unhandled exception while processing update: %s", update, exc_info=context.error)


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------

def main():
    if not BOT_TOKEN:
        raise SystemExit("TELEGRAM_BOT_TOKEN environment variable is not set.")
    if AUTHORIZED_CHAT_ID is None:
        raise SystemExit("TELEGRAM_CHAT_ID environment variable is not set.")

    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("restart", cmd_restart))
    app.add_handler(CallbackQueryHandler(on_callback))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(on_error)

    logger.info("Navigoals bot starting (polling mode)...")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()