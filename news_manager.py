# news_manager.py
"""
سیستم مدیریت هوشمند و تعاملی اخبار بین‌الملل و ایران
پوشش اختصاصی: واشنگتن پست (Washington Post)، ایران اینترنشنال (Iran International) و بی‌بی‌سی
امکان ارائه فهرست کددار و ارسال گزارش مشروح و کامل با Gemini 3.5 Flash Lite
"""

from typing import Dict, List, Optional
from dataclasses import dataclass
import asyncio
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
import httpx
import gemini_client


@dataclass
class NewsArticle:
    """مدل داده یک مقاله خبری"""
    id: int
    title: str
    title_fa: str
    source: str
    url: str
    snippet: str
    content: str = ""


class NewsManager:
    """مدیریت فرآیند واکشی، کدگذاری و ترجمه مشروح اخبار روز"""

    def __init__(self, gemini_api_key: str, gemini_model: str = "gemini-3.5-flash-lite"):
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        # کش اختصاصی آخرین فهرست اخبار به ازای هر کاربر
        self.user_news_cache: Dict[str, List[NewsArticle]] = {}
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept-Language": "fa,en;q=0.5",
        }

    async def _fetch_iran_intl(self, client: httpx.AsyncClient) -> List[dict]:
        """واکشی جدیدترین اخبار از صفحه اصلی ایران اینترنشنال"""
        articles = []
        try:
            r = await client.get("https://www.iranintl.com/", timeout=9.0)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                seen = set()
                for a in soup.find_all("a", href=True):
                    href = a["href"]
                    title = a.get_text(strip=True)
                    if ("/202" in href or "/news" in href) and len(title) > 25 and href not in seen:
                        seen.add(href)
                        full_url = href if href.startswith("http") else f"https://www.iranintl.com{href}"
                        articles.append({
                            "title": title,
                            "title_fa": title,
                            "source": "ایران اینترنشنال (Iran Intl)",
                            "url": full_url,
                            "snippet": title,
                        })
                        if len(articles) >= 4:
                            break
        except Exception as e:
            print(f"⚠️ Iran Intl fetch error: {e}")
        return articles

    async def _fetch_washington_post(self, client: httpx.AsyncClient) -> List[dict]:
        """واکشی تیترهای داغ بین‌المللی از واشنگتن پست"""
        articles = []
        urls = [
            "https://feeds.washingtonpost.com/rss/world",
            "https://feeds.washingtonpost.com/rss/national"
        ]
        for feed_url in urls:
            try:
                r = await client.get(feed_url, timeout=12.0)
                if r.status_code == 200:
                    root = ET.fromstring(r.content)
                    for item in root.findall(".//item")[:3]:
                        t = item.find("title").text if item.find("title") is not None else ""
                        l = item.find("link").text if item.find("link") is not None else ""
                        d = item.find("description").text if item.find("description") is not None else ""
                        if t and l:
                            articles.append({
                                "title": t.strip(),
                                "title_fa": t.strip(),
                                "source": "واشنگتن پست (Washington Post)",
                                "url": l.strip(),
                                "snippet": d.strip(),
                            })
                    if articles:
                        break
            except Exception as e:
                print(f"⚠️ Washington Post fetch error on {feed_url}: {e}")
        return articles

    async def _fetch_bbc_world(self, client: httpx.AsyncClient) -> List[dict]:
        """واکشی اخبار بین‌المللی بی‌بی‌سی"""
        articles = []
        try:
            r = await client.get("https://feeds.bbci.co.uk/news/world/rss.xml", timeout=9.0)
            if r.status_code == 200:
                root = ET.fromstring(r.content)
                for item in root.findall(".//item")[:2]:
                    t = item.find("title").text if item.find("title") is not None else ""
                    l = item.find("link").text if item.find("link") is not None else ""
                    d = item.find("description").text if item.find("description") is not None else ""
                    if t:
                        articles.append({
                            "title": t.strip(),
                            "title_fa": t.strip(),
                            "source": "بی‌بی‌سی (BBC World)",
                            "url": l.strip(),
                            "snippet": d.strip(),
                        })
        except Exception as e:
            print(f"⚠️ BBC World fetch error: {e}")
        return articles

    async def fetch_latest_news_list(self, user_id: str) -> List[NewsArticle]:
        """واکشی و شماره‌گذاری اخبار از واشنگتن پست، ایران اینترنشنال و بی‌بی‌سی"""
        raw_items = []
        async with httpx.AsyncClient(headers=self.headers, follow_redirects=True) as client:
            iran_intl_task = self._fetch_iran_intl(client)
            wapo_task = self._fetch_washington_post(client)
            bbc_task = self._fetch_bbc_world(client)

            results = await asyncio.gather(iran_intl_task, wapo_task, bbc_task, return_exceptions=True)

            for res in results:
                if isinstance(res, list):
                    raw_items.extend(res)

        if not raw_items:
            return []

        # ترجمه سریع تیترهای انگلیسی به فارسی در یک پرامپت با هوش مصنوعی
        english_titles = [item["title"] for item in raw_items if "واشنگتن" in item["source"] or "بی‌بی‌سی" in item["source"]]
        if english_titles:
            prompt = "Translate these news headlines into concise, natural, journalistic Persian. Return each translation on a new line matching the input order:\n" + "\n".join(f"- {t}" for t in english_titles)
            try:
                trans_text = await gemini_client.async_generate_text(
                    prompt,
                    api_key=self.gemini_api_key,
                    model=self.gemini_model,
                    temperature=0.2,
                    max_output_tokens=500,
                    timeout=15.0
                )
                trans_lines = [line.lstrip("- •0123456789. ").strip() for line in trans_text.splitlines() if line.strip()]
                idx = 0
                for item in raw_items:
                    if ("واشنگتن" in item["source"] or "بی‌بی‌سی" in item["source"]) and idx < len(trans_lines):
                        item["title_fa"] = trans_lines[idx]
                        idx += 1
            except Exception as e:
                print(f"⚠️ Title translation error: {e}")

        # تبدیل به شیءهای کلاسی با شماره‌های منظم
        structured_articles: List[NewsArticle] = []
        for i, item in enumerate(raw_items, start=1):
            structured_articles.append(NewsArticle(
                id=i,
                title=item["title"],
                title_fa=item.get("title_fa", item["title"]),
                source=item["source"],
                url=item["url"],
                snippet=item["snippet"],
                content=item["snippet"]
            ))

        # ذخیره در کش کاربر
        self.user_news_cache[str(user_id)] = structured_articles
        return structured_articles

    async def get_full_news_report(self, user_id: str, news_id: int) -> Optional[str]:
        """تولید گزارش کامل، مشروح و همه‌جانبه فارسی از خبر انتخاب‌شده"""
        cached = self.user_news_cache.get(str(user_id), [])
        target_article: Optional[NewsArticle] = None

        for art in cached:
            if art.id == news_id:
                target_article = art
                break

        if not target_article:
            return None

        # واکشی محتوای کامل از صفحه خبر در صورت امکان
        article_text = target_article.snippet
        try:
            async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
                r = await client.get(target_article.url)
                if r.status_code == 200:
                    soup = BeautifulSoup(r.text, "html.parser")
                    paragraphs = [p.get_text(strip=True) for p in soup.find_all("p") if len(p.get_text(strip=True)) > 25]
                    if paragraphs:
                        article_text = "\n\n".join(paragraphs[:15])  # تا ۱۵ بند کامل
        except Exception as e:
            print(f"⚠️ Full article fetch error: {e}")

        prompt = f"""شما یک خبرنگار و تحلیل‌گر ارشد امور بین‌الملل هستید.
وظیفه شما ترجمه و ارائه گزارش «کامل، مفصل، بدون جا افتادن هیچ نکته‌ای و بند به بند» از خبر زیر به زبان فارسی سلیس و استاندارد است.

مشخصات خبر:
- تیتر اصلی: {target_article.title}
- منبع خبر: {target_article.source}
- لینک مستقیم: {target_article.url}
- متن/اطلاعات دریافت شده از خبرگزاری:
{article_text}

ساختار پاسخ شما باید به این صورت باشد:
📰 **تیتر کامل و رسمی خبر:** (تیتر جامع فارسی)
🏛 **منبع و مرجع:** {target_article.source}

📝 **خلاصه یک‌نگاهی:**
(خلاصه خبر در ۲ الی ۳ جمله)

📖 **گزارش مشروح و جزئیات کامل ماجرا:**
(کل ماجرا، ریشه‌ها، آمار و ارقام، اسامی، محل وقوع و جزئیات بند به بند با قلم حرفه‌ای روزنامه‌نگاری توضیح داده شود. هیچ بخش مهمی از خبر حذف نشود.)

💬 **اظهارات، موضع‌گیری‌ها و نقل‌قول‌ها:**
(نقل‌قول‌های رسمی مقامات، بیانیه‌ها و واکنش‌ها)

🌍 **پیامدها و چشم‌انداز موضوع:**
(تاثیر این خبر بر منطقه یا جهان)

🔗 **لینک منبع اصلی:** {target_article.url}
"""

        try:
            full_report = await gemini_client.async_generate_text(
                prompt,
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                temperature=0.3,
                max_output_tokens=1500,
                timeout=30.0
            )
            return full_report
        except Exception as e:
            return f"❌ در ترجمه و آماده‌سازی گزارش مشروح خطایی رخ داد: {e}"
