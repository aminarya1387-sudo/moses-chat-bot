import os
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from dotenv import load_dotenv
from memory_ultimate import MemoryManagerUltimate as MemoryManager
from system_prompt import get_system_prompt
from image_generator import ImageGenerator
from web_search import WebSearch
import gemini_client

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# ====== اطلاعات ربات ======
BOT_NAME = "Moses"
BOT_CREATOR = "Amin"
BOT_DESCRIPTION = "just a chatbot"
BOT_VERSION = "1.0.0"

SYSTEM_PROMPT = get_system_prompt(BOT_NAME, BOT_CREATOR, BOT_DESCRIPTION, BOT_VERSION)

memory_manager = MemoryManager(GEMINI_API_KEY, GEMINI_MODEL)
image_generator = ImageGenerator()
web_search = WebSearch()

# ====== تشخیص درخواست عکس ======
def is_image_request(text: str) -> bool:
    text_lower = text.lower()
    keywords = [
        "draw", "paint", "sketch", "illustrate", "render",
        "generate image", "create image", "make image",
        "تصویر", "عکس", "بکش", "بساز", "طراحی کن", "نقاشی کن",
        "a picture of", "an image of", "draw me", "make me", "create me"
    ]
    for keyword in keywords:
        if keyword in text_lower:
            return True
    return False

def extract_image_prompt(text: str) -> str:
    remove_words = [
        "draw", "paint", "sketch", "illustrate", "render",
        "generate image", "create image", "make image",
        "تصویر", "عکس", "بکش", "بساز", "طراحی کن", "نقاشی کن",
        "a picture of", "an image of", "draw me", "make me", "create me",
        "please", "لطفا", "برام", "برا", "یک", "یه"
    ]
    prompt = text
    for word in remove_words:
        prompt = prompt.replace(word, "").strip()
    return prompt if prompt else "a beautiful landscape"

# ====== دستورات ربات ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    summary = memory_manager.get_memory_summary(user_id)
    
    await update.message.reply_text(
        f"🤖 **{BOT_NAME}**\n"
        f"📌 Version: {BOT_VERSION}\n"
        f"👨‍💻 Created by: {BOT_CREATOR}\n"
        f"📝 {BOT_DESCRIPTION}\n\n"
        f"{summary}\n\n"
        "💡 **How I work:**\n"
        "• I automatically save important information\n"
        "• I can generate images! Try: 'Draw me a picture of a cat'\n"
        "• I can search the web! Try: 'Search for latest news'\n\n"
        "📌 Commands:\n"
        "/info - Show all saved info\n"
        "/search <query> - Search in memory\n"
        "/about - About this bot\n"
        "/forgetme - Delete all your data\n"
        "/reset - Clear chat history"
    )

async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        f"🤖 **About {BOT_NAME}**\n\n"
        f"📌 **Name:** {BOT_NAME}\n"
        f"👨‍💻 **Creator:** {BOT_CREATOR}\n"
        f"📝 **Description:** {BOT_DESCRIPTION}\n"
        f"🔢 **Version:** {BOT_VERSION}\n"
        f"🧠 **Memory:** Ultimate AI-powered memory with SQLite\n"
        f"🗣️ **Model:** {GEMINI_MODEL}\n"
        f"🎨 **Image Generation:** Pollinations.ai (Free)\n"
        f"🌐 **Web Search:** Google Search (Free)\n\n"
        f"💡 I'm a smart chatbot with permanent memory."
    )

async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    summary = memory_manager.get_memory_summary(user_id)
    await update.message.reply_text(summary)

async def search_memory(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    parts = update.message.text.split(maxsplit=1)
    
    if len(parts) < 2:
        await update.message.reply_text("❌ Provide a query. Example: /search pizza")
        return
    
    results = memory_manager.search(user_id, parts[1])
    
    if not results:
        await update.message.reply_text(f"🔍 No results for '{parts[1]}'")
        return
    
    text = f"🔍 **Results for '{parts[1]}':**\n\n"
    for result in results[:10]:
        text += f"• {result.key}: {result.value} [{result.category}]\n"
    
    await update.message.reply_text(text)

async def forget_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    await update.message.reply_text("🗑️ All your data has been deleted!")

async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    context.user_data.clear()
    await update.message.reply_text("🧹 Chat history cleared!")

# ====== تابع اصلی پردازش پیام ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = str(update.message.chat_id)
    user_message = update.message.text
    
    print(f"📩 User message: {user_message}")
    
    # ====== ذخیره‌سازی پیام کاربر در دیتابیس ======
    memory_manager.save_conversation(user_id, "user", user_message)
    
    # ====== تشخیص جستجوی اینترنت ======
    search_keywords = ["جستجو", "search", "گوگل", "google", "اخبار", "news", 
                       "پیدا کن", "find", "اطلاعات", "info", "چه خبر"]
    
    if any(keyword in user_message.lower() for keyword in search_keywords):
        await update.message.reply_text("🔍 در حال جستجو در اینترنت... لطفاً چند ثانیه صبر کنید.")
        
        query = user_message
        for word in search_keywords:
            query = query.replace(word, "").strip()
        
        if not query:
            await update.message.reply_text("❌ لطفاً عبارت مورد نظر برای جستجو رو وارد کن. مثال: قیمت طلا")
            return
        
        result = web_search.search_and_summarize(query)
        
        if len(result) > 4000:
            for i in range(0, len(result), 4000):
                await update.message.reply_text(result[i:i+4000])
        else:
            await update.message.reply_text(result)
        
        memory_manager.save_conversation(user_id, "assistant", result[:500])
        return
    
    # ====== تشخیص درخواست عکس ======
    if is_image_request(user_message):
        print("🖼️ Image request detected!")
        await update.message.reply_text("🎨 Generating image... Please wait a moment.")
        
        image_prompt = extract_image_prompt(user_message)
        print(f"🎨 Extracted prompt: {image_prompt}")
        
        image_data = image_generator.generate_image(image_prompt)
        
        if image_data:
            await update.message.reply_photo(
                photo=image_data,
                caption=f"🖼️ Image created for: {image_prompt}"
            )
            print("✅ Image sent successfully!")
            memory_manager.save_conversation(user_id, "assistant", f"[Image generated: {image_prompt}]")
        else:
            await update.message.reply_text("❌ Sorry, I couldn't generate the image. Please try again.")
            print("❌ Image generation failed!")
        return
    
    # ====== ذخیره‌سازی اطلاعات شخصی در حافظه ======
    new_items = memory_manager.analyze_and_save(user_id, user_message)
    
    if new_items:
        text = "🧠 **I remembered:**\n"
        for item in new_items:
            text += f"• {item.key}: {item.value} [{item.category}]\n"
        await update.message.reply_text(text)
    
    # ====== دریافت تاریخچه‌ی کامل مکالمه ======
    conversation_history = memory_manager.get_conversation_history(user_id, limit=20)
    
    history_text = ""
    for msg in conversation_history:
        history_text += f"{msg['role']}: {msg['message']}\n"
    
    memory_context = memory_manager.get_context(user_id, user_message)
    
    msg = await update.message.reply_text("🤔 Thinking...")
    
    full_prompt = f"""{SYSTEM_PROMPT}

{memory_context}

Conversation history:
{history_text}

user: {user_message}
assistant:"""
    
    try:
        reply = gemini_client.generate_text(
            full_prompt,
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            temperature=0.7,
            max_output_tokens=1024,
            timeout=30,
        )
    except Exception as e:
        reply = f"❌ Error: {e}"
    
    # ====== ذخیره‌سازی پاسخ ربات در دیتابیس ======
    memory_manager.save_conversation(user_id, "assistant", reply)
    
    await msg.edit_text(reply)

def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("info", show_info))
    app.add_handler(CommandHandler("search", search_memory))
    app.add_handler(CommandHandler("forgetme", forget_me))
    app.add_handler(CommandHandler("reset", reset))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    
    print(f"🚀 {BOT_NAME} Ultimate started!")
    print(f"👨‍💻 Created by: {BOT_CREATOR}")
    print(f"📝 {BOT_DESCRIPTION}")
    print(f"🎨 Image generator: Pollinations.ai (Free)")
    print(f"🌐 Web search: Google Search (Free)")
    print(f"🧠 Memory: SQLite Database")
    
    app.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()