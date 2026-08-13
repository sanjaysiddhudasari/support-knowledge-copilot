from fastapi import FastAPI

app = FastAPI(title="Support Knowledge Copilot", version="0.1.0")

@app.get("/health")
async def health():
    return {"status": "ok"}
