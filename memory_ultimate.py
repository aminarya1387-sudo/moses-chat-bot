# memory_ultimate.py
"""
سیستم حافظه پیشرفته و چندلایه (Ultimate Memory Engine)
طراحی شده به صورت کاملاً غیرمسدودکننده (Async) با پشتیبانی از aiosqlite، ChromaDB و Gemini API
"""

import os
import json
import sqlite3
import hashlib
import asyncio
from datetime import datetime
from typing import Dict, List, Any, Optional
import re
from dataclasses import dataclass
import aiosqlite
import gemini_client

# ====== کتابخانه‌های برداری (Semantic Memory) ======
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    HAS_VECTOR_DB = True
except ImportError:
    HAS_VECTOR_DB = False
    print("⚠️ ChromaDB or Sentence-Transformers not installed. Vector memory disabled.")


@dataclass
class MemoryItem:
    """ساختار داده برای هر فکت یا آیتم ذخیره شده در حافظه"""
    key: str
    value: Any
    category: str
    importance: int  # 1 تا 10
    timestamp: str
    context: str = ""
    confidence: float = 0.0
    last_accessed: str = ""


class MemoryStorageUltimate:
    """لایه ذخیره‌سازی داده‌ها در SQLite به صورت کاملاً آسنکرون (Non-blocking)"""

    def __init__(self, db_path: str = "memory_ultimate.db"):
        self.db_path = db_path
        self._init_sync_db()

    def _init_sync_db(self):
        """ایجاد جداول و ایندکس‌های پرسرعت در زمان استارت‌آپ"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        # جدول حافظه اصلی (فکت‌ها و اطلاعات کاربر)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                key TEXT NOT NULL,
                value TEXT,
                category TEXT,
                importance INTEGER DEFAULT 5,
                timestamp TEXT,
                context TEXT,
                confidence REAL DEFAULT 0.0,
                last_accessed TEXT,
                UNIQUE(user_id, key)
            )
        ''')

        # جدول رویدادها
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                title TEXT NOT NULL,
                description TEXT,
                date TEXT,
                importance INTEGER DEFAULT 5,
                reminder INTEGER DEFAULT 0,
                created_at TEXT
            )
        ''')

        # جدول پیام‌ها و تاریخچه مکالمات
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS conversations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                message TEXT,
                role TEXT,
                timestamp TEXT,
                embedding BLOB,
                summary TEXT
            )
        ''')

        # ایندکس‌های پرسرعت برای تسریع کوئری‌های واکشی
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_conversations_user_timestamp 
            ON conversations(user_id, timestamp DESC)
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_memory_user_key 
            ON memory(user_id, key)
        ''')

        conn.commit()
        conn.close()

    async def save_memory_item(self, user_id: str, item: MemoryItem):
        """ذخیره یا به‌روزرسانی فکت در دیتابیس به صورت غیرمسدودکننده"""
        val_str = json.dumps(item.value, ensure_ascii=False) if isinstance(item.value, (dict, list)) else str(item.value)
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT OR REPLACE INTO memory 
                (user_id, key, value, category, importance, timestamp, context, confidence, last_accessed)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                user_id,
                item.key,
                val_str,
                item.category,
                item.importance,
                item.timestamp,
                item.context,
                item.confidence,
                datetime.now().isoformat()
            ))
            await db.commit()

    async def get_memory_items(self, user_id: str, limit: int = 100) -> List[MemoryItem]:
        """واکشی اقلام حافظه کاربر بر اساس درجه اهمیت"""
        items = []
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT key, value, category, importance, timestamp, context, confidence
                FROM memory
                WHERE user_id = ?
                ORDER BY importance DESC, timestamp DESC
                LIMIT ?
            ''', (user_id, limit)) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        value = json.loads(row[1])
                    except Exception:
                        value = row[1]

                    items.append(MemoryItem(
                        key=row[0],
                        value=value,
                        category=row[2],
                        importance=row[3],
                        timestamp=row[4],
                        context=row[5] or "",
                        confidence=row[6] or 0.0
                    ))
        return items

    async def search_memory(self, user_id: str, query: str) -> List[MemoryItem]:
        """جستجوی متنی در کلیدها و مقادیر ذخیره شده"""
        items = []
        async with aiosqlite.connect(self.db_path) as db:
            pattern = f"%{query}%"
            async with db.execute('''
                SELECT key, value, category, importance, timestamp, context, confidence
                FROM memory
                WHERE user_id = ? 
                AND (key LIKE ? OR value LIKE ?)
                ORDER BY importance DESC
            ''', (user_id, pattern, pattern)) as cursor:
                rows = await cursor.fetchall()
                for row in rows:
                    try:
                        value = json.loads(row[1])
                    except Exception:
                        value = row[1]

                    items.append(MemoryItem(
                        key=row[0],
                        value=value,
                        category=row[2],
                        importance=row[3],
                        timestamp=row[4],
                        context=row[5] or "",
                        confidence=row[6] or 0.0
                    ))
        return items

    async def save_conversation(self, user_id: str, role: str, message: str):
        """ذخیره هر پیام در جدول مکالمات"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute('''
                INSERT INTO conversations (user_id, message, role, timestamp)
                VALUES (?, ?, ?, ?)
            ''', (user_id, message, role, datetime.now().isoformat()))
            await db.commit()

    async def get_conversation_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """دریافت تاریخچه پیام‌های اخیر کاربر به ترتیب زمانی"""
        async with aiosqlite.connect(self.db_path) as db:
            async with db.execute('''
                SELECT role, message, timestamp
                FROM conversations
                WHERE user_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (user_id, limit)) as cursor:
                rows = await cursor.fetchall()

        history = []
        for row in rows:
            history.append({
                "role": row[0],
                "message": row[1],
                "timestamp": row[2]
            })
        return history[::-1]

    async def delete_all_user_data(self, user_id: str) -> bool:
        """پاکسازی کامل تمام اطلاعات، پیام‌ها و فکت‌های کاربر از دیتابیس"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM memory WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            await db.execute("DELETE FROM events WHERE user_id = ?", (user_id,))
            await db.commit()
        return True

    async def clear_conversation_history(self, user_id: str) -> bool:
        """پاکسازی تاریخچه چت کاربر بدون دستکاری فکت‌های هویتی"""
        async with aiosqlite.connect(self.db_path) as db:
            await db.execute("DELETE FROM conversations WHERE user_id = ?", (user_id,))
            await db.commit()
        return True


class VectorMemory:
    """حافظه برداری و معنایی (Semantic Vector Memory) مبتنی بر ChromaDB"""

    def __init__(self):
        if not HAS_VECTOR_DB:
            return

        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        self.chroma_client = chromadb.PersistentClient(
            path="chroma_memory",
            settings=Settings(anonymized_telemetry=False)
        )
        self._init_collections()

    def _init_collections(self):
        try:
            self.collection = self.chroma_client.get_collection("conversations")
        except Exception:
            self.collection = self.chroma_client.create_collection("conversations")

    async def add_conversation(self, user_id: str, message: str, role: str, timestamp: str):
        """افزودن پیام به حافظه برداری با اجرای امبدینگ در ترد مجزا"""
        if not HAS_VECTOR_DB:
            return

        def _encode_and_add():
            embedding = self.model.encode([message])[0].tolist()
            doc_id = f"{user_id}_{hashlib.md5(f'{message}{timestamp}'.encode()).hexdigest()}"
            self.collection.add(
                embeddings=[embedding],
                documents=[message],
                metadatas=[{
                    "user_id": user_id,
                    "role": role,
                    "timestamp": timestamp
                }],
                ids=[doc_id]
            )

        await asyncio.to_thread(_encode_and_add)

    async def semantic_search(self, user_id: str, query: str, n_results: int = 3) -> List[str]:
        """جستجوی معنایی بدون متوقف کردن ترد اصلی"""
        if not HAS_VECTOR_DB:
            return []

        def _query():
            try:
                query_embedding = self.model.encode([query])[0].tolist()
                results = self.collection.query(
                    query_embeddings=[query_embedding],
                    n_results=n_results,
                    where={"user_id": user_id}
                )
                return results['documents'][0] if results.get('documents') else []
            except Exception as e:
                print(f"⚠️ Vector search error: {e}")
                return []

        return await asyncio.to_thread(_query)

    async def delete_user_vectors(self, user_id: str):
        """حذف تمامی وکتورهای کاربر از ChromaDB"""
        if not HAS_VECTOR_DB:
            return

        def _delete():
            try:
                self.collection.delete(where={"user_id": user_id})
            except Exception as e:
                print(f"⚠️ Vector delete error: {e}")

        await asyncio.to_thread(_delete)


class MemoryManagerUltimate:
    """مدیر ارشد حافظه ربات Moses با سرعت و دقت بهینه"""

    def __init__(self, gemini_api_key: str = "", model: str = "gemini-3.5-flash-lite"):
        self.storage = MemoryStorageUltimate()
        self.vector_memory = VectorMemory() if HAS_VECTOR_DB else None
        self.gemini_api_key = gemini_api_key
        self.model = model

    async def analyze_and_save(self, user_id: str, message: str, role: str = "user") -> List[MemoryItem]:
        """
        تحلیل پیام و استخراج هوشمند فکت‌های کاربر در پس‌زمینه.
        این متد بدون متوقف کردن جریان اصلی چت اجرا می‌شود.
        """
        new_items = []
        try:
            current_items = await self.storage.get_memory_items(user_id)
            current_info = {item.key: item.value for item in current_items}

            prompt = f"""You are an advanced memory fact extraction system. Analyze this user message and decide what important facts about the user should be remembered.

Current user memory: {json.dumps(current_info, ensure_ascii=False)[:800]}

User message: "{message}"

Return a JSON array of NEW or UPDATED facts about the user.
Format:
[
  {{"key": "user_name", "value": "Ali", "category": "personal", "importance": 10}},
  {{"key": "programming_language", "value": "Python", "category": "work", "importance": 8}}
]

RULES:
1. ONLY return facts that are explicitly mentioned or clearly stated by the user.
2. Greetings, casual chat, questions, insults, or bot commands must return [].
3. If no new information: return []
4. Return ONLY valid JSON array with NO markdown formatting or commentary.
"""

            analysis = await gemini_client.async_generate_text(
                prompt,
                api_key=self.gemini_api_key,
                model=self.model,
                temperature=0.1,
                max_output_tokens=512,
                timeout=15.0,
            )

            json_match = re.search(r'\[.*\]', analysis, re.DOTALL)
            if json_match:
                items_data = json.loads(json_match.group())
                for item_data in items_data:
                    if isinstance(item_data, dict):
                        key = str(item_data.get("key", "")).lower().strip()
                        value = str(item_data.get("value", "")).strip()
                        category = str(item_data.get("category", "fact")).strip()
                        importance = int(item_data.get("importance", 5))

                        if key and value:
                            if key not in current_info or current_info[key] != value:
                                memory_item = MemoryItem(
                                    key=key,
                                    value=value,
                                    category=category,
                                    importance=importance,
                                    timestamp=datetime.now().isoformat(),
                                    context=message[:200],
                                    confidence=0.9
                                )
                                await self.storage.save_memory_item(user_id, memory_item)
                                new_items.append(memory_item)
        except Exception as e:
            print(f"⚠️ Memory extraction error: {e}")

        # ذخیره در حافظه برداری
        if self.vector_memory:
            try:
                await self.vector_memory.add_conversation(
                    user_id, message, role, datetime.now().isoformat()
                )
            except Exception as e:
                print(f"⚠️ Vector add error: {e}")

        return new_items

    async def get_context(self, user_id: str, query: str = "") -> str:
        """واکشی سریع فکت‌های کاربر و مکالمات مرتبط برای پرامپت"""
        important_items = await self.storage.get_memory_items(user_id, limit=12)

        context_lines = []
        if important_items:
            context_lines.append("🧠 **User Profile & Known Facts:**")
            for item in sorted(important_items, key=lambda x: x.importance, reverse=True):
                context_lines.append(f"- {item.key}: {item.value}")

        if query and self.vector_memory:
            try:
                semantic_results = await self.vector_memory.semantic_search(user_id, query, n_results=2)
                if semantic_results:
                    context_lines.append("\n📚 **Relevant Past Context:**")
                    for result in semantic_results:
                        context_lines.append(f"- {result[:180]}")
            except Exception:
                pass

        return "\n".join(context_lines)

    async def get_memory_summary(self, user_id: str) -> str:
        """تولید گزارش متنی زیبا از حافظه کاربر برای دستور /info"""
        items = await self.storage.get_memory_items(user_id)
        if not items:
            return "📭 هیچ اطلاعات ذخیره‌شده‌ای از شما در حافظه وجود ندارد."

        categories: Dict[str, List[MemoryItem]] = {}
        for item in items:
            cat = item.category or "سایر"
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(item)

        summary = "📊 **خلاصه اطلاعات ذخیره‌شده از شما در حافظه:**\n\n"
        for category, items_list in categories.items():
            summary += f"📁 **{category.capitalize()}** ({len(items_list)} مورد):\n"
            for item in items_list[:6]:
                summary += f"  • {item.key}: {item.value}\n"
            if len(items_list) > 6:
                summary += f"  ... و {len(items_list)-6} مورد دیگر\n"
            summary += "\n"

        return summary

    async def search(self, user_id: str, query: str) -> Dict[str, Any]:
        """
        جستجوی کامل در حافظه (اصلاح شده: ترکیب جستجوی پایگاه داده و معنایی)
        """
        sql_items = await self.storage.search_memory(user_id, query)
        semantic_texts = []
        if self.vector_memory:
            semantic_texts = await self.vector_memory.semantic_search(user_id, query, n_results=3)

        return {
            "facts": sql_items,
            "semantic": semantic_texts
        }

    async def delete_user_data(self, user_id: str) -> bool:
        """پاکسازی قطعی تمام داده‌های کاربر برای دستور /forgetme"""
        await self.storage.delete_all_user_data(user_id)
        if self.vector_memory:
            await self.vector_memory.delete_user_vectors(user_id)
        return True

    async def clear_conversation_history(self, user_id: str) -> bool:
        """پاکسازی تاریخچه چت برای دستور /reset"""
        return await self.storage.clear_conversation_history(user_id)

    async def save_conversation(self, user_id: str, role: str, message: str):
        """ذخیره ناهمگام پیام"""
        await self.storage.save_conversation(user_id, role, message)

    async def get_conversation_history(self, user_id: str, limit: int = 20) -> List[Dict]:
        """واکشی تاریخچه چت اخیر"""
        return await self.storage.get_conversation_history(user_id, limit=limit)


# حفظ سازگاری
MemoryManager = MemoryManagerUltimate