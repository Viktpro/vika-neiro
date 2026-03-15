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

    def ask_with_image(self, prompt, base64_image, model="llama"):
        """Отправляет запрос с изображением"""
        try:
            # Модели с поддержкой vision
            vision_models = {
                "llama": "meta-llama/llama-3.2-11b-vision-instruct",
                "mistral": "mistralai/pixtral-12b",
                "qwen": "qwen/qwen-2.5-7b-instruct",
                "gemma": "google/gemma-2-9b-it",
                "deepseek": "deepseek/deepseek-chat"
            }

            model_name = vision_models.get(model, vision_models["llama"])

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
                    "max_tokens": 1000
                },
                timeout=60
            )

            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            else:
                return f"❌ Ошибка {model} (vision): {response.status_code}"
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
        """Получает токен доступа к GigaChat"""
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
            else:
                print(f"Ошибка получения токена: {response.status_code}")
                return False
        except Exception as e:
            print(f"Ошибка при получении токена: {e}")
            return False

    def ask(self, prompt, system_prompt=None):
        """Обычный текстовый запрос"""
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
            elif response.status_code == 401:
                # Токен истёк, пробуем ещё раз
                if self._get_access_token():
                    return self.ask(prompt, system_prompt)
                else:
                    return "❌ Ошибка авторизации GigaChat"
            else:
                return f"❌ Ошибка GigaChat: {response.status_code}"
        except Exception as e:
            return f"❌ Ошибка: {e}"

    def ask_with_image(self, prompt, image_path):
        """Отправляет запрос с изображением в GigaChat (ИСПРАВЛЕННАЯ ВЕРСИЯ)"""
        if not self.access_token or time.time() > self.token_expires:
            if not self._get_access_token():
                return "❌ Ошибка подключения к GigaChat"

        # Кодируем изображение в base64
        try:
            with open(image_path, "rb") as f:
                image_data = f.read()
                image_base64 = base64.b64encode(image_data).decode('utf-8')
                print(f"✅ Изображение закодировано, размер: {len(image_data)} байт")
        except Exception as e:
            return f"❌ Ошибка при чтении изображения: {e}"

        url = "https://gigachat.devices.sberbank.ru/api/v1/chat/completions"

        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'Authorization': f'Bearer {self.access_token}'
        }

        # ПРАВИЛЬНЫЙ формат для GigaChat с изображением
        data = {
            "model": "GigaChat",
            "messages": [
                {
                    "role": "user",
                    "content": prompt  # Текст запроса
                }
            ],
            "temperature": 0.7,
            "max_tokens": 1000,
            "attachments": [  # Изображение как attachment
                {
                    "type": "image",
                    "content": image_base64,
                    "mime_type": "image/jpeg"
                }
            ]
        }

        try:
            print("📤 Отправка запроса в GigaChat Vision...")
            requests.packages.urllib3.disable_warnings()
            response = requests.post(url, headers=headers, json=data, verify=False, timeout=60)

            print(f"📥 Статус ответа: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                return result['choices'][0]['message']['content']
            elif response.status_code == 401:
                print("🔄 Токен истёк, обновляем...")
                if self._get_access_token():
                    return self.ask_with_image(prompt, image_path)
                else:
                    return "❌ Ошибка авторизации GigaChat"
            else:
                error_text = response.text if response.text else "Нет описания ошибки"
                return f"❌ Ошибка GigaChat Vision ({response.status_code}): {error_text}"

        except requests.exceptions.Timeout:
            return "❌ Таймаут при запросе к GigaChat Vision"
        except requests.exceptions.ConnectionError:
            return "❌ Ошибка соединения с GigaChat Vision"
        except Exception as e:
            return f"❌ Ошибка при запросе к GigaChat Vision: {str(e)}"


# ========== ТЕСТОВАЯ ФУНКЦИЯ ==========
if __name__ == "__main__":
    # Тестирование работы с GigaChat
    print("🔍 Тестирование GigaChat...")

    # Тестовые данные
    test_client_id = "019c9dd5-08ad-714c-8358-5945e8c15fee"
    test_client_secret = "90a0e997-4015-458f-907a-d59f5d9e68a7"

    giga = GigaChatModel(test_client_id, test_client_secret)

    # Тест текстового запроса
    print("\n📝 Тест текстового запроса:")
    result = giga.ask("Привет! Как дела?")
    print(result)

    print("\n✅ Тест завершён")