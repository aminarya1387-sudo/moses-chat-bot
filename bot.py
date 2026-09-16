import os
import re
import asyncio
from typing import Optional
from dotenv import load_dotenv
from telegram import Update, constants, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)

from memory_ultimate import MemoryManagerUltimate as MemoryManager
from system_prompt import get_system_prompt
from image_generator import ImageGenerator
from web_search import WebSearch
from news_manager import NewsManager
from keep_alive import keep_alive
import gemini_client

# بارگذاری متغیرهای محیطی
load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.5-flash-lite")

# ====== اطلاعات ربات از .env با مقادیر پیش‌فرض ======
BOT_NAME = os.getenv("BOT_NAME", "Moses")
BOT_CREATOR = os.getenv("BOT_CREATOR", "Amin")
BOT_DESCRIPTION = os.getenv("BOT_DESCRIPTION", "just a chatbot")
BOT_VERSION = os.getenv("BOT_VERSION", "1.2.0")

SYSTEM_PROMPT = get_system_prompt(BOT_NAME, BOT_CREATOR, BOT_DESCRIPTION, BOT_VERSION)

# مقداردهی سرویس‌ها
memory_manager = MemoryManager(GEMINI_API_KEY, GEMINI_MODEL)
image_generator = ImageGenerator()
web_search = WebSearch(GEMINI_API_KEY, GEMINI_MODEL)
news_manager = NewsManager(GEMINI_API_KEY, GEMINI_MODEL)


# ====== تبدیل اعداد فارسی به انگلیسی ======
def normalize_digits(text: str) -> str:
    fa_digits = "۰۱۲۳۴۵۶۷۸۹"
    en_digits = "0123456789"
    table = str.maketrans(dict(zip(fa_digits, en_digits)))
    return text.translate(table)


# ====== ارسال و ویرایش ایمن پیام‌ها در تلگرام (جلوگیری از خطای محدودیت کاراکتر) ======
async def safe_reply(update: Update, text: str, reply_markup=None):
    """ارسال پیام با تقسیم خودکار متن‌های طولانی به بسته‌های زیر ۴۰۰۰ کاراکتر"""
    if not text:
        return
    chunk_size = 4000
    if len(text) <= chunk_size:
        if update.message:
            await update.message.reply_text(text, reply_markup=reply_markup)
        elif update.effective_chat:
            await update.get_bot().send_message(chat_id=update.effective_chat.id, text=text, reply_markup=reply_markup)
        return

    for i in range(0, len(text), chunk_size):
        chunk = text[i:i + chunk_size]
        is_last = (i + chunk_size >= len(text))
        markup = reply_markup if is_last else None
        if update.message:
            await update.message.reply_text(chunk, reply_markup=markup)
        elif update.effective_chat:
            await update.get_bot().send_message(chat_id=update.effective_chat.id, text=chunk, reply_markup=markup)


async def safe_edit_or_send(msg, update: Update, text: str, reply_markup=None):
    """ویرایش پیام اولیه یا ارسال پیام جدید در صورت طولانی بودن بدون کرش کردن ربات"""
    if not text:
        text = "⚠️ پاسخی دریافت نشد."

    if len(text) <= 4000:
        try:
            await msg.edit_text(text, reply_markup=reply_markup)
            return
        except Exception:
            pass

    try:
        await msg.delete()
    except Exception:
        pass
    await safe_reply(update, text, reply_markup=reply_markup)


# ====== نمایش فهرست اخبار با دکمه‌های شیشه‌ای تعاملی ======
async def send_news_list(update: Update, user_id: str):
    """واکشی تیترهای داغ از واشنگتن پست و ایران اینترنشنال و ارسال با شماره/کد"""
    wait_msg = await update.message.reply_text("🌐 در حال واکشی سرخط اخبار از واشنگتن پست، ایران اینترنشنال و منابع بین‌المللی...")
    articles = await news_manager.fetch_latest_news_list(user_id)

    if not articles:
        await wait_msg.edit_text("❌ متأسفانه در حال حاضر امکان اتصال به خبرگزاری‌ها فراهم نشد. لطفاً چند لحظه دیگر امتحان کنید.")
        return

    text = "📰 **آخرین سرخط اخبار معتبر جهان و ایران (واشنگتن پست، ایران اینترنشنال و بین‌الملل):**\n\n"
    buttons = []
    current_row = []

    for a in articles:
        text += f"**[{a.id}]** 🏛 *{a.source}*\n"
        text += f"🔹 **{a.title_fa}**\n\n"

        current_row.append(InlineKeyboardButton(f"📰 خبر {a.id}", callback_data=f"read_news_{a.id}"))
        if len(current_row) == 3:
            buttons.append(current_row)
            current_row = []

    if current_row:
        buttons.append(current_row)

    text += "👇 **برای مطالعه گزارش کامل، مشروح و ترجمه دقیق هر خبر:**\n"
    text += "کافیست **شماره خبر** (مثلاً `1` یا `4`) را ارسال کنید یا روی دکمه‌های زیر کلیک نمایید."

    keyboard = InlineKeyboardMarkup(buttons)
    await safe_edit_or_send(wait_msg, update, text, reply_markup=keyboard)


# ====== نمایش گزارش کامل و تفصیلی خبر انتخاب‌شده ======
async def show_full_news(update: Update, user_id: str, news_id: int):
    """تولید و نمایش ترجمه کامل، مشروح و جامع یک خبر با Gemini 3.5 Flash Lite"""
    chat_id = update.effective_chat.id
    bot = update.get_bot()

    status_msg = await bot.send_message(
        chat_id=chat_id,
        text=f"⏳ **در حال دریافت متن اصلی و آماده‌سازی گزارش کامل خبر [{news_id}] با جزئیات کامل و ترجمه فارسی...**"
    )

    report = await news_manager.get_full_news_report(user_id, news_id)

    if not report:
        await status_msg.edit_text("❌ کد خبر یافت نشد یا منقضی شده است. لطفاً ابتدا دستور /news را ارسال نمایید.")
        return

    await safe_edit_or_send(status_msg, update, report)


# ====== هندلر دکمه‌های شیشه‌ای تلگرام ======
async def handle_news_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مدیریت کلیک روی دکمه‌های شیشه‌ای اخبار"""
    query = update.callback_query
    await query.answer()

    if query.data.startswith("read_news_"):
        try:
            news_id = int(query.data.split("_")[-1])
            user_id = str(query.from_user.id)
            await show_full_news(update, user_id, news_id)
        except Exception as e:
            print(f"⚠️ Callback error: {e}")


# ====== تشخیص هوشمند درخواست تولید تصویر ======
IMAGE_PATTERNS = [
    r'^(بکش|نقاشی کن|طراحی کن|عکس بساز|تصویر بساز)\s+(.+)',
    r'(.+)\s+(رو برام بکش|رو نقاشی کن|رو طراحی کن|رو بساز)$',
    r'^(draw|paint|sketch|illustrate|generate image of|create image of|make image of)\s+(.+)',
    r'^(یک|یه)\s+(عکس|تصویر|نقاشی)\s+از\s+(.+)',
]


def detect_image_intent(text: str) -> Optional[str]:
    """تشخیص قصد تولید تصویر بدون اشتباه روی کلماتی مثل 'عکس‌العمل'"""
    text_clean = text.strip()
    for pattern in IMAGE_PATTERNS:
        match = re.search(pattern, text_clean, re.IGNORECASE)
        if match:
            groups = match.groups()
            prompt = groups[-1].strip()
            return prompt if prompt else text_clean

    direct_keywords = ["draw me", "generate image", "عکس بکش", "تصویر بساز", "نقاشی کن"]
    for kw in direct_keywords:
        if kw in text_clean.lower():
            p = re.sub(kw, "", text_clean, flags=re.IGNORECASE).strip()
            return p if p else "a beautiful scenic view"

    return None


# ====== تشخیص هوشمند درخواست اخبار و سرچ وب ======
CASUAL_PHRASES = {
    "سلام چه خبر", "چه خبر", "چخبر", "چه خبر؟", "چطوری چه خبر",
    "چه خبرها", "what's up", "whats up", "سلام چطوری", "چطوری", "خوبی"
}


def is_news_list_intent(text: str) -> bool:
    """بررسی اینکه آیا کاربر فهرست اخبار روز، واشنگتن پست یا ایران اینترنشنال را می‌خواهد"""
    text_clean = text.strip()
    text_lower = text_clean.lower()
    if text_lower in CASUAL_PHRASES:
        return False

    news_triggers = [
        "اخبار", "خبرهای روز", "اخبار روز", "اخبار دنیا", "اخبار جهان",
        "واشنگتن پست", "ایران اینترنشنال", "آخرین اخبار", "اخبار امروز",
        "تیتر اخبار", "خبر تازه", "خبر فوری", "اخبار جدید"
    ]
    for trigger in news_triggers:
        if trigger in text_clean:
            return True
    return False


def detect_web_search_intent(text: str) -> Optional[str]:
    """تشخیص استعلامات قیمت یا جستجوهای عمومی وب"""
    text_clean = text.strip()

    finance_weather_triggers = [
        "قیمت دلار", "قیمت طلا", "قیمت سکه", "قیمت بیت کوین", "قیمت ارز",
        "قیمت خودرو", "وضعیت هوا", "آب و هوای", "پیش بینی هوا"
    ]
    for trigger in finance_weather_triggers:
        if trigger in text_clean:
            return text_clean

    search_cmd_match = re.search(
        r'^(سرچ کن|جستجو کن|در گوگل بگرد|در اینترنت بگرد|پیدا کن|search for|google)\s+(.+)',
        text_clean,
        re.IGNORECASE
    )
    if search_cmd_match:
        return search_cmd_match.group(2).strip()

    search_suffix_match = re.search(
        r'(.+)\s+(رو سرچ کن|رو جستجو کن|رو در اینترنت پیدا کن|رو برام پیدا کن)$',
        text_clean,
        re.IGNORECASE
    )
    if search_suffix_match:
        return search_suffix_match.group(1).strip()

    return None


# ====== دستورات اصلی ربات ======
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پیام شروع و معرفی قابلیت‌ها"""
    user_id = str(update.message.chat_id)
    summary = await memory_manager.get_memory_summary(user_id)

    welcome_text = (
        f"🤖 **{BOT_NAME}** (نسخه {BOT_VERSION})\n"
        f"👨‍💻 توسعه داده شده توسط: {BOT_CREATOR}\n"
        f"⚡ مجهز به مدل فوق‌سریع **{GEMINI_MODEL}**\n\n"
        f"{summary}\n\n"
        "💡 **قابلیت‌های ویژه و جدید:**\n"
        "• 📰 **سیستم اخبار حرفه‌ای و دو مرحله‌ای:** دستور `/news` را بزنید تا اخبار **واشنگتن پست** و **ایران اینترنشنال** را با کد دریافت کنید و با ارسال شماره هر خبر، گزارش کامل و مشروح آن را بخوانید!\n"
        "• 🧠 **حافظه هوشمند:** یادآوری خودکار اطلاعات شما در گفتگوها\n"
        "• 🎨 **تولید تصویر:** مثلاً بنویسید: `نقاشی کن یک فضانورد در مریخ`\n"
        "• 🌐 **جستجوی وب:** دستور `/web <عبارت>`\n\n"
        "📌 **فرمان‌های سریع:**\n"
        "/news - دریافت سرخط اخبار با امکان درخواست گزارش کامل هر خبر\n"
        "/web <عبارت> - جستجوی زنده در اینترنت\n"
        "/info - مشاهده اطلاعات ثبت‌شده از شما\n"
        "/search <عبارت> - جستجو در حافظه مکالمات\n"
        "/about - مشخصات فنی ربات\n"
        "/reset - ریست تاریخچه مکالمات اخیر\n"
        "/forgetme - حذف کامل و قطعی داده‌های شما از سیستم"
    )
    await safe_reply(update, welcome_text)


async def about(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """مشخصات فنی و وضعیت سیستم"""
    about_text = (
        f"🤖 **درباره {BOT_NAME}**\n\n"
        f"📌 **نام:** {BOT_NAME}\n"
        f"👨‍💻 **سازنده:** {BOT_CREATOR}\n"
        f"🔢 **نسخه:** {BOT_VERSION}\n"
        f"⚡ **موتور هوش مصنوعی:** {GEMINI_MODEL} (Ultra-Fast Async)\n"
        f"📰 **پوشش اخبار اختصاصی:** واشنگتن پست، ایران اینترنشنال و بی‌بی‌سی با کدگذاری و گزارش کامل\n"
        f"🌐 **موتور وب:** DuckDuckGo + خلاصه هوشمند\n"
        f"🧠 **سیستم حافظه:** SQLite غیرمسدودکننده (aiosqlite) + حافظه برداری (ChromaDB)\n"
        f"🎨 **موتور تصویرساز:** Pollinations.ai (با Seed تصادفی پویا)\n\n"
        f"🚀 معماری ۱۰۰٪ ناهمگام (Non-blocking Async) برای نهایت سرعت و پایداری."
    )
    await safe_reply(update, about_text)


async def news_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور دریافت سرخط اخبار روز با کد اختصاصی"""
    user_id = str(update.message.chat_id)
    await send_news_list(update, user_id)


async def web_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """دستور مستقیم جستجو در وب"""
    parts = update.message.text.split(maxsplit=1)
    if len(parts) < 2:
        await safe_reply(update, "❌ لطفاً عبارت مورد نظر برای جستجو را بنویسید. مثال:\n`/web نرخ لحظه‌ای طلا`")
        return

    query = parts[1].strip()
    wait_msg = await update.message.reply_text(f"🌐 در حال جستجوی زنده در وب برای: «{query}»...")
    result = await web_search.search_and_summarize(query)
    await safe_edit_or_send(wait_msg, update, result)


async def show_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """نمایش وضعیت و فکت‌های ذخیره‌شده از کاربر"""
    user_id = str(update.message.chat_id)
    summary = await memory_manager.get_memory_summary(user_id)
    await safe_reply(update, summary)


async def search_memory_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """جستجوی دقیق و معنایی در اطلاعات و تاریخچه کاربر"""
    user_id = str(update.message.chat_id)
    parts = update.message.text.split(maxsplit=1)

    if len(parts) < 2:
        await safe_reply(update, "❌ لطفاً عبارت مورد نظر را بنویسید. مثال: `/search پایتون`")
        return

    query = parts[1].strip()
    results = await memory_manager.search(user_id, query)

    facts = results.get("facts", [])
    semantics = results.get("semantic", [])

    if not facts and not semantics:
        await safe_reply(update, f"🔍 نتیجه‌ای برای '{query}' در حافظه یافت نشد.")
        return

    res_text = f"🔍 **نتایج جستجو برای '{query}':**\n\n"
    if facts:
        res_text += "🧠 **فکت‌های ثبت‌شده:**\n"
        for item in facts[:8]:
            res_text += f"• {item.key}: {item.value} [{item.category}]\n"
        res_text += "\n"

    if semantics:
        res_text += "📚 **مکالمات مشابه قبلی:**\n"
        for s in semantics[:3]:
            res_text += f"• {s[:150]}...\n"

    await safe_reply(update, res_text)


async def forget_me(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """حذف واقعی تمام سوابق، پیام‌ها و فکت‌های کاربر از دیتابیس و ChromaDB"""
    user_id = str(update.message.chat_id)
    await memory_manager.delete_user_data(user_id)
    await safe_reply(update, "🗑️ **تمامی داده‌ها، حافظه و پیام‌های شما به طور کامل و قطعی از سیستم حذف شدند.**")


async def reset(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پاکسازی تاریخچه چت جاری بدون حذف فکت‌های هویتی"""
    user_id = str(update.message.chat_id)
    await memory_manager.clear_conversation_history(user_id)
    await safe_reply(update, "🧹 **تاریخچه مکالمات اخیر ریست شد!** (فکت‌های هویتی شما همچنان محفوظ هستند)")


# ====== تابع اصلی پردازش پیام ======
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """پردازش پیام‌های ورودی، بررسی کدهای خبر و چت سریع با هوش مصنوعی"""
    if not update.message or not update.message.text:
        return

    user_id = str(update.message.chat_id)
    user_message = update.message.text.strip()
    normalized_text = normalize_digits(user_message)

    # ۱. بررسی اینکه آیا کاربر کد یک خبر را فرستاده است (مثلاً 1 یا خبر 2 یا /read 3)
    code_match = re.search(r'^(?:خبر\s*|شماره\s*|/read\s*)?(\d{1,2})$', normalized_text)
    if code_match:
        news_id = int(code_match.group(1))
        cached_articles = news_manager.user_news_cache.get(user_id, [])
        if any(a.id == news_id for a in cached_articles):
            await show_full_news(update, user_id, news_id)
            return

    # ارسال اکشن Typing در تلگرام برای بازخورد سریع
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)

    # ذخیره پیام کاربر در دیتابیس
    await memory_manager.save_conversation(user_id, "user", user_message)

    # ۲. بررسی درخواست دریافت فهرست اخبار روز (واشنگتن پست و ایران اینترنشنال)
    if is_news_list_intent(user_message):
        await send_news_list(update, user_id)
        return

    # ۳. بررسی درخواست جستجوی وب عمومی یا استعلام قیمت
    search_query = detect_web_search_intent(user_message)
    if search_query:
        wait_msg = await update.message.reply_text(f"🌐 در حال جستجوی زنده در اینترنت برای: «{search_query}»...")
        search_result = await web_search.search_and_summarize(search_query)
        await safe_edit_or_send(wait_msg, update, search_result)
        await memory_manager.save_conversation(user_id, "assistant", search_result[:500])
        return

    # ۴. بررسی درخواست تولید تصویر
    image_prompt = detect_image_intent(user_message)
    if image_prompt:
        wait_msg = await update.message.reply_text(f"🎨 در حال تولید تصویر: «{image_prompt}»...")
        image_bytes = await image_generator.generate_image(image_prompt)

        if image_bytes:
            try:
                await wait_msg.delete()
            except Exception:
                pass
            await update.message.reply_photo(
                photo=image_bytes,
                caption=f"🖼️ تصویر تولید شده برای:\n{image_prompt}"
            )
            await memory_manager.save_conversation(user_id, "assistant", f"[Image generated: {image_prompt}]")
        else:
            await wait_msg.edit_text("❌ متأسفانه در ساخت تصویر خطایی رخ داد. لطفاً مجدداً امتحان کنید.")
        return

    # ۵. استخراج فکت در پس‌زمینه (Background Task) بدون ایجاد تاخیر برای کاربر
    asyncio.create_task(memory_manager.analyze_and_save(user_id, user_message))

    # ۶. واکشی همزمان کانتکست و تاریخچه اخیر چت
    memory_context_task = memory_manager.get_context(user_id, user_message)
    history_task = memory_manager.get_conversation_history(user_id, limit=12)

    memory_context, conversation_history = await asyncio.gather(memory_context_task, history_task)

    history_text = ""
    for msg in conversation_history:
        history_text += f"{msg['role']}: {msg['message']}\n"

    status_msg = await update.message.reply_text("🤔 ...")

    full_prompt = f"""{SYSTEM_PROMPT}

{memory_context}

Conversation history:
{history_text}
user: {user_message}
assistant:"""

    try:
        reply = await gemini_client.async_generate_text(
            full_prompt,
            api_key=GEMINI_API_KEY,
            model=GEMINI_MODEL,
            temperature=0.7,
            max_output_tokens=1024,
            timeout=25.0,
        )
    except Exception as e:
        reply = f"❌ متأسفانه در پردازش پاسخ خطایی رخ داد: {e}"

    # ۷. ذخیره پاسخ دستیار
    await memory_manager.save_conversation(user_id, "assistant", reply)

    # ۸. ارسال یا ویرایش ایمن پاسخ
    await safe_edit_or_send(status_msg, update, reply)


def main():
    if not TELEGRAM_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN is not set in .env! Please configure it.")
        return

    print(f"🚀 Starting {BOT_NAME} v{BOT_VERSION}...")
    print(f"🧠 Model: {GEMINI_MODEL}")
    print(f"👨‍💻 Creator: {BOT_CREATOR}")
    print(f"📰 News Engine: Washington Post & Iran International (Interactive Code & Full Report)")
    print(f"⚡ Concurrency Engine: 100% Async / Non-blocking")
    keep_alive()

    app = Application.builder().token(TELEGRAM_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("about", about))
    app.add_handler(CommandHandler("news", news_command))
    app.add_handler(CommandHandler("web", web_command))
    app.add_handler(CommandHandler("info", show_info))
    app.add_handler(CommandHandler("search", search_memory_command))
    app.add_handler(CommandHandler("forgetme", forget_me))
    app.add_handler(CommandHandler("reset", reset))

    # هندلر کلیک روی دکمه‌های شیشه‌ای اخبار
    app.add_handler(CallbackQueryHandler(handle_news_callback))

    # هندلر پیام‌های متنی
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print(f"✅ {BOT_NAME} is live and polling updates!")
    app.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()