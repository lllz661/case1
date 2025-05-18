# mainapi.py
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import os, shutil, ffmpeg
from main import transcribe_audio, extract_highlights, save_clips, generate_hashtags
import logging

# в начале файла
logging.basicConfig(level=logging.INFO)


app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

UPLOAD_FOLDER = "static/uploads"
CLIPS_FOLDER  = "static/clips_output"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(CLIPS_FOLDER, exist_ok=True)

# Переназначаем папку выходных клипов в main.py
import main
main.OUTPUT_DIR = CLIPS_FOLDER

@app.post("/process/")
async def process_video(video: UploadFile = File(...)):
    # сохраняем исходник
    path = os.path.join(UPLOAD_FOLDER, video.filename)
    with open(path, "wb") as buf:
        shutil.copyfileobj(video.file, buf)

    # конвертация в mp3 для Whisper
    audio_path = path.rsplit(".", 1)[0] + ".mp3"
    try:
        ffmpeg.input(path).output(audio_path).run(overwrite_output=True)
    except Exception as e:
        raise HTTPException(500, f"FFmpeg error: {e}")

    # 1. Транскрипция
    try:
        transcript_data = transcribe_audio(audio_path)
        transcript_text = transcript_data.get("text", "")
    except Exception as e:
        raise HTTPException(500, f"Transcription error: {e}")

    # 2. Вычисляем длительность и хайлайты
    try:
        duration = float(ffmpeg.probe(path)["format"]["duration"])
    except Exception:
        duration = 0.0
    highlights = extract_highlights(transcript_data, duration)

    # 3. Сохраняем клипы
    try:
        save_clips(path, highlights)
    except Exception as e:
        raise HTTPException(500, f"Clip saving error: {e}")

    # 4. Генерируем хэштеги
    try:
        hashtags = generate_hashtags(transcript_data)
    except Exception:
        hashtags = {}
    # в конце process_video, перед return:
    logging.info(f"Generated hashtags: {hashtags}")

    return JSONResponse({
        "transcript": transcript_text,
        "highlights": highlights,
        "hashtags": hashtags
    })
