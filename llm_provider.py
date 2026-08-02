import base64
from abc import ABC, abstractmethod
from openai import OpenAI

class BaseLLMProvider(ABC):
    @abstractmethod
    def analyze_screen(self, image_bytes: bytes, system_prompt: str, user_prompt: str) -> str:
        pass

class OpenAICompatibleProvider(BaseLLMProvider):
    def __init__(self, api_key: str, base_url: str, model_name: str):
        self.client = OpenAI(api_key=api_key, base_url=base_url)
        self.model_name = model_name

    def analyze_screen(self, image_bytes: bytes, system_prompt: str, user_prompt: str) -> str:
        b64_img = base64.b64encode(image_bytes).decode('utf-8')
        kwargs = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system_prompt},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64_img}"}}
                    ]
                }
            ],
            "max_tokens": 1024,
            "temperature": 0.1
        }
        if "cerebras" not in str(self.client.base_url).lower():
            kwargs["response_format"] = {"type": "json_object"}
            
        response = self.client.chat.completions.create(**kwargs)
        return response.choices[0].message.content

class GoogleGenAIProvider(BaseLLMProvider):
    def __init__(self, api_key: str, model_name: str = "gemini-3.1-flash-lite"):
        from google import genai
        self.client = genai.Client(api_key=api_key)
        self.model_name = model_name

    def analyze_screen(self, image_bytes: bytes, system_prompt: str, user_prompt: str) -> str:
        from PIL import Image
        from google.genai import types
        import io
        img = Image.open(io.BytesIO(image_bytes))
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=[user_prompt, img],
            config=types.GenerateContentConfig(
                system_instruction=system_prompt
            )
        )
        return response.text

