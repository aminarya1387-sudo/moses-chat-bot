# web_search.py

import requests
from bs4 import BeautifulSoup
from googlesearch import search
import time
import urllib.parse

class WebSearch:
    """کلاس جستجوی اینترنت"""
    
    def __init__(self):
        self.user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    
    def search_google(self, query: str, num_results: int = 3) -> list:
        """جستجو در گوگل و برگرداندن لینک‌ها"""
        try:
            results = []
            for url in search(query, num_results=num_results, lang="fa"):
                results.append(url)
            return results
        except Exception as e:
            print(f"Search error: {e}")
            return []
    
    def get_page_content(self, url: str) -> str:
        """دریافت محتوای متن از یک صفحه"""
        try:
            headers = {"User-Agent": self.user_agent}
            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # حذف تگ‌های غیرضروری
            for tag in soup(['script', 'style', 'nav', 'header', 'footer', 'aside']):
                tag.decompose()
            
            # استخراج متن
            text = soup.get_text(separator=' ', strip=True)
            
            # محدود کردن به ۲۰۰۰ کاراکتر
            if len(text) > 2000:
                text = text[:2000] + "..."
            
            return text
            
        except Exception as e:
            print(f"Page content error: {e}")
            return ""
    
    def search_and_summarize(self, query: str) -> str:
        """جستجو و خلاصه‌سازی نتایج"""
        
        # ۱. جستجو و دریافت لینک‌ها
        urls = self.search_google(query)
        
        if not urls:
            return "❌ نتیجه‌ای برای جستجوی شما پیدا نشد."
        
        # ۲. دریافت محتوای صفحات
        all_content = []
        for url in urls[:3]:  # فقط ۳ لینک اول
            content = self.get_page_content(url)
            if content:
                all_content.append(f"📎 منبع: {url}\n{content}\n")
        
        if not all_content:
            return "❌ نتواستم محتوایی از صفحات پیدا کنم."
        
        # ۳. ترکیب محتوا
        combined = "\n\n".join(all_content)
        
        return combined