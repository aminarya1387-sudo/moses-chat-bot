# gemini_client.py
"""کلاینت سبک، مدرن و فوق‌العاده سریع بر پایه httpx برای ارتباط آسنکرون با Gemini API"""

from typing import Optional
import httpx
import requests

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

# کلاینت آسنکرون پایدار با قابلیت استفاده مجدد از کانکشن‌ها (Connection Pooling)
_async_client: Optional[httpx.AsyncClient] = None


def get_async_client() -> httpx.AsyncClient:
    global _async_client
    if _async_client is None or _async_client.is_closed:
        _async_client = httpx.AsyncClient(
            timeout=httpx.Timeout(25.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=20, max_connections=50),
            headers={"Content-Type": "application/json"},
        )
    return _async_client


async def async_generate_text(
    prompt: str,
    api_key: str,
    model: str,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    timeout: float = 25.0,
) -> str:
    """ارسال آسنکرون و سریع پرامپت به Gemini بدون مسدود کردن Event Loop"""
    url = GEMINI_API_URL.format(model=model)
    client = get_async_client()

    headers = {}
    if api_key:
        headers["x-goog-api-key"] = str(api_key)
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": temperature,
            "maxOutputTokens": max_output_tokens,
        },
    }

    response = await client.post(
        url,
        params={"key": api_key},
        headers=headers,
        json=payload,
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "no candidates returned")
        raise ValueError(f"Gemini returned no response ({reason})")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text


def generate_text(
    prompt: str,
    api_key: str,
    model: str,
    temperature: float = 0.7,
    max_output_tokens: int = 1024,
    timeout: int = 30,
) -> str:
    """نسخه همگام (Sync) برای سازگاری با کدهای قدیمی"""
    url = GEMINI_API_URL.format(model=model)

    response = requests.post(
        url,
        params={"key": api_key},
        headers={"x-goog-api-key": api_key},
        json={
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": temperature,
                "maxOutputTokens": max_output_tokens,
            },
        },
        timeout=timeout,
    )
    response.raise_for_status()
    data = response.json()

    candidates = data.get("candidates") or []
    if not candidates:
        reason = data.get("promptFeedback", {}).get("blockReason", "no candidates returned")
        raise ValueError(f"Gemini returned no response ({reason})")

    parts = candidates[0].get("content", {}).get("parts") or []
    text = "".join(part.get("text", "") for part in parts).strip()
    if not text:
        raise ValueError("Gemini returned an empty response")
    return text
