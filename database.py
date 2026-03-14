import sqlite3
from datetime import datetime


class Database:
    def __init__(self, db_name="bot_database.db"):
        self.db_name = db_name
        self.init_db()

    def get_connection(self):
        """Создаёт и возвращает соединение с БД"""
        conn = sqlite3.connect(self.db_name)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Создаёт таблицы, если их нет"""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Таблица пользователей
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    mode TEXT DEFAULT 'general',
                    username TEXT,
                    first_name TEXT,
                    last_name TEXT,
                    registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # Таблица для истории диалогов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS chat_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    role TEXT,
                    message TEXT,
                    mode TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица для обратной связи
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS feedback (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    message_id INTEGER,
                    rating INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Таблица для системных промптов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS prompts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    mode TEXT UNIQUE NOT NULL,
                    prompt TEXT NOT NULL,
                    description TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            # ===== НОВАЯ ТАБЛИЦА ДЛЯ ЗАМЕТОК =====
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS notes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    note TEXT NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
            ''')

            # Добавляем начальные промпты, если таблица пуста
            cursor.execute("SELECT COUNT(*) as count FROM prompts")
            if cursor.fetchone()['count'] == 0:
                default_prompts = [
                    ('general', 'Ты полезный ассистент. Отвечай кратко, по делу, дружелюбно.', 'Свободное общение'),
                    (
                    'code', 'Ты эксперт по программированию на Python. Помогай писать код, объясняй сложные концепции.',
                    'Помощь с кодом'),
                    ('explain', 'Ты учитель. Объясняй сложные темы простыми словами, приводи примеры из жизни.',
                     'Объяснение тем'),
                    ('ideas', 'Ты креативный помощник. Генерируй идеи для проектов, стартапов, творчества.',
                     'Генерация идей')
                ]
                cursor.executemany('''
                    INSERT INTO prompts (mode, prompt, description) VALUES (?, ?, ?)
                ''', default_prompts)
                conn.commit()

    # ===== МЕТОДЫ ДЛЯ ЗАМЕТОК =====
    def save_note(self, user_id, note_text):
        """Сохраняет заметку пользователя и возвращает её ID"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO notes (user_id, note) VALUES (?, ?)
            ''', (user_id, note_text))
            conn.commit()
            return cursor.lastrowid

    def get_notes(self, user_id):
        """Получает все заметки пользователя"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, note, created_at FROM notes 
                WHERE user_id = ? 
                ORDER BY created_at DESC
            ''', (user_id,))
            return cursor.fetchall()

    def delete_note(self, note_id, user_id):
        """Удаляет заметку (проверяя, что она принадлежит пользователю)"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                DELETE FROM notes WHERE id = ? AND user_id = ?
            ''', (note_id, user_id))
            conn.commit()
            return cursor.rowcount > 0

    # ===== ОСТАЛЬНЫЕ МЕТОДЫ (как были раньше) =====
    def get_user_mode(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mode FROM users WHERE user_id = ?", (user_id,))
            result = cursor.fetchone()
            return result['mode'] if result else 'general'

    def set_user_mode(self, user_id, mode, username=None, first_name=None, last_name=None):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM users WHERE user_id = ?", (user_id,))
            if cursor.fetchone():
                cursor.execute('''
                    UPDATE users SET mode = ?, last_active = CURRENT_TIMESTAMP,
                        username = COALESCE(?, username),
                        first_name = COALESCE(?, first_name),
                        last_name = COALESCE(?, last_name)
                    WHERE user_id = ?
                ''', (mode, username, first_name, last_name, user_id))
            else:
                cursor.execute('''
                    INSERT INTO users (user_id, mode, username, first_name, last_name)
                    VALUES (?, ?, ?, ?, ?)
                ''', (user_id, mode, username, first_name, last_name))
            conn.commit()

    def save_message(self, user_id, role, message, mode):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO chat_history (user_id, role, message, mode)
                VALUES (?, ?, ?, ?)
            ''', (user_id, role, message, mode))
            conn.commit()
            return cursor.lastrowid

    def save_feedback(self, user_id, message_id, rating):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO feedback (user_id, message_id, rating)
                VALUES (?, ?, ?)
            ''', (user_id, message_id, rating))
            conn.commit()

    def get_user_stats(self, user_id):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT COUNT(*) as msg_count FROM chat_history 
                WHERE user_id = ? AND role = 'user'
            ''', (user_id,))
            msg_count = cursor.fetchone()['msg_count']

            cursor.execute('''
                SELECT COUNT(*) as likes FROM feedback f
                JOIN chat_history ch ON f.message_id = ch.id
                WHERE ch.user_id = ? AND f.rating = 1
            ''', (user_id,))
            likes = cursor.fetchone()['likes']

            cursor.execute('''
                SELECT COUNT(*) as dislikes FROM feedback f
                JOIN chat_history ch ON f.message_id = ch.id
                WHERE ch.user_id = ? AND f.rating = -1
            ''', (user_id,))
            dislikes = cursor.fetchone()['dislikes']

            return {
                'messages': msg_count,
                'likes': likes,
                'dislikes': dislikes
            }

    def get_all_users_count(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM users")
            return cursor.fetchone()['count']

    # Методы для промптов
    def get_all_prompts(self):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT mode, prompt FROM prompts")
            return {row['mode']: row['prompt'] for row in cursor.fetchall()}

    def get_prompt(self, mode):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT prompt FROM prompts WHERE mode = ?", (mode,))
            result = cursor.fetchone()
            return result['prompt'] if result else None

    def update_prompt(self, mode, new_prompt):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                UPDATE prompts SET prompt = ? WHERE mode = ?
            ''', (new_prompt, mode))
            conn.commit()
            return cursor.rowcount > 0

    def add_prompt(self, mode, prompt):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            try:
                cursor.execute('''
                    INSERT INTO prompts (mode, prompt) VALUES (?, ?)
                ''', (mode, prompt))
                conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def delete_prompt(self, mode):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM prompts WHERE mode = ?", (mode,))
            conn.commit()
            return cursor.rowcount > 0