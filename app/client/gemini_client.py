import google.generativeai as genai

from app.core.config import Settings


class GeminiClient:
    # Gemini API 호출을 담당하는 client

    def __init__(self, settings: Settings):
        self._model_name = settings.gemini_model
        genai.configure(api_key=settings.gemini_api_key)
        self._model = genai.GenerativeModel(self._model_name)

    def generate_text(self, prompt: str) -> str:
        # 프롬프트를 Gemini에 전달하고 텍스트 응답을 반환한다.
        response = self._model.generate_content(prompt)

        if not response.text or not response.text.strip():
            raise RuntimeError("Gemini returned empty response.")

        return response.text.strip()