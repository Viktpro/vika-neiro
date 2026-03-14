import subprocess
from pathlib import Path
import io


class TTS:
    """Text-to-Speech модуль на базе Google TTS"""

    def __init__(self):
        self.language = 'ru'  # по умолчанию русский
        print("✅ TTS инициализирован")

    def set_language(self, lang):
        """Устанавливает язык озвучки (ru/en)"""
        if lang in ['ru', 'en']:
            self.language = lang
            return True
        return False

    def text_to_ogg(self, text, output_path):
        """
        Преобразует текст в OGG аудиофайл через Google TTS
        """
        try:
            from gtts import gTTS

            # Полный путь к ffmpeg
            ffmpeg_path = r"C:\ffmpeg\bin\ffmpeg.exe"

            # Создаём временный MP3 в памяти
            mp3_buffer = io.BytesIO()
            tts = gTTS(text=text, lang=self.language, slow=False)
            tts.write_to_fp(mp3_buffer)
            mp3_buffer.seek(0)

            # Сохраняем MP3 во временный файл
            temp_mp3 = Path(output_path).with_suffix('.temp.mp3')
            with open(temp_mp3, 'wb') as f:
                f.write(mp3_buffer.getvalue())

            # Конвертируем MP3 в OGG
            cmd = [
                ffmpeg_path, '-i', str(temp_mp3),
                '-c:a', 'libvorbis',
                '-q:a', '4',
                '-y', str(output_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True)

            # Удаляем временный файл
            temp_mp3.unlink()

            return output_path

        except ImportError:
            print("❌ Установи gtts: pip install gtts")
            return None
        except Exception as e:
            print(f"Ошибка синтеза речи: {e}")
            return None