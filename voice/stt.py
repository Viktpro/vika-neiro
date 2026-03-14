import speech_recognition as sr
import subprocess
import tempfile
import os
from pathlib import Path


class STT:
    """Speech-to-Text модуль для Railway"""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        print("✅ STT инициализирован")

    def _convert_ogg_to_wav(self, ogg_path, wav_path):
        """Конвертирует OGG в WAV используя ffmpeg"""
        try:
            # Ищем ffmpeg в разных местах
            ffmpeg_paths = [
                "/usr/bin/ffmpeg",
                "/usr/local/bin/ffmpeg",
                "ffmpeg"  # надеемся на PATH
            ]

            ffmpeg_cmd = None
            for path in ffmpeg_paths:
                if os.path.exists(path) or path == "ffmpeg":
                    ffmpeg_cmd = path
                    break

            if not ffmpeg_cmd:
                print("❌ FFmpeg не найден")
                return False

            cmd = [
                ffmpeg_cmd, '-i', str(ogg_path),
                '-ar', '16000',
                '-ac', '1',
                '-y', str(wav_path)
            ]
            result = subprocess.run(cmd, capture_output=True, timeout=30)
            return result.returncode == 0

        except Exception as e:
            print(f"Ошибка конвертации: {e}")
            return False

    def audio_to_text(self, ogg_file_path):
        """
        Преобразует аудиофайл в текст через Google Speech Recognition
        """
        ogg_path = Path(ogg_file_path)
        wav_path = ogg_path.with_suffix('.wav')

        # Конвертируем OGG в WAV
        if not self._convert_ogg_to_wav(ogg_path, wav_path):
            return "❌ Ошибка конвертации аудио"

        try:
            # Загружаем аудиофайл
            with sr.AudioFile(str(wav_path)) as source:
                audio = self.recognizer.record(source)

            # Используем Google Speech Recognition
            text = self.recognizer.recognize_google(audio, language='ru-RU')

            # Удаляем временный файл
            try:
                wav_path.unlink()
            except:
                pass

            return text

        except sr.UnknownValueError:
            return "🔇 Не удалось распознать речь"
        except sr.RequestError as e:
            return f"❌ Ошибка сети: {e}"
        except Exception as e:
            return f"❌ Ошибка: {str(e)}"