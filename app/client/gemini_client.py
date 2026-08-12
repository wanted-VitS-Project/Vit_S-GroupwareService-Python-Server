from google import genai

from app.core.config import Settings
from app.core.exceptions import VitamateAiGenerateError


class GeminiClient:
    # Gemini API를 호출해 비타메이트 분석 결과 텍스트를 생성합니다.
    def __init__(self, settings: Settings):
        self._model_name = settings.gemini_model
        self._client = genai.Client(api_key=settings.gemini_api_key)

    def generate_text(self, prompt: str) -> str:
        try:
            response = self._client.models.generate_content(
                model=self._model_name,
                contents=prompt,
            )
        except Exception as exc:
            # 외부 AI 예외는 안전한 메시지로 감싸 worker가 처리하게 합니다.
            raise VitamateAiGenerateError("Gemini analysis request failed") from exc

        if not response.text or not response.text.strip():
            raise VitamateAiGenerateError("Gemini returned empty response")

        return response.text.strip()
