# web_search.py
"""
ماژول جستجوی زنده در اینترنت و بررسی اخبار روز دنیا
مجهز به موتور جستجوی DuckDuckGo و خلاصه‌سازی هوشمند با Gemini 3.5 Flash Lite
بدون محدودیت IP یا مسدودسازی توسط گوگل
"""

from typing import List, Dict
from bs4 import BeautifulSoup
import httpx
import gemini_client


class WebSearch:
    """کلاس جستجوی زنده، پرسرعت و پایدار در اینترنت"""

    def __init__(self, gemini_api_key: str = "", gemini_model: str = "gemini-3.5-flash-lite"):
        self.gemini_api_key = gemini_api_key
        self.gemini_model = gemini_model
        self.headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "fa,en;q=0.5",
        }

    async def search_duckduckgo(self, query: str, max_results: int = 6) -> List[Dict[str, str]]:
        """جستجوی زنده در وب با DuckDuckGo بدون مسدودسازی و با سرعت بالا"""
        results = []
        endpoints = [
            ("https://html.duckduckgo.com/html/", {"q": query}),
            ("https://lite.duckduckgo.com/lite/", {"q": query})
        ]

        async with httpx.AsyncClient(headers=self.headers, timeout=12.0, follow_redirects=True) as client:
            for url, data in endpoints:
                try:
                    response = await client.post(url, data=data)
                    if response.status_code != 200:
                        continue

                    soup = BeautifulSoup(response.text, "html.parser")

                    # استخراج از فرمت HTML DuckDuckGo
                    result_divs = soup.find_all("div", class_="result")
                    for div in result_divs:
                        title_tag = div.find("a", class_="result__a")
                        snippet_tag = div.find("a", class_="result__snippet")
                        url_tag = div.find("a", class_="result__url")

                        if title_tag and snippet_tag:
                            title = title_tag.get_text(strip=True)
                            snippet = snippet_tag.get_text(strip=True)
                            link = url_tag.get("href") if url_tag else title_tag.get("href", "")

                            if title and snippet:
                                results.append({
                                    "title": title,
                                    "snippet": snippet,
                                    "link": link
                                })
                                if len(results) >= max_results:
                                    break

                    # اگر روش اول نتیجه داد، خروج از حلقه
                    if results:
                        break

                    # پشتیبان: فرمت جدول نسخه Lite
                    rows = soup.find_all("tr")
                    for row in rows:
                        link_tag = row.find("a", class_="result-link")
                        snippet_td = row.find("td", class_="result-snippet")
                        if link_tag and snippet_td:
                            results.append({
                                "title": link_tag.get_text(strip=True),
                                "snippet": snippet_td.get_text(strip=True),
                                "link": link_tag.get("href", "")
                            })
                            if len(results) >= max_results:
                                break

                    if results:
                        break

                except Exception as e:
                    print(f"⚠️ Search endpoint error ({url}): {e}")

        return results

    async def search_and_summarize(self, query: str) -> str:
        """
        جستجوی زنده در اینترنت و تحلیل/خلاصه‌سازی هوشمند پاسخ با Gemini 3.5 Flash Lite
        """
        # ۱. واکشی اطلاعات زنده از موتور جستجو
        search_items = await self.search_duckduckgo(query, max_results=6)

        if not search_items:
            return (
                f"❌ متأسفانه در حال حاضر نتوانستم اطلاعات زنده‌ای درباره «{query}» در اینترنت پیدا کنم.\n"
                "لطفاً با کلمات کلیدی دیگری امتحان کنید."
            )

        # ۲. قالب‌بندی نتایج جستجو برای هوش مصنوعی
        context_blocks = []
        sources = []
        for item in search_items:
            context_blocks.append(f"• عنوان: {item['title']}\n  خلاصه: {item['snippet']}")
            if item.get("link"):
                sources.append(item["link"])

        search_context = "\n\n".join(context_blocks)

        # ۳. ارسال به Gemini 3.5 Flash Lite برای ارائه پاسخ ساختاریافته و تحلیلی
        prompt = f"""شما یک دستیار هوشمند، آگاه و مسلط به زبان فارسی هستید.
کاربر این سوال یا درخواست را مطرح کرده است: "{query}"

در ادامه، جدیدترین و تازه‌ترین نتایج جستجوی زنده در وب درباره این موضوع آورده شده است:
---
{search_context}
---

وظایف شما:
1. بر اساس این داده‌های زنده و به روز اینترنت، پاسخی دقیق، جامع، شیوا و کاملاً به‌روز ارائه بده.
2. اگر کاربر درباره اخبار روز دنیا، اخبار ایران یا رویدادهای جاری سوال پرسیده، اخبار را به صورت دسته‌بندی‌شده و با بولت‌پوینت‌های جذاب، مهم‌ترین تیترها و جزئیات کلیدی توضیح بده.
3. از ادبیات محترمانه، خوانا و روان فارسی استفاده کن.
4. در پایان، اشاره کن که این اطلاعات بر اساس تازه‌ترین نتایج جستجوی زنده وب گردآوری شده است.
"""

        try:
            ai_summary = await gemini_client.async_generate_text(
                prompt,
                api_key=self.gemini_api_key,
                model=self.gemini_model,
                temperature=0.4,
                max_output_tokens=1024,
                timeout=25.0,
            )
            return ai_summary
        except Exception as e:
            print(f"⚠️ AI Summarization fallback error: {e}")
            # بازگشت نتایج خام در صورت بروز خطای مدل
            fallback = f"🌐 **نتایج جستجوی زنده برای «{query}»:**\n\n"
            for item in search_items[:4]:
                fallback += f"📌 **{item['title']}**\n{item['snippet']}\n\n"
            return fallback