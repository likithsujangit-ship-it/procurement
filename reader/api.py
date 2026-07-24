import sys
from pathlib import Path
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

# Ensure the database package directory is on sys.path
sys.path.append(str(Path(__file__).parent.resolve()))

from db.db import get_comparison_grid, get_session
from sqlalchemy import text

app = FastAPI(title="RFQ Comparison API")

# Add CORS middleware to allow cross-origin requests
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/rfqs")
def list_rfqs():
    session = get_session()
    try:
        rows = session.execute(text("SELECT id, rfq_number, part_description, status FROM rfqs")).fetchall()
        return [dict(r._mapping) for r in rows]
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        session.close()


@app.get("/rfqs/{rfq_number}/comparison")
def comparison(rfq_number: str):
    try:
        grid = get_comparison_grid(rfq_number)
        return grid
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
