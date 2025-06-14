import os

ADMIN_IDS = [5718213826]  # Replace with your Telegram user IDs

def is_admin(user_id):
    return user_id in ADMIN_IDS

def get_token():
    return os.environ.get('BOT_TOKEN', '6547874705:AAFEcs-AG3pRlU5tqrj-pZunp_TyXB7oHFA')

def time_now():
    from datetime import datetime
    return datetime.utcnow().isoformat()
