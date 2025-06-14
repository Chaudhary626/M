from aiogram import Router, types, F
from utils import is_admin
from db import get_db, _db_lock

router = Router()

@router.message(F.text.startswith("/adminpanel"))
async def admin_panel(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Not authorized.")
        return

    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT * FROM users WHERE strikes >= 2")
        users = c.fetchall()
        reply = "👮‍♀️ Admin Panel:\n\nUsers with 2+ strikes:\n"
        for u in users:
            reply += f"- @{u['username']} (TG: {u['tg_id']}) — Strikes: {u['strikes']}\n"
        await message.answer(reply)

@router.message(F.text.startswith("/strike"))
async def admin_strike(message: types.Message):
    if not is_admin(message.from_user.id):
        await message.answer("Not authorized.")
        return
    parts = message.text.split()
    if len(parts) < 3:
        await message.answer("Usage: /strike <add|remove> <tg_id>")
        return
    action, tg_id = parts[1], int(parts[2])
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        if action == "add":
            c.execute("UPDATE users SET strikes = strikes + 1 WHERE tg_id=?", (tg_id,))
        elif action == "remove":
            c.execute("UPDATE users SET strikes = MAX(strikes-1, 0) WHERE tg_id=?", (tg_id,))
        else:
            await message.answer("Action must be add or remove.")
            return
        conn.commit()
    await message.answer(f"Strike {action}ed for user {tg_id}.")