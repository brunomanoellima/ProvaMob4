# Routes/uploadDb_routes.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import JSONResponse, HTMLResponse
from pathlib import Path
from typing import Optional
from Routes.processes_routes import collect_processed, DB_PATH  # reaproveita o coletor

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

@router.get(
    "/",
    response_class=HTMLResponse,
    description="""
    Retorna uma página HTML simples com um formulário para envio de arquivos de banco de dados SQLite.
    
    O formulário permite:
    - Selecionar o arquivo (`.sqlite` ou `.db`)
    - Definir filtros opcionais (`start_ms`, `end_ms`, `package_name`, `uid`, `limit`)
    - Enviar e processar automaticamente o banco
    
    Também é possível usar diretamente os endpoints na interface `/docs`.
    """
)
def home():
    return """
    <!doctype html><html><head><meta charset="utf-8"><title>Upload DB</title>
    <style>body{font:14px system-ui;margin:40px}.card{max-width:620px;margin:auto;padding:24px;border:1px solid #ddd;border-radius:12px}</style>
    </head><body><div class="card">
      <h2>Enviar base SQLite</h2>
      <form action="/upload-db" method="post" enctype="multipart/form-data">
        <p>Arquivo (.sqlite / .db): <input type="file" name="file" required></p>
        <p>start_ms (opcional): <input type="text" name="start_ms"></p>
        <p>end_ms (opcional): <input type="text" name="end_ms"></p>
        <p>package_name (opcional): <input type="text" name="package_name"></p>
        <p>uid (opcional): <input type="text" name="uid"></p>
        <p>limit (padrão 1000): <input type="number" name="limit" value="1000"></p>
        <button type="submit">Enviar e Processar</button>
      </form>
      <p>Ou use <a href="/docs">/docs</a>.</p>
    </div></body></html>
    """

@router.post(
    "/upload-db",
    description="""
    Recebe um arquivo SQLite, salva como `data/live.sqlite` e retorna os dados processados.

    **Fluxo de funcionamento:**
    1. O arquivo enviado é validado (`.sqlite` ou `.db`).
    2. É salvo na pasta `data/` com o nome `live.sqlite`.
    3. É processado usando o mesmo parser de `/processes`, retornando os resultados filtrados.

    **Parâmetros opcionais de filtro:**
    - `start_ms`: timestamp inicial (ms)
    - `end_ms`: timestamp final (ms)
    - `package_name`: filtro pelo nome do pacote
    - `uid`: filtro pelo UID
    - `limit`: quantidade máxima de registros (padrão 1000)
    
    **Resposta:**
    ```json
    {
        "saved_as": "caminho/do/arquivo.sqlite",
        "count": 123,
        "results": [ ... ]
    }
    ```
    """
)
async def upload_db(
    file: UploadFile = File(..., description="Arquivo SQLite (.sqlite ou .db)"),
    start_ms: Optional[int] = Query(None, description="timestamp inicial em ms (opcional)"),
    end_ms: Optional[int]   = Query(None, description="timestamp final em ms (opcional)"),
    package_name: Optional[str] = Query(None, description="filtro por package (opcional)"),
    uid: Optional[str] = Query(None, description="filtro por uid (opcional)"),
    limit: int = Query(1000, ge=1, le=100_000, description="quantidade máxima de registros retornados")
):
    if not file.filename.lower().endswith((".sqlite", ".db", ".sql")):
        raise HTTPException(status_code=400, detail="Envie um arquivo SQLite (.sqlite ou .db)")

    data = await file.read()
    with open(DB_PATH, "wb") as f:
        f.write(data)
    await file.close()

    items = collect_processed(
        start_ms=start_ms, end_ms=end_ms, limit=limit,
        package_name=package_name, uid=uid
    )

    return JSONResponse(content={
        "saved_as": str(DB_PATH),
        "count": len(items),
        "results": items
    })
