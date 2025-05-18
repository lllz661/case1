# app.py — Flask frontend
import os
from flask import Flask, render_template, request
import requests

app = Flask(__name__)
UPLOAD_FOLDER = "static/uploads"
OUTPUT_FOLDER = "static/clips_output"
# Создаем папки, если не существуют
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def clear_old_clips(folder):
    """
    Удаляем все предыдущие клипы перед новой загрузкой
    """
    for fname in os.listdir(folder):
        if fname.startswith("highlight_") and fname.endswith(".mp4"):
            try:
                os.remove(os.path.join(folder, fname))
            except OSError:
                pass

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        file = request.files.get("video")
        if not file or file.filename == "":
            return "No file provided", 400

        # Очищаем старые клипы
        clear_old_clips(OUTPUT_FOLDER)

        # Сохраняем загруженное видео
        upload_path = os.path.join(UPLOAD_FOLDER, file.filename)
        file.save(upload_path)

        # Отправляем на FastAPI для обработки
        with open(upload_path, "rb") as f:
            resp = requests.post(
                "http://127.0.0.1:8000/api/process/",
                files={"video": f}
            )
        if resp.status_code != 200:
            return f"Processing error: {resp.status_code}", 500

        data = resp.json()
        highlights = data.get("highlights", [])
        hashtags = data.get("hashtags", {})
        transcript = data.get("transcript", "")

        return render_template(
            "result.html",
            highlights=highlights,
            hashtags=hashtags,
            transcript=transcript
        )

    return render_template("index.html")

if __name__ == "__main__":
    app.run(port=5000, debug=True)
