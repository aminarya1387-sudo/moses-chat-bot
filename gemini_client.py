# gemini_client.py
"""کلاینت سبک برای صحبت با Gemini API (بدون نیاز به SDK اضافه)"""

import requests

GEMINI_API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"


def generate_text(prompt: str, api_key: str, model: str,
                   temperature: float = 0.7, max_output_tokens: int = 1024,
                   timeout: int = 30) -> str:
    """یک پرامپت رو به Gemini می‌فرسته و متن پاسخ رو برمی‌گردونه"""
    url = GEMINI_API_URL.format(model=model)

    response = requests.post(
        url,
        params={"key": api_key},
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
