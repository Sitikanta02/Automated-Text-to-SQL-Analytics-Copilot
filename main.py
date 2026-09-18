"""
main.py
-------
FastAPI app exposing the Text-to-SQL Analytics Copilot.

Endpoints:
  GET  /health   -> liveness check
  GET  /schema   -> shows the introspected DB schema (useful for debugging)
  POST /query    -> the main endpoint: English question -> SQL -> results

Run with:
  uvicorn main:app --reload
"""

from dotenv import load_dotenv
load_dotenv()  # must run before importing copilot_service, which reads env vars at import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from database import engine, init_db
from copilot_service import (
    build_schema_description,
    run_query,
    SQLValidationError,
)

app = FastAPI(
    title="Text-to-SQL Analytics Copilot",
    description="Ask plain-English questions about the e-commerce database "
                "and get back the generated SQL plus the results.",
    version="1.0.0",
)


@app.on_event("startup")
def on_startup():
    """Create tables and seed mock data on first run."""
    init_db()


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class QueryRequest(BaseModel):
    question: str = Field(
        ...,
        min_length=3,
        description="A plain-English analytics question.",
        json_schema_extra={"example": "What are the top 5 best-selling products by revenue?"},
    )


class QueryResponse(BaseModel):
    question: str
    generated_sql: str
    columns: list
    rows: list
    row_count: int


class ErrorResponse(BaseModel):
    detail: str
    generated_sql: str | None = None


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/schema")
def schema():
    """Returns the live, introspected database schema. Useful to sanity-check
    what the LLM is actually being told about the database."""
    return {"schema": build_schema_description(engine)}


@app.post("/query", response_model=QueryResponse, responses={400: {"model": ErrorResponse}})
def query(request: QueryRequest):
    """
    Takes a plain-English question, converts it to SQL via the LLM,
    validates the SQL against the safety guardrails, executes it, and
    returns both the SQL and the results.

    Returns 400 if:
      - the LLM isn't configured (missing API key)
      - the generated SQL fails the safety validator
      - the SQL fails to execute against the database (e.g. bad syntax)
    """
    try:
        result = run_query(request.question, engine)
        return QueryResponse(
            question=result.question,
            generated_sql=result.generated_sql,
            columns=result.columns,
            rows=result.rows,
            row_count=result.row_count,
        )
    except SQLValidationError as e:
        # Blocked by our guardrail — surface the SQL so the user/developer
        # can see exactly what was rejected and why.
        raise HTTPException(status_code=400, detail=f"Unsafe SQL blocked: {e}")
    except RuntimeError as e:
        # e.g. missing LLM_API_KEY
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # Catch-all for DB execution errors (bad column name, syntax error
        # in generated SQL, etc.) so the API never 500s with a stack trace.
        raise HTTPException(status_code=400, detail=f"Query execution failed: {e}")
