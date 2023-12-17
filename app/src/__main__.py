import sys
import sqlite3
import sqlite_vss
import datetime
from pathlib import Path
from pydub import AudioSegment
from sentence_transformers import SentenceTransformer
import speech_recognition as sr

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
logger.addHandler(logging.StreamHandler(sys.stdout))

class Transcriber:
    audio_files = Path("/personal_logs/audio_files")
    markdown_files = Path("/personal_logs/markdown_files")
    embedder = SentenceTransformer("all-mpnet-base-v2")
    db = sqlite3.connect("/app/memory.db")

    def stampname(self, path:Path) -> str:
        stamp = path.lstat().st_mtime
        dtime = datetime.datetime.fromtimestamp(stamp)
        return dtime.strftime("%Y-%m-%d_%H-%M-%S")

    def transcribe_new(self):
        for audiofile in self.audio_files.glob("*.m4a"):
            logger.info("assessing file %s", audiofile.name)
            stampname = self.stampname(audiofile)
            if not (self.markdown_files / (stampname + ".md")).exists():
                logger.info("file %s is new, transcribing", audiofile.name)
                self.transcribe(audiofile.name)

    def transcribe(self, filename:str) -> str:
        log = self.audio_files / filename
        assert log.exists()
        r = sr.Recognizer()
        log_as_string = str(log.absolute())
        if log.suffix == ".m4a":
            sound = AudioSegment.from_file(log_as_string, "m4a")
            log_as_string = log_as_string.replace(".m4a", ".wav")
            sound.export(log_as_string, format="wav")

        audiofile = sr.AudioFile(log_as_string)
        with audiofile as source:
            audio = r.record(source)
        try:
            transcribed = r.recognize_whisper(audio, show_dict=True)
            logger.info("transcribed as: %s", transcribed["text"])
        except sr.UnknownValueError:
            logger.error("Whisper could not understand audio")
        except sr.RequestError as e:
            logger.error("Whisper error; {0}".format(e))

    def write_markdown_file(self,
                            filename:str,
                            content:str) -> None:
        """Write markdown file to disk"""
        (self.markdown_files / filename + ".md").write_text(content)

    def record_embeddings(self,
                          audio_file: str,
                          markdown_file: str,
                          transcribed_parts: list[dict],
                          ) -> None:
        for part in transcribed_parts:
            part["embeddings"] = self.embedder.encode(part["text"])
            self.db.execute("""\
            INSERT INTO memory (audio_file,
                                    markdown_file,
                                    text,
                                    start_time,
                                    embeddings) VALUES (?, ?, ?, ?, ?)""",
                            (audio_file, markdown_file, part["start"], part["text"], part["embeddings"]))

transcriber = Transcriber()
transcriber.transcribe_new()