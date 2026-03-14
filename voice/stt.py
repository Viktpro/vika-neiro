import speech_recognition as sr
import subprocess
from pathlib import Path
import os


class STT:
    """Speech-to-Text модуль на базе Google Speech Recognition"""

    def __init__(self):
        self.recognizer = sr.Recognizer()
        print("✅ SpeechRecognition инициализирован")

    def _convert_ogg_to_wav(self, ogg_path, wav_path):
        """Конвертирует OGG в WAV используя ffmpeg"""
        try:
            # Проверяем наличие ffmpeg
            ffmpeg_path = self._find_ffmpeg()
            if not ffmpeg_path:
                return False

            cmd = [
                ffmpeg_path, '-i', str(ogg_path),
                '-ar', '16000',
                '-ac', '1',
                '-y', str(wav_path)
            ]
            subprocess.run(cmd, check=True, capture_output=True, timeout=30)
            return True
        except Exception as e:
            print(f"Ошибка конвертации: {e}")
            return False

    def _find_ffmpeg(self):
        """Ищет ffmpeg в системе"""
        possible_paths = [
            r"C:\ffmpeg\bin\ffmpeg.exe",
            "/usr/bin/ffmpeg",
            "/usr/local/bin/ffmpeg"
        ]
        for path in possible_paths:
            if os.path.exists(path):
                return path
        return "ffmpeg"  # надеемся, что в PATH

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