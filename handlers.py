from aiogram import Router, types, F
from aiogram.fsm.context import FSMContext
from fsm import UploadVideoFSM, SubmitProofFSM, RemoveVideoFSM
from db import get_db, _db_lock, add_log
from tasks import (
    get_next_video_for_user, assign_task, get_task_for_review,
    mark_task_verified, increment_strike, reset_task_after_rejection,
)
from utils import is_admin, time_now
from aiogram.types import (
    ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton,
    InputMediaPhoto
)

router = Router()

def main_menu():
    kb = ReplyKeyboardMarkup(resize_keyboard=True)
    kb.add(KeyboardButton('/upload'), KeyboardButton('/gettask'))
    kb.add(KeyboardButton('/submitproof'), KeyboardButton('/remove'))
    kb.add(KeyboardButton('/status'), KeyboardButton('/strikes'))
    kb.add(KeyboardButton('/pause'), KeyboardButton('/resume'))
    kb.add(KeyboardButton('/rules'), KeyboardButton('/menu'))
    return kb

def yes_no_kb(action):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Yes", callback_data=f"{action}_yes"),
         InlineKeyboardButton(text="❌ No", callback_data=f"{action}_no")]
    ])

def proof_review_kb(task_id):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ I completed as expected", callback_data=f"verify_{task_id}_ok")],
        [InlineKeyboardButton(text="❌ I skipped something", callback_data=f"verify_{task_id}_fail")]
    ])

@router.message(F.text == "/start")
async def start_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        if not c.fetchone():
            c.execute("INSERT INTO users (tg_id, username, last_active) VALUES (?, ?, ?)",
                (message.from_user.id, message.from_user.username, time_now()))
            conn.commit()
    await message.answer(
        "👋 Welcome! Use the menu below to get started.",
        reply_markup=main_menu())
    await message.answer(
        "Rules:\n"
        "1. Upload up to 5 videos with /upload\n"
        "2. Complete tasks to view & interact with others' videos\n"
        "3. You must screen record each task and submit proof\n"
        "4. If you skip or delay, you get strikes (4 = temp ban)\n"
        "5. Pause with /pause, resume with /resume\n"
        "6. Remove videos with /remove\n"
    )

@router.message(F.text == "/rules")
@router.message(F.text == "/help")
async def rules_cmd(message: types.Message):
    await message.answer(
        "Rules:\n"
        "1. Upload up to 5 videos with /upload\n"
        "2. Complete tasks to view & interact with others' videos\n"
        "3. You must screen record each task and submit proof\n"
        "4. If you skip or delay, you get strikes (4 = temp ban)\n"
        "5. Pause with /pause, resume with /resume\n"
        "6. Remove videos with /remove\n"
    )

@router.message(F.text == "/menu")
async def menu_cmd(message: types.Message):
    await message.answer("Use the buttons below:", reply_markup=main_menu())

# FSM: /upload
@router.message(F.text == "/upload")
async def upload_cmd(message: types.Message, state: FSMContext):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        uid = c.fetchone()
        if not uid:
            await message.answer("Please /start first.")
            return
        uid = uid["id"]
        c.execute("SELECT COUNT(*) as cnt FROM videos WHERE user_id=? AND active=1", (uid,))
        if c.fetchone()["cnt"] >= 5:
            await message.answer("You already have 5 active videos. Remove one with /remove before uploading a new one.")
            return
    await state.set_state(UploadVideoFSM.waiting_for_title)
    await message.answer("Send me your video *title* (max 100 chars):", parse_mode="Markdown")

@router.message(UploadVideoFSM.waiting_for_title)
async def upload_title(message: types.Message, state: FSMContext):
    title = message.text.strip()
    if len(title) > 100:
        await message.answer("Title too long. Please send a title under 100 characters.")
        return
    await state.update_data(title=title)
    await state.set_state(UploadVideoFSM.waiting_for_thumbnail)
    await message.answer("Now send the *thumbnail* as a photo (mandatory):", parse_mode="Markdown")

@router.message(UploadVideoFSM.waiting_for_thumbnail)
async def upload_thumbnail(message: types.Message, state: FSMContext):
    if not message.photo:
        await message.answer("Please send a photo as thumbnail.")
        return
    thumbnail_file_id = message.photo[-1].file_id
    await state.update_data(thumbnail_file_id=thumbnail_file_id)
    await state.set_state(UploadVideoFSM.waiting_for_duration)
    await message.answer("Send video duration in seconds (max 300):")

@router.message(UploadVideoFSM.waiting_for_duration)
async def upload_duration(message: types.Message, state: FSMContext):
    try:
        dur = int(message.text.strip())
    except Exception:
        await message.answer("Please send number of seconds (max 300).")
        return
    if not (0 < dur <= 300):
        await message.answer("Duration must be between 1 and 300 seconds.")
        return
    await state.update_data(duration=dur)
    await state.set_state(UploadVideoFSM.waiting_for_link)
    await message.answer("Paste your YouTube video link (optional, or say skip):")

@router.message(UploadVideoFSM.waiting_for_link)
async def upload_link(message: types.Message, state: FSMContext):
    yt_link = message.text.strip() if "skip" not in message.text.lower() else ""
    data = await state.get_data()
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        uid = c.fetchone()["id"]
        c.execute("""
            INSERT INTO videos (user_id, title, thumbnail_file_id, duration, yt_link, uploaded_at, active)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (uid, data["title"], data["thumbnail_file_id"], data["duration"], yt_link, time_now()))
        conn.commit()
    await message.answer("✅ Video uploaded! Use /gettask to start viewing others.", reply_markup=main_menu())
    await state.clear()

# /remove video
@router.message(F.text == "/remove")
async def remove_cmd(message: types.Message, state: FSMContext):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        uid = c.fetchone()
        if not uid:
            await message.answer("Please /start first.")
            return
        uid = uid["id"]
        c.execute("SELECT * FROM videos WHERE user_id=? AND active=1", (uid,))
        vids = c.fetchall()
        if not vids:
            await message.answer("You have no active videos.")
            return
        reply = "Select a video to remove:\n"
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=v["title"], callback_data=f"removev_{v['id']}")] for v in vids
        ])
        await message.answer(reply, reply_markup=kb)

@router.callback_query(F.data.startswith("removev_"))
async def remove_video_cb(call: types.CallbackQuery):
    vid = int(call.data.split("_")[1])
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE videos SET active=0 WHERE id=?", (vid,))
        conn.commit()
    await call.answer("Removed!")
    await call.message.edit_text("Video removed.", reply_markup=main_menu())

# /pause and /resume
@router.message(F.text == "/pause")
async def pause_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        uid = c.fetchone()
        if not uid:
            await message.answer("Please /start first.")
            return
        uid = uid["id"]
        # Check if any video is being reviewed
        c.execute("""
            SELECT t.id FROM tasks t 
            JOIN videos v ON t.video_id = v.id 
            WHERE v.user_id=? AND t.verified=0 AND t.expired=0 AND t.proof_uploaded_at IS NOT NULL
        """, (uid,))
        if c.fetchone():
            await message.answer("Can't pause while someone is viewing your video.")
            return
        c.execute("UPDATE users SET paused=1 WHERE id=?", (uid,))
        conn.commit()
    await message.answer("You are paused. Use /resume to return.")

@router.message(F.text == "/resume")
async def resume_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE users SET paused=0 WHERE tg_id=?", (message.from_user.id,))
        conn.commit()
    await message.answer("Participation resumed.", reply_markup=main_menu())

# /gettask
@router.message(F.text == "/gettask")
async def gettask_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id, paused, strikes, banned_until FROM users WHERE tg_id=?", (message.from_user.id,))
        u = c.fetchone()
        if not u:
            await message.answer("Please /start first.")
            return
        if u["paused"]:
            await message.answer("You are paused. Use /resume to get tasks.")
            return
        if u["strikes"] >= 4:
            await message.answer("You are banned due to strikes.")
            return
        # Check if any pending review tasks for this user
        task = get_task_for_review(u["id"])
        if task:
            # Notify user to review proof first
            await message.answer("You have a proof to review! Please verify the task before getting a new one.")
            return

        # Assign a new task
        vid = get_next_video_for_user(u["id"])
        if not vid:
            await message.answer("No videos available at the moment. Please try later.")
            return
        t_id = assign_task(vid, u["id"])
        # Get video details
        c.execute("SELECT * FROM videos WHERE id=?", (vid,))
        v = c.fetchone()
        kb = yes_no_kb(f"accepttask_{t_id}")
        await message.answer_photo(
            v["thumbnail_file_id"], 
            caption=f"Task:\nTitle: {v['title']}\nDuration: {v['duration']}s\n"
                    f"{'Link: '+v['yt_link'] if v['yt_link'] else ''}\n\n"
                    "1. Search the video on YouTube.\n"
                    "2. Play at least 2 min.\n"
                    "3. Like, Comment, Subscribe as instructed.\n"
                    "4. Screen record the process.\n"
                    "Ready? Press Yes to start, No to skip.",
            reply_markup=kb
        )

@router.callback_query(F.data.startswith("accepttask_"))
async def accepttask_cb(call: types.CallbackQuery):
    t_id = int(call.data.split("_")[1].replace("yes","").replace("no",""))
    if call.data.endswith("no"):
        await call.answer("Task skipped.")
        with _db_lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("UPDATE tasks SET expired=1 WHERE id=?", (t_id,))
            conn.commit()
        await call.message.edit_text("Task skipped. Use /gettask to get a new task.", reply_markup=main_menu())
        return
    # Accepted
    await call.answer("Task accepted. Complete and use /submitproof to upload your screen record.")
    await call.message.edit_text("Task accepted. Complete the video view and use /submitproof.", reply_markup=main_menu())

# /submitproof
@router.message(F.text == "/submitproof")
async def submitproof_cmd(message: types.Message, state: FSMContext):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT t.id, v.title FROM tasks t JOIN videos v ON t.video_id = v.id WHERE t.assigned_to=? AND t.proof_uploaded_at IS NULL AND t.expired=0 AND t.verified=0", (message.from_user.id,))
        t = c.fetchone()
        if not t:
            await message.answer("No pending task found. Use /gettask to receive one.")
            return
        await state.set_state(SubmitProofFSM.waiting_for_proof)
        await state.update_data(task_id=t["id"])
        await message.answer(f"Upload screen-record video as a file (not as video), as proof for: {t['title']}")

@router.message(SubmitProofFSM.waiting_for_proof)
async def submitproof_file(message: types.Message, state: FSMContext):
    if not message.document:
        await message.answer("Please upload a screen-recording as a file.")
        return
    file_id = message.document.file_id
    data = await state.get_data()
    task_id = data["task_id"]
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("UPDATE tasks SET proof_file_id=?, proof_uploaded_at=? WHERE id=?",
                  (file_id, time_now(), task_id))
        conn.commit()
    # Notify uploader
    c.execute("SELECT v.user_id FROM tasks t JOIN videos v ON t.video_id=v.id WHERE t.id=?", (task_id,))
    uploader_id = c.fetchone()["user_id"]
    # Store for review
    await message.answer("Proof submitted! The uploader will verify within 20 minutes.", reply_markup=main_menu())
    await state.clear()
    # Notify uploader
    await message.bot.send_message(uploader_id, f"You have a proof to review for your video. Use /review to verify.")

# /review: For uploader to verify proof
@router.message(F.text == "/review")
async def review_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT id FROM users WHERE tg_id=?", (message.from_user.id,))
        u = c.fetchone()
        if not u:
            await message.answer("Please /start first.")
            return
        u = u["id"]
        task = get_task_for_review(u)
        if not task:
            await message.answer("No pending proofs to review.")
            return
        # Send proof for review
        kb = proof_review_kb(task["id"])
        await message.answer_document(task["proof_file_id"], caption=f"Proof for: {task['title']}", reply_markup=kb)

@router.callback_query(F.data.startswith("verify_"))
async def verify_cb(call: types.CallbackQuery):
    parts = call.data.split("_")
    task_id = int(parts[1])
    if parts[2] == "ok":
        mark_task_verified(task_id, "accepted", call.from_user.id)
        # Notify viewer: next task unlocked
        with _db_lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT assigned_to FROM tasks WHERE id=?", (task_id,))
            viewer = c.fetchone()["assigned_to"]
        await call.bot.send_message(viewer, "Your proof was accepted! You can now get the next task using /gettask.")
        await call.answer("Proof accepted.")
        await call.message.edit_text("Proof accepted.", reply_markup=main_menu())
    else:
        mark_task_verified(task_id, "rejected", call.from_user.id, reviewer_msg="Skipped something")
        with _db_lock:
            conn = get_db()
            c = conn.cursor()
            c.execute("SELECT assigned_to FROM tasks WHERE id=?", (task_id,))
            viewer = c.fetchone()["assigned_to"]
        increment_strike(viewer)
        await call.bot.send_message(viewer, "Your proof was rejected. You received a strike. Please check requirements.")
        await call.answer("Proof rejected and strike added.")
        await call.message.edit_text("Proof rejected.", reply_markup=main_menu())
        reset_task_after_rejection(task_id)

# /strikes
@router.message(F.text == "/strikes")
async def strikes_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT strikes FROM users WHERE tg_id=?", (message.from_user.id,))
        s = c.fetchone()
        strikes = s["strikes"] if s else 0
    await message.answer(f"Your strikes: {strikes} (4 = ban).")

# /status
@router.message(F.text == "/status")
async def status_cmd(message: types.Message):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT paused, strikes FROM users WHERE tg_id=?", (message.from_user.id,))
        u = c.fetchone()
        if not u:
            await message.answer("Please /start first.")
            return
        c.execute("SELECT COUNT(*) as cnt FROM videos WHERE user_id=? AND active=1", (message.from_user.id,))
        v = c.fetchone()
    await message.answer(f"Paused: {'Yes' if u['paused'] else 'No'}\nStrikes: {u['strikes']}\nActive videos: {v['cnt']}")