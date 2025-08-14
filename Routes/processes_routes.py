from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse
from pathlib import Path
from typing import List, Dict, Optional
import sqlite3

router = APIRouter()

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "live.sqlite"

TABLES = ["processes1", "processes2", "processes3"]

METRICS_INDEX = {
    "timestramp": 0,
    "usage_time": 1,
    "delta_cpu_time": 2,
    "cpu_usage": 3,
    "rx_data": 4,
    "tx_data": 5,
}

def connect():
    if not DB_PATH.exists():
        raise HTTPException(status_code=400, detail="Nenhum banco enviado. Use / (upload).")
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def table_exists(conn: sqlite3.Connection, name: str) -> bool:
    cur = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1;", (name,))
    return cur.fetchone() is not None

def parse_metrics(metrics: str, pkg: str, uid: str) -> List[Dict]:
    if not metrics:
        return []
    out: List[Dict] = []
    for chunk in (c for c in metrics.split(";") if c.strip() != ""):
        parts = chunk.split(":")

        def geti(i: int) -> Optional[int]:
            try:
                v = parts[i]
                return None if v == "" else int(v)
            except (IndexError, ValueError):
                return None

        def getf(i: int) -> Optional[float]:
            try:
                v = parts[i]
                return None if v == "" else float(v)
            except (IndexError, ValueError):
                return None

        ts   = geti(METRICS_INDEX["timestramp"])
        usage= geti(METRICS_INDEX["usage_time"])
        dcpu = geti(METRICS_INDEX["delta_cpu_time"])
        cpu  = getf(METRICS_INDEX["cpu_usage"])
        rx   = geti(METRICS_INDEX["rx_data"]) if "rx_data" in METRICS_INDEX else None
        tx   = geti(METRICS_INDEX["tx_data"])

        if cpu is None and usage and usage != 0 and dcpu is not None:
            cpu = float(dcpu) / float(usage)

        if ts is None:
            continue

        out.append({
            "timestramp": ts,
            "uid": str(uid),
            "package_name": pkg,
            "usage_time": usage or 0,
            "delta_cpu_time": dcpu or 0,
            "cpu_usage": cpu or 0.0,
            "rx_data": rx or 0,
            "tx_data": tx or 0,
        })
    return out

def collect_processed(
    start_ms: Optional[int] = None,
    end_ms: Optional[int] = None,
    limit: int = 1000,
    package_name: Optional[str] = None,
    uid: Optional[str] = None,
) -> List[Dict]:
    results: List[Dict] = []
    with connect() as conn:
        for t in TABLES:
            if not table_exists(conn, t):
                continue
            cur = conn.execute(f"SELECT PackageName, Uid, Pids, Metrics FROM {t}")
            for row in cur:
                pkg = row["PackageName"]
                uid_row = str(row["Uid"])
                if package_name and pkg != package_name:
                    continue
                if uid and uid_row != uid:
                    continue
                for rec in parse_metrics(row["Metrics"], pkg, uid_row):
                    ts = rec["timestramp"]
                    if (start_ms is None or ts >= start_ms) and (end_ms is None or ts <= end_ms):
                        results.append(rec)
                        if len(results) >= limit:
                            results.sort(key=lambda x: x["timestramp"], reverse=True)
                            return results
    results.sort(key=lambda x: x["timestramp"], reverse=True)
    return results

@router.get(
    "/processes",
    description="""
    Lê os dados do banco `data/live.sqlite`, processa o campo `Metrics` e retorna um JSON estruturado contendo:

    - **timestramp**
    - **uid**
    - **package_name**
    - **usage_time**
    - **delta_cpu_time**
    - **cpu_usage**
    - **rx_data**
    - **tx_data**

    Permite filtros por intervalo de tempo (`start_ms`, `end_ms`), pacote (`package_name`), UID e limite de resultados (`limit`).
    """
)
def processes(
    start_ms: int = Query(..., description="timestramp inicial (ms)"),
    end_ms:   int = Query(..., description="timestramp final (ms)"),
    package_name: Optional[str] = Query(None),
    uid: Optional[str] = Query(None),
    limit: int = Query(1000, ge=1, le=100_000)
):
    if start_ms > end_ms:
        raise HTTPException(status_code=400, detail="start_ms deve ser <= end_ms")
    items = collect_processed(start_ms=start_ms, end_ms=end_ms, limit=limit,
                              package_name=package_name, uid=uid)
    return JSONResponse(content=items)

@router.get(
    "/processes-latest",
    description="""
    Retorna apenas os registros mais recentes de cada aplicação/processo do banco `data/live.sqlite`,
    já processados no formato JSON.  
    Útil para consultar o estado atual sem precisar especificar intervalos de tempo.
    """
)
def processes_latest(
    limit: int = Query(1000, ge=1, le=100_000),
    package_name: Optional[str] = Query(None),
    uid: Optional[str] = Query(None),
):
    items = collect_processed(start_ms=None, end_ms=None, limit=limit,
                              package_name=package_name, uid=uid)
    if not items:
        raise HTTPException(status_code=404, detail="Nenhum registro encontrado em data/live.sqlite")
    return JSONResponse(content=items)

@router.get(
    "/debug/tables",
    description="""
    Lista todas as tabelas existentes no banco SQLite carregado,
    junto com o SQL de criação de cada uma.  
    Útil para verificar a estrutura do banco enviado.
    """
)
def debug_tables():
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()
        return [{"name": r["name"], "sql": r["sql"]} for r in rows]

@router.get(
    "/debug/sample",
    description="""
    Retorna uma pequena amostra (padrão: 3 linhas) das tabelas `processes1`, `processes2`, `processes3`.  
    Útil para inspecionar rapidamente o conteúdo sem processar todos os dados.
    """
)
def debug_sample(limit: int = 3):
    with sqlite3.connect(str(DB_PATH)) as conn:
        conn.row_factory = sqlite3.Row
        out = {}
        for t in ["processes1", "processes2", "processes3"]:
            try:
                rows = conn.execute(f"SELECT PackageName, Uid, Pids, Metrics FROM {t} LIMIT ?", (limit,)).fetchall()
                out[t] = [dict(r) for r in rows]
            except sqlite3.OperationalError:
                out[t] = "tabela não encontrada"
        return out
