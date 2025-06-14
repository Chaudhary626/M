from db import get_db, _db_lock
from datetime import datetime, timedelta

def get_next_video_for_user(user_id):
    """Find a video the user has not yet viewed and is not their own, ensuring fair rotation."""
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        # Get all active videos not owned by the user
        c.execute("""
            SELECT v.id FROM videos v
            WHERE v.active=1 AND v.user_id != ? AND v.id NOT IN (
                SELECT video_id FROM tasks WHERE assigned_to = ?
            )
        """, (user_id, user_id))
        videos = [row["id"] for row in c.fetchall()]
        if not videos:
            conn.close()
            return None

        # For fairness: get view counts for these videos
        candidate_views = []
        for vid in videos:
            c.execute("SELECT COUNT(*) as cnt FROM tasks WHERE video_id=? AND proof_uploaded_at IS NOT NULL", (vid,))
            candidate_views.append((vid, c.fetchone()["cnt"]))
        # Pick the one with lowest views
        candidate_views.sort(key=lambda x: x[1])
        selected_video_id = candidate_views[0][0]
        conn.close()
        return selected_video_id

def assign_task(video_id, user_id):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            INSERT INTO tasks (video_id, assigned_to, assigned_at)
            VALUES (?, ?, ?)
        """, (video_id, user_id, datetime.utcnow().isoformat()))
        conn.commit()
        c.execute("SELECT last_insert_rowid() as tid")
        task_id = c.fetchone()["tid"]
        conn.close()
        return task_id

def get_task_for_review(uploader_id):
    """Get the next submitted proof for this uploader to review."""
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            SELECT t.*, v.title FROM tasks t
            JOIN videos v ON t.video_id = v.id
            WHERE v.user_id=? AND t.proof_uploaded_at IS NOT NULL AND t.verified=0 AND t.expired=0
            ORDER BY t.proof_uploaded_at ASC
            LIMIT 1
        """, (uploader_id,))
        row = c.fetchone()
        conn.close()
        return row

def mark_task_verified(task_id, result, reviewer_id, reviewer_msg=None):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("""
            UPDATE tasks 
            SET verified=1, verification_result=?, verification_at=?, reviewer_id=?, reviewer_msg=?
            WHERE id=?
        """, (result, datetime.utcnow().isoformat(), reviewer_id, reviewer_msg, task_id))
        conn.commit()
        conn.close()

def increment_strike(tg_id):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        c.execute("SELECT strikes FROM users WHERE tg_id=?", (tg_id,))
        user = c.fetchone()
        if user is None: return
        new_strikes = user["strikes"] + 1
        c.execute("UPDATE users SET strikes=? WHERE tg_id=?", (new_strikes, tg_id))
        conn.commit()
        conn.close()
        return new_strikes

def reset_task_after_rejection(task_id):
    with _db_lock:
        conn = get_db()
        c = conn.cursor()
        # Set task as expired so it won't be counted anymore
        c.execute("UPDATE tasks SET expired=1 WHERE id=?", (task_id,))
        conn.commit()
        conn.close()