from fastapi import FastAPI

from takab_api.health import router as health_router

app = FastAPI(title="TAKAB API", version="0.1.0")
app.include_router(health_router)
