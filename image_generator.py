# image_generator.py
"""کلاس غیرمسدودکننده و سریع برای تولید تصویر با استفاده از Pollinations.ai"""

import random
import urllib.parse
from typing import Optional
import httpx


class ImageGenerator:
    """تولید تصویر آسنکرون با استفاده از هوش مصنوعی Pollinations.ai"""

    def __init__(self):
        self.base_url = "https://image.pollinations.ai/prompt/"

    async def generate_image(self, prompt: str, width: int = 1024, height: int = 1024) -> Optional[bytes]:
        """تولید عکس بر اساس پرامپت کاربر با seed تصادفی و به صورت آسنکرون"""
        try:
            encoded_prompt = urllib.parse.quote(prompt.strip())
            # ایجاد یک seed کاملاً تصادفی برای تنوع در خروجی
            random_seed = random.randint(1, 9999999)
            url = f"{self.base_url}{encoded_prompt}?width={width}&height={height}&seed={random_seed}&nologo=true"

            async with httpx.AsyncClient(timeout=httpx.Timeout(45.0, connect=10.0)) as client:
                response = await client.get(url)
                response.raise_for_status()

                # اعتبارسنجی ساده نوع محتوا
                content_type = response.headers.get("content-type", "")
                if "image" in content_type or len(response.content) > 1000:
                    return response.content

                print(f"⚠️ Unexpected content type: {content_type}")
                return response.content

        except Exception as e:
            print(f"❌ Async Image generation error: {e}")
            return None

    def generate_image_sync(self, prompt: str) -> Optional[bytes]:
        """متد همگام برای سازگاری"""
        import asyncio
        return asyncio.run(self.generate_image(prompt))