from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from demo.api.routers.appointments import router as appointments_router
from demo.api.routers.auth import router as auth_router

app = FastAPI(
    title="SpecNetra Target Service",
    version="1.0.0",
    description="Healthcare appointment management — SpecNetra demo target",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/healthz")
async def healthz():
    return {"status": "ok"}


app.include_router(auth_router)
app.include_router(appointments_router)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("demo.api.main:app", host="0.0.0.0", port=8001, reload=True)
