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


# ========== OPENROUTER ==========
class OpenRouterModel:
    def __init__(self):
        self.api_key = "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"
        self.url = "https://openrouter.ai/api/v1/chat/completions"
        self.models = {
            "mistral": "mistralai/mistral-7b-instruct",
            "llama": "meta-llama/llama-3.1-8b-instruct",
            "qwen": "qwen/qwen-2.5-7b-instruct",
            "gemma": "google/gemma-2-9b-it",
            "deepseek": "deepseek/deepseek-chat"
        }

    def ask(self, prompt, model="mistral", system_prompt=None):
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
                    "model": self.models.get(model, self.models["mistral"]),
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


# ========== GIGACHAT (ИСПРАВЛЕННЫЙ) ==========
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

    def ask_with_image_simple(self, prompt, image_path):
        """Простой и надёжный запрос с фото - только для распознавания объектов"""
        if not self.access_token or time.time() > self.token_expires:
            if not self._get_access_token():
                return "❌ Ошибка подключения"

        try:
            with open(image_path, "rb") as f:
                image_base64 = base64.b64encode(f.read()).decode('utf-8')
        except Exception as e:
            return f"❌ Ошибка чтения фото: {e}"

        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }

        # Максимально простой формат
        data = {
            "model": "GigaChat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "temperature": 0.3,  # Минимум творчества
            "max_tokens": 50  # Только короткий ответ
        }

        try:
            requests.packages.urllib3.disable_warnings()
            response = requests.post(url, headers=headers, json=data, verify=False, timeout=60)

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"