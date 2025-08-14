from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pathlib import Path

# importa as rotas
from Routes.uploadDb_routes import router as update_router
from Routes.processes_routes import router as processes_router

app = FastAPI(title="Prova MOB - Consolidador de Processos")

app.include_router(update_router, tags=["upload"])
app.include_router(processes_router, tags=["processes"])


