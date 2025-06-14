import os

ADMIN_IDS = [123456789]  # Replace with your Telegram user IDs

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_token():
    return os.environ.get('BOT_TOKEN', 'PASTE_YOUR_TOKEN_HERE')

def time_now():
    from datetime import datetime
    return datetime.utcnow().isoformat()