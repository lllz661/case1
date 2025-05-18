# main.py — логика обработки видео
import os
import json
import re
import subprocess
from datetime import timedelta
from openai import OpenAI
import ffmpeg

os.environ["PATH"] += os.pathsep + r"C:\\ffmpeg\\bin"

OUTPUT_DIR = "clips_output"
os.makedirs(OUTPUT_DIR, exist_ok=True)

KEYWORDS = ['вау', 'круто', 'важно', 'смотрите']
client = OpenAI(api_key="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")

def transcribe_audio(file_path: str) -> dict:
    with open(file_path, "rb") as audio_file:
        resp = client.audio.transcriptions.create(
            file=audio_file,
            model="whisper-1",
            response_format="verbose_json",
        )
    data = resp.model_dump()
    segments = [
        seg for seg in data.get("segments", [])
        if seg.get("no_speech_prob", 0) < 0.5 and seg.get("text", '').strip()
    ]
    if not segments:
        data["segments"] = generate_fallback_segments(file_path)
        data["text"] = ""
    else:
        data["segments"] = segments
        data["text"] = " ".join(seg["text"] for seg in segments).strip()
    return data

def generate_fallback_segments(file_path: str, max_clips: int = 5) -> list:
    try:
        duration = float(ffmpeg.probe(file_path)["format"]["duration"])
    except:
        duration = max_clips * 5
    seg_len = duration / max_clips
    return [
        {"start": round(i*seg_len,2), "end": round((i+1)*seg_len,2), "text": ""}
        for i in range(max_clips)
    ]

def save_srt(transcript: dict, srt_path: str):
    with open(srt_path, "w", encoding="utf-8") as f:
        for i, seg in enumerate(transcript.get("segments", []), 1):
            start = timedelta(seconds=seg["start"])
            end   = timedelta(seconds=seg["end"])
            text  = seg["text"].strip()
            f.write(f"{i}\n{start} --> {end}\n{text}\n\n")

def fallback_highlights(transcript: dict, duration: float, max_clips: int = 5) -> list:
    out = []
    for seg in transcript.get("segments", []):
        t = seg["text"].lower()
        if any(kw in t for kw in KEYWORDS):
            out.append({"start":seg["start"],"end":seg["end"],"text":seg["text"]})
        if len(out) >= max_clips: break
    return out or generate_fallback_segments("", max_clips)

def extract_highlights(transcript: dict, duration: float, max_clips: int = 5) -> list:
    if not transcript.get("text"):
        return fallback_highlights(transcript, duration, max_clips)

    segments = [
        {"start": round(s["start"],2), "end": round(s["end"],2), "text": s["text"].strip()}
        for s in transcript["segments"]
    ]
    prompt = (
        f"Видео {duration:.2f}s, сегменты:\n{json.dumps(segments, ensure_ascii=False)}\n"
        f"Выбери до {max_clips} самых интересных и верни JSON-массив объектов start/end/text."
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"Возвращай только JSON."},
                {"role":"user","content":prompt}
            ],
            temperature=0.2,
            max_tokens=1000
        )
        arr = json.loads(re.search(r"(\[.*\])", resp.choices[0].message.content, re.S).group(1))
        uniq, out = set(), []
        for s in arr:
            if s["text"] not in uniq and len(s["text"]) > 3:
                uniq.add(s["text"])
                out.append(s)
                if len(out) >= max_clips: break
        return out
    except:
        return fallback_highlights(transcript, duration, max_clips)

def save_clips(video_path: str, highlights: list):
    for i, seg in enumerate(highlights, 1):
        d = seg["end"] - seg["start"]
        if d < 0.5: continue
        out = os.path.join(OUTPUT_DIR, f"highlight_{i}.mp4")
        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seg["start"]),
            "-i", video_path,
            "-t", str(d),
            "-vf", "crop='ih*9/16:ih:(iw-ih*9/16)/2:0',scale=720:1280",
            "-c:v", "libx264", "-preset","fast","-crf","23",
            "-c:a","aac","-b:a","128k",
            out
        ]
        subprocess.run(cmd, check=True)
        import time

        def wait_for_file(path, timeout=10):
            for _ in range(timeout * 10):
                if os.path.exists(path) and os.path.getsize(path) > 0:
                    return True
                time.sleep(0.1)
            return False


def generate_hashtags(transcript: dict, count: int = 10) -> dict:
    full = transcript.get("text", "").strip()
    if not full:
        full = " ".join(s["text"] for s in transcript.get("segments", []))
    if not full:
        return {}
    prompt = (
        f"Ты опытный SMM-специалист. На основе следующего текста видео сгенерируй список из {count} "
        f"популярных, релевантных и цепляющих хэштегов на русском языке для платформ TikTok, Instagram и YouTube Shorts. "
        f"Хэштеги должны отражать суть видео, быть трендовыми и способствовать росту охвата.\n\n"
        f"Текст видео:\n\"{full}\"\n\n"
        f"📌 Условия:\n"
        f"- Хэштеги должны быть короткими, конкретными и легко читаемыми.\n"
        f"- Не добавляй пояснений — только JSON.\n\n"
        f"Формат ответа:\n{{\"#тема1\": популярность (1-100), \"#тема2\": ...}}"
    )

    try:
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role":"system","content":"Ты SMM-ассистент."},
                {"role":"user","content":prompt}
            ],
            temperature=0.7,
            max_tokens=300
        )
        data = json.loads(re.search(r"(\{[\s\S]*\})", resp.choices[0].message.content).group(1))
        return {
            (k if k.startswith("#") else "#"+k): v
            for k, v in data.items() if isinstance(v, int) and 1<=v<=100
        }
    except:
        return {}
