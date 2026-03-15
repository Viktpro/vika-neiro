import requests
import base64
import time
import uuid
from openai import OpenAI


# ========== DEEPSEEK ==========
class DeepSeekModel:
    def __init__(self):
        self.client = OpenAI(
            api_key="sk-c2311f9622cb4a81bfc5c43788c0a876",
            base_url="https://api.deepseek.com/v1"
        )
        self.model = "deepseek-chat"

    def ask(self, prompt, system_prompt=None):
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                temperature=0.7,
                max_tokens=1000
            )
            return response.choices[0].message.content
        except Exception as e:
            return f"❌ Ошибка DeepSeek: {e}"


# ========== GIGACHAT (только текст) ==========
class GigaChatModel:
    def __init__(self, client_id, client_secret):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expires = 0
        self.auth_string = base64.b64encode(f"{client_id}:{client_secret}".encode()).decode()

    def _get_access_token(self):
        url = "https://ngw.devices.sberbank.ru:9443/api/v2/oauth"
        rq_uid = str(uuid.uuid4())
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Accept': 'application/json',
            'RqUID': rq_uid,
            'Authorization': f'Basic {self.auth_string}'
        }
        data = {'scope': 'GIGACHAT_API_PERS'}
        try:
            requests.packages.urllib3.disable_warnings()
            response = requests.post(url, headers=headers, data=data, verify=False, timeout=30)
            if response.status_code == 200:
                result = response.json()
                self.access_token = result['access_token']
                self.token_expires = result['expires_at'] / 1000
                return True
        except Exception as e:
            print(f"Ошибка получения токена: {e}")
            return False
        return False

    def ask(self, prompt, system_prompt=None):
        if not self.access_token or time.time() > self.token_expires:
            if not self._get_access_token():
                return "❌ Ошибка подключения к GigaChat"

        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }
        data = {
            "model": "GigaChat",
            "messages": messages,
            "temperature": 0.7,
            "max_tokens": 1000
        }
        try:
            requests.packages.urllib3.disable_warnings()
            response = requests.post(url, headers=headers, json=data, verify=False, timeout=60)
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка GigaChat: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"


# ========== OPENROUTER (текст + фото) ==========
class OpenRouterModel:
    def __init__(self):
        self.api_key = "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"
        self.url = "https://openrouter.ai/api/v1/chat/completions"

        # Модели для текста
        self.text_models = {
            "mistral": "mistralai/mistral-7b-instruct",
            "llama": "meta-llama/llama-3.1-8b-instruct",
            "qwen": "qwen/qwen-2.5-7b-instruct",
            "gemma": "google/gemma-2-9b-it",
            "deepseek": "deepseek/deepseek-chat"
        }

        # Модели для распознавания изображений
        self.vision_models = {
            "llama": "meta-llama/llama-3.2-11b-vision-instruct",
            "mistral": "mistralai/pixtral-12b",
            "qwen": "qwen/qwen-2.5-7b-instruct",  # Не все модели имеют vision
            "gemma": "google/gemma-2-9b-it",
            "deepseek": "deepseek/deepseek-chat"
        }

    def ask(self, prompt, model="mistral", system_prompt=None):
        """Текстовый запрос"""
        try:
            messages = []
            if system_prompt:
                messages.append({"role": "system", "content": system_prompt})
            messages.append({"role": "user", "content": prompt})

            response = requests.post(
                url=self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": self.text_models.get(model, self.text_models["mistral"]),
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 1000
                },
                timeout=60
            )

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка {model}: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def ask_with_image(self, prompt, image_path, model="llama"):
        """Распознавание изображения через OpenRouter"""
        try:
            # Проверяем существование файла
            import os
            if not os.path.exists(image_path):
                return f"❌ Файл не найден: {image_path}"

            # Кодируем изображение
            with open(image_path, "rb") as f:
                image_data = f.read()
                base64_image = base64.b64encode(image_data).decode('utf-8')

            # Выбираем модель с поддержкой vision
            model_name = self.vision_models.get(model, self.vision_models["llama"])

            # Формируем запрос с изображением
            messages = [
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ]

            response = requests.post(
                url=self.url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json"
                },
                json={
                    "model": model_name,
                    "messages": messages,
                    "temperature": 0.7,
                    "max_tokens": 500
                },
                timeout=60
            )

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                error_text = response.text if response.text else "Нет описания ошибки"
                return f"❌ Ошибка Vision ({response.status_code}): {error_text}"

        except requests.exceptions.Timeout:
            return "❌ Таймаут при запросе к OpenRouter"
        except requests.exceptions.ConnectionError:
            return "❌ Ошибка соединения с OpenRouter"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"