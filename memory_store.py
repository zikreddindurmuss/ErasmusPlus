"""
Kalıcı Konuşma Hafızası (SQLite)
================================
ai_engine.py'nin RAM'de tuttuğu `user_sessions` sözlüğünü dosya-tabanlı
kalıcı hafızayla değiştirir. Harici servis yok; tek bir SQLite dosyası.

Davranış, eski RAM mantığıyla birebir aynı:
  - user_id bazlı sohbet geçmişi tutulur
  - her kullanıcı için son 3 soru-cevap (6 mesaj) saklanır (Sliding Window)

Bağlantılar kısa ömürlüdür (her işlemde aç-kapat). Bot asyncio ile tek
thread üzerinde sıralı çalıştığından bu güvenlidir ve kilit sorunları olmaz.
"""

import sqlite3
from contextlib import closing
from datetime import datetime

DB_PATH = "chat_memory.db"

# Kullanıcı başına saklanacak maksimum mesaj sayısı (3 soru-cevap = 6 mesaj)
MAX_MESSAGES = 6


def _connect() -> sqlite3.Connection:
    return sqlite3.connect(DB_PATH)


def init_db() -> None:
    """messages tablosunu (yoksa) oluştur. Modül yüklenirken çağrılır."""
    # Not: `closing(...)` bağlantıyı garanti kapatır (sqlite3'ün `with conn:`
    # bloğu yalnızca transaction'ı yönetir, bağlantıyı KAPATMAZ).
    with closing(_connect()) as conn, conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                role    TEXT    NOT NULL,
                content TEXT    NOT NULL,
                ts      TEXT    NOT NULL
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user ON messages (user_id, id)"
        )


def get_history(user_id: int, limit: int = MAX_MESSAGES) -> list[dict]:
    """
    Kullanıcının son `limit` mesajını KRONOLOJİK sırayla döndür.
    Format: [{"role": ..., "content": ...}, ...] — LLM messages listesine hazır.
    """
    with closing(_connect()) as conn:
        rows = conn.execute(
            """
            SELECT role, content FROM messages
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()

    # En yeniden en eskiye çektik → kronolojik sıraya çevir
    return [{"role": role, "content": content} for role, content in reversed(rows)]


def add_turn(user_id: int, user_msg: str, assistant_msg: str) -> None:
    """
    Bir soru-cevap çiftini hafızaya ekle ve pencereyi (son MAX_MESSAGES mesaj)
    koru. Eski RAM mantığındaki `.append(...) + [-6:]` adımının karşılığı.
    """
    now = datetime.now().isoformat()
    with closing(_connect()) as conn, conn:
        conn.executemany(
            "INSERT INTO messages (user_id, role, content, ts) VALUES (?, ?, ?, ?)",
            [
                (user_id, "user", user_msg, now),
                (user_id, "assistant", assistant_msg, now),
            ],
        )
        # Sliding window: bu kullanıcının en yeni MAX_MESSAGES satırı dışını sil
        conn.execute(
            """
            DELETE FROM messages
            WHERE user_id = ?
              AND id NOT IN (
                  SELECT id FROM messages
                  WHERE user_id = ?
                  ORDER BY id DESC
                  LIMIT ?
              )
            """,
            (user_id, user_id, MAX_MESSAGES),
        )
