# image_generator.py

import requests
import urllib.parse
from typing import Optional

class ImageGenerator:
    """کلاس تولید عکس با استفاده از Pollinations.ai"""
    
    def __init__(self):
        # آدرس پایه API
        self.base_url = "https://image.pollinations.ai/prompt/"
    
    def generate_image(self, prompt: str) -> Optional[bytes]:
        """تولید عکس بر اساس پرامپت کاربر"""
        try:
            # پرامپت رو برای URL آماده می‌کنیم
            encoded_prompt = urllib.parse.quote(prompt)
            
            # ساخت URL نهایی (ابعاد ۱۰۲۴ در ۱۰۲۴)
            url = f"{self.base_url}{encoded_prompt}?width=1024&height=1024&seed=42"
            
            # درخواست GET
            response = requests.get(url, timeout=60)
            response.raise_for_status()
            
            # محتوای عکس رو برمی‌گردونیم
            return response.content
            
        except Exception as e:
            print(f"❌ Image generation error: {e}")
            return None