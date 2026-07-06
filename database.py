import sqlite3
import json

DB_NAME = "context.db"

def init_db():
    """Создает таблицы истории, если они еще не существуют."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS history (
                user_id INTEGER PRIMARY KEY,
                messages TEXT
            )
        """)
        conn.commit()

def get_context(user_id: int) -> list:
    """Безопасно извлекает историю переписки конкретного пользователя."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT messages FROM history WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        
        if not row or not row[0]:
            return []
            
        try:
            data = json.loads(row[0])
            # Если данные упакованы в формат [system_prompt, messages_list]
            if isinstance(data, list) and len(data) == 2 and isinstance(data[1], list):
                return data[1]
            if isinstance(data, list):
                return data
            return []
        except Exception:
            return []

def save_context(user_id: int, system_prompt: dict, messages: list):
    """Сохраняет историю диалога, ограничивая ее 10 репликами."""
    truncated_messages = messages[-10:]
    full_data = [system_prompt, truncated_messages]
    json_string = json.dumps(full_data, ensure_ascii=False)
    
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO history (user_id, messages) 
            VALUES (?, ?) 
            ON CONFLICT(user_id) DO UPDATE SET messages = excluded.messages
        """, (user_id, json_string))
        conn.commit()

def clear_context(user_id: int):
    """Полностью очищает кэш общения пользователя."""
    with sqlite3.connect(DB_NAME) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM history WHERE user_id = ?", (user_id,))
        conn.commit()
