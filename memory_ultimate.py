import os
import json
import sqlite3
import hashlib
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
import re
from dataclasses import dataclass, asdict
import threading
import time
import gemini_client

# ====== کتابخونه‌های پیشرفته ======
try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    HAS_VECTOR_DB = True
except ImportError:
    HAS_VECTOR_DB = False
    print("⚠️  ChromaDB or Sentence-Transformers not installed. Vector memory disabled.")
    print("   Install with: pip install chromadb sentence-transformers")

# ====== کلاس‌های داده ======
@dataclass
class MemoryItem:
    """یک آیتم حافظه"""
    key: str
    value: Any
    category: str
    importance: int  # 1-10 (10 = most important)
    timestamp: str
    context: str = ""
    confidence: float = 0.0
    last_accessed: str = ""

@dataclass
class Event:
    """یک رویداد در حافظه"""
    title: str
    description: str
    date: str
    importance: int
    user_id: str
    reminder: bool = False

class MemoryStorageUltimate:
    """لایه ذخیره‌سازی پیشرفته با SQLite"""
    
    def __init__(self, db_path="memory_ultimate.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """ایجاد جداول مورد نیاز"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # جدول حافظه‌ی اصلی
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
        
        # جدول مکالمات (برای Semantic Memory)
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
        
        conn.commit()
        conn.close()
    
    def save_memory_item(self, user_id: str, item: MemoryItem):
        """ذخیره‌سازی یک آیتم حافظه"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO memory 
            (user_id, key, value, category, importance, timestamp, context, confidence, last_accessed)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            user_id,
            item.key,
            json.dumps(item.value) if isinstance(item.value, (dict, list)) else str(item.value),
            item.category,
            item.importance,
            item.timestamp,
            item.context,
            item.confidence,
            datetime.now().isoformat()
        ))
        
        conn.commit()
        conn.close()
    
    def get_memory_items(self, user_id: str, limit: int = 100) -> List[MemoryItem]:
        """دریافت آیتم‌های حافظه"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT key, value, category, importance, timestamp, context, confidence
            FROM memory
            WHERE user_id = ?
            ORDER BY importance DESC, timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        
        items = []
        for row in cursor.fetchall():
            try:
                value = json.loads(row[1])
            except:
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
        
        conn.close()
        return items
    
    def search_memory(self, user_id: str, query: str) -> List[MemoryItem]:
        """جستجوی ساده در حافظه"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT key, value, category, importance, timestamp, context, confidence
            FROM memory
            WHERE user_id = ? 
            AND (key LIKE ? OR value LIKE ?)
            ORDER BY importance DESC
        ''', (user_id, f'%{query}%', f'%{query}%'))
        
        items = []
        for row in cursor.fetchall():
            try:
                value = json.loads(row[1])
            except:
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
        
        conn.close()
        return items

class VectorMemory:
    """حافظه‌ی برداری (Semantic Memory)"""
    
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
        """ایجاد مجموعه‌ها"""
        try:
            self.collection = self.chroma_client.get_collection("conversations")
        except:
            self.collection = self.chroma_client.create_collection("conversations")
    
    def add_conversation(self, user_id: str, message: str, role: str, timestamp: str):
        """افزودن مکالمه به حافظه‌ی برداری"""
        if not HAS_VECTOR_DB:
            return
        
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
    
    def semantic_search(self, user_id: str, query: str, n_results: int = 5) -> List[str]:
        """جستجوی معنایی در مکالمات"""
        if not HAS_VECTOR_DB:
            return []
        
        query_embedding = self.model.encode([query])[0].tolist()
        
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=n_results,
            where={"user_id": user_id}
        )
        
        return results['documents'][0] if results['documents'] else []

class MemoryManagerUltimate:
    """مدیریت‌کننده‌ی نهایی حافظه"""
    
    def __init__(self, gemini_api_key: str = "", model: str = "gemini-3.5-flash-lite"):
        self.storage = MemoryStorageUltimate()
        self.vector_memory = VectorMemory() if HAS_VECTOR_DB else None
        self.gemini_api_key = gemini_api_key
        self.model = model
        
        # قوانین اهمیت
        self.importance_rules = {
            "personal": 10,
            "event": 9,
            "relationship": 8,
            "work": 7,
            "health": 7,
            "preference": 6,
            "interest": 5,
            "fact": 4,
            "casual": 2
        }
    
    def analyze_and_save(self, user_id: str, message: str, role: str = "user") -> List[MemoryItem]:
        """تحلیل پیام و ذخیره‌سازی هوشمند"""
        new_items = []
        
        # ۱. دریافت حافظه‌ی فعلی
        current_items = self.storage.get_memory_items(user_id)
        current_info = {item.key: item.value for item in current_items}
        
        # ۲. تحلیل پیام با LLM
        prompt = f"""You are an advanced memory system. Analyze this user message and decide what to remember.

Current memory: {json.dumps(current_info, ensure_ascii=False)[:1000]}

User message: "{message}"

Return a JSON array of information to remember. For each item, provide:
- key: the name of the information
- value: the actual information
- category: personal, work, health, relationship, event, preference, interest, fact, casual
- importance: 1-10 (10 = most important)

IMPORTANT RULES:
1. Only save NEW information or UPDATED information
2. If the information is already in memory, DON'T save it again
3. Small talk, greetings, questions → DON'T save (importance < 3)
4. Personal information, preferences, events → SAVE (importance > 5)

Example response:
[
  {{"key": "name", "value": "Alex", "category": "personal", "importance": 10}},
  {{"key": "favorite_food", "value": "pizza", "category": "preference", "importance": 6}}
]

If nothing to save: return []

ONLY return the JSON array.
"""
        
        try:
            analysis = gemini_client.generate_text(
                prompt,
                api_key=self.gemini_api_key,
                model=self.model,
                temperature=0.1,
                max_output_tokens=1024,
                timeout=30,
            )

            # استخراج JSON
            json_match = re.search(r'\[.*\]', analysis, re.DOTALL)
            if json_match:
                items_data = json.loads(json_match.group())
                for item_data in items_data:
                    if isinstance(item_data, dict):
                        key = item_data.get("key", "").lower().strip()
                        value = item_data.get("value", "").strip()
                        category = item_data.get("category", "fact")
                        importance = item_data.get("importance", 5)
                        
                        if key and value:
                            if key not in current_info or current_info[key] != value:
                                memory_item = MemoryItem(
                                    key=key,
                                    value=value,
                                    category=category,
                                    importance=importance,
                                    timestamp=datetime.now().isoformat(),
                                    context=message[:200],
                                    confidence=0.8
                                )
                                self.storage.save_memory_item(user_id, memory_item)
                                new_items.append(memory_item)
        except Exception as e:
            print(f"Analysis error: {e}")
        
        # ۳. ذخیره در حافظه‌ی برداری
        if self.vector_memory:
            self.vector_memory.add_conversation(
                user_id, message, role, datetime.now().isoformat()
            )
        
        return new_items
    
    def get_context(self, user_id: str, query: str = "", limit: int = 15) -> str:
        """دریافت متن حافظه برای پرامپت"""
        context = "🧠 **User's Memory:**\n\n"
        
        important_items = self.storage.get_memory_items(user_id, limit=10)
        important_items = sorted(important_items, key=lambda x: x.importance, reverse=True)
        
        for item in important_items:
            context += f"• {item.key}: {item.value} (importance: {item.importance})\n"
        
        if query and self.vector_memory:
            semantic_results = self.vector_memory.semantic_search(user_id, query, n_results=3)
            if semantic_results:
                context += "\n📚 **Related conversations:**\n"
                for result in semantic_results:
                    context += f"• {result[:200]}...\n"
        
        return context
    
    def get_memory_summary(self, user_id: str) -> str:
        """خلاصه‌ی حافظه‌ی کاربر"""
        items = self.storage.get_memory_items(user_id)
        
        if not items:
            return "No information saved yet."
        
        categories = {}
        for item in items:
            if item.category not in categories:
                categories[item.category] = []
            categories[item.category].append(item)
        
        summary = "📊 **Memory Summary**\n\n"
        for category, items_list in categories.items():
            summary += f"**{category.capitalize()}** ({len(items_list)} items):\n"
            for item in items_list[:5]:
                summary += f"  • {item.key}: {item.value}\n"
            if len(items_list) > 5:
                summary += f"  ... and {len(items_list)-5} more\n"
            summary += "\n"
        
        return summary
    
    def search(self, user_id: str, query: str) -> List[MemoryItem]:
        """جستجو در حافظه"""
        items = self.storage.search_memory(user_id, query)
        
        if self.vector_memory and not items:
            semantic_results = self.vector_memory.semantic_search(user_id, query)
        
        return items

    # ============================================
    # ====== توابع جدید برای ذخیره‌سازی مکالمات ======
    # ============================================
    
    def save_conversation(self, user_id: str, role: str, message: str):
        """ذخیره‌سازی هر پیام در دیتابیس"""
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO conversations (user_id, message, role, timestamp)
            VALUES (?, ?, ?, ?)
        ''', (user_id, message, role, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()

    def get_conversation_history(self, user_id: str, limit: int = 50) -> List[Dict]:
        """دریافت تاریخچه‌ی مکالمه"""
        conn = sqlite3.connect(self.storage.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT role, message, timestamp
            FROM conversations
            WHERE user_id = ?
            ORDER BY timestamp DESC
            LIMIT ?
        ''', (user_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        history = []
        for row in rows:
            history.append({
                "role": row[0],
                "message": row[1],
                "timestamp": row[2]
            })
        
        return history[::-1]  # برعکس کردن برای ترتیب درست

class MemoryOptimizer:
    """بهینه‌ساز حافظه - خلاصه‌سازی و پاکسازی خودکار"""
    
    def __init__(self, memory_manager: MemoryManagerUltimate):
        self.memory_manager = memory_manager
        self.gemini_api_key = memory_manager.gemini_api_key
        self.model = memory_manager.model
    
    def compress_old_memory(self, user_id: str):
        """فشرده‌سازی حافظه‌های قدیمی"""
        items = self.memory_manager.storage.get_memory_items(user_id)
        old_items = [i for i in items if i.importance < 4]
        
        if len(old_items) > 10:
            prompt = f"""Summarize this user's information in 5-10 sentences:
{json.dumps([{"key": i.key, "value": i.value} for i in old_items], ensure_ascii=False)}
"""
            try:
                summary = gemini_client.generate_text(
                    prompt,
                    api_key=self.gemini_api_key,
                    model=self.model,
                    max_output_tokens=500,
                    timeout=30,
                )

                memory_item = MemoryItem(
                    key="summary_compressed",
                    value=summary,
                    category="summary",
                    importance=5,
                    timestamp=datetime.now().isoformat(),
                    context="Auto-compressed old memory"
                )
                self.memory_manager.storage.save_memory_item(user_id, memory_item)
                    
            except Exception as e:
                print(f"Compression error: {e}")

# ====== این خط رو اضافه کن تا با نسخه‌های قبلی سازگار باشه ======
MemoryManager = MemoryManagerUltimate