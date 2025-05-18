# run.py
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.wsgi import WSGIMiddleware

from app import app as flask_app
from mainapi import app as fastapi_app

combined_app = FastAPI()

# Сначала монтируем FastAPI под /api
combined_app.mount("/api", fastapi_app)

# А только потом — Flask под / (все остальные запросы)
combined_app.mount("/", WSGIMiddleware(flask_app))

if __name__ == "__main__":
    uvicorn.run("run:combined_app", host="127.0.0.1", port=8000, reload=False)
