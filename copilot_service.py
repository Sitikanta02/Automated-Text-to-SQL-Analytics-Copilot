"""
copilot_service.py
-------------------
The brain of the copilot. Three responsibilities, kept in separate
functions so each is independently testable:

1. Schema introspection  -> build_schema_description()
2. English -> SQL via LLM -> generate_sql()
3. SQL safety guardrails  -> validate_sql()

Plus one orchestrator, run_query(), that main.py calls.
"""
import time
import os
import re
from dataclasses import dataclass
from typing import Any
from functools import lru_cache

import sqlparse
from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

# The OpenAI SDK also works for Groq, Together, etc. — anything with an
# OpenAI-compatible /chat/completions endpoint. Point base_url at it.
from openai import OpenAI

# ---------------------------------------------------------------------------
# LLM client configuration
# ---------------------------------------------------------------------------

LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_BASE_URL = os.getenv("LLM_BASE_URL")  # e.g. "https://api.groq.com/openai/v1"
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4o-mini")

_client = (
    OpenAI(
        api_key=LLM_API_KEY,
        base_url=LLM_BASE_URL,
        timeout=30.0
    )
    if LLM_API_KEY
    else None
)


# ---------------------------------------------------------------------------
# 1. Schema introspection
# ---------------------------------------------------------------------------

@lru_cache(maxsize=1)
def build_schema_description(engine: Engine) -> str:
    """Reads the live database schema (tables, columns, types, foreign
    keys) and renders it as plain text the LLM can use as grounding.

    This is done dynamically via SQLAlchemy's inspector rather than
    hardcoding table names, so the copilot keeps working if the schema
    changes later.
    """
    inspector = inspect(engine)
    lines = []

    for table_name in inspector.get_table_names():
        columns = inspector.get_columns(table_name)
        pk = inspector.get_pk_constraint(table_name).get("constrained_columns", [])
        fks = inspector.get_foreign_keys(table_name)

        col_descriptions = []
        for col in columns:
            marker = " [PK]" if col["name"] in pk else ""
            col_descriptions.append(f"{col['name']} ({col['type']}){marker}")

        lines.append(f"Table: {table_name}")
        lines.append(f"  Columns: {', '.join(col_descriptions)}")

        for fk in fks:
            local_cols = ", ".join(fk["constrained_columns"])
            ref_table = fk["referred_table"]
            ref_cols = ", ".join(fk["referred_columns"])
            lines.append(f"  Foreign Key: {local_cols} -> {ref_table}({ref_cols})")

        lines.append("")  # blank line between tables

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 2. LLM prompt engineering
# ---------------------------------------------------------------------------

SYSTEM_PROMPT_TEMPLATE = """Generate one valid SQLite SELECT query for the user's question.

Rules:
- Output ONLY SQL. No explanation, markdown, or comments.
- SELECT only. Never modify data or schema.
- Use only tables and columns in the schema.
- Use explicit JOIN ... ON syntax.
- Qualify columns when using multiple tables.
- If the question cannot be answered, output:
  SELECT 'UNANSWERABLE' AS error;
- Add LIMIT 100 to non-aggregate queries that may return many rows.

Schema:
{schema}
"""


def generate_sql(question: str, schema_description: str) -> str:
    """Calls the LLM to translate an English question into SQL.

    Raises RuntimeError if no LLM client is configured, so the failure
    is explicit rather than silently returning garbage.
    """
    if _client is None:
        raise RuntimeError(
            "No LLM API key configured. Set LLM_API_KEY (and optionally "
            "LLM_BASE_URL / LLM_MODEL) in your environment or .env file."
        )

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(schema=schema_description)

    response = _client.chat.completions.create(
    model=LLM_MODEL,
    messages=[
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ],
    temperature=0,
    max_tokens=500,
    extra_body={
        "include_reasoning": False
    },
)

    raw_sql = response.choices[0].message.content.strip()
    return _strip_markdown_fences(raw_sql)


def _strip_markdown_fences(sql: str) -> str:
    """LLMs love wrapping SQL in ```sql ... ``` even when told not to.
    Strip it defensively so the validator sees clean SQL."""
    sql = re.sub(r"^```(?:sql)?\s*", "", sql.strip())
    sql = re.sub(r"\s*```$", "", sql.strip())
    return sql.strip()


# ---------------------------------------------------------------------------
# 3. SQL safety guardrails
# ---------------------------------------------------------------------------

# Any statement type other than SELECT is blocked outright.
FORBIDDEN_KEYWORDS = {
    "INSERT", "UPDATE", "DELETE", "DROP", "ALTER", "CREATE", "TRUNCATE",
    "REPLACE", "MERGE", "GRANT", "REVOKE", "ATTACH", "DETACH", "PRAGMA",
    "VACUUM", "REINDEX", "EXEC", "EXECUTE", "CALL",
}


class SQLValidationError(Exception):
    """Raised when generated SQL fails a safety check."""


def validate_sql(sql: str) -> str:
    """Defense-in-depth guardrail. Even though the LLM is instructed to
    only write SELECTs, we never trust an LLM's output directly — this
    function is the actual security boundary.

    Checks, in order:
    1. Exactly one statement (blocks stacked queries like "SELECT ...; DROP ...").
    2. The statement must parse as a SELECT.
    3. No forbidden keyword appears anywhere in the query (belt-and-braces
       in case a keyword is smuggled inside a subquery or CTE).
    4. Blocks comment-based obfuscation ("--", "/*") which is a classic
       SQL injection technique to hide a second statement.

    Returns the cleaned SQL on success. Raises SQLValidationError on
    failure with a human-readable reason.
    """
    if not sql or not sql.strip():
        raise SQLValidationError("Generated SQL is empty.")

    # Block comment-based smuggling before anything else.
    if "--" in sql or "/*" in sql:
        raise SQLValidationError("SQL comments are not allowed (possible injection attempt).")

    statements = [s for s in sqlparse.parse(sql) if s.token_first(skip_cm=True) is not None]

    if len(statements) == 0:
        raise SQLValidationError("No valid SQL statement found.")
    if len(statements) > 1:
        raise SQLValidationError("Multiple SQL statements are not allowed.")

    stmt = statements[0]
    stmt_type = stmt.get_type()  # e.g. "SELECT", "INSERT", "UNKNOWN"

    if stmt_type != "SELECT":
        raise SQLValidationError(
            f"Only SELECT queries are allowed. Detected statement type: {stmt_type}"
        )

    # Keyword scan across the raw text as a second, independent check —
    # catches cases sqlparse might classify ambiguously (e.g. "SELECT ... ;
    # DELETE ..." parsed oddly), and catches keywords hidden in subqueries.
    upper_sql = sql.upper()
    for keyword in FORBIDDEN_KEYWORDS:
        if re.search(rf"\b{keyword}\b", upper_sql):
            raise SQLValidationError(f"Forbidden keyword detected: {keyword}")

    cleaned = sql.strip().rstrip(";")
    return cleaned


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

@dataclass
class QueryResult:
    question: str
    generated_sql: str
    columns: list
    rows: list
    row_count: int

def run_query(question: str, engine: Engine) -> QueryResult:
    """Full pipeline with performance timing."""

    start = time.time()

    print("\n--- Starting Query ---")
    print(f"Question: {question}")

    # Step 1: Get database schema
    schema_start = time.time()
    schema_description = build_schema_description(engine)
    schema_time = time.time() - schema_start

    # Step 2: Generate SQL using the LLM
    llm_start = time.time()
    raw_sql = generate_sql(question, schema_description)
    llm_time = time.time() - llm_start

    # Step 3: Validate SQL
    validation_start = time.time()
    safe_sql = validate_sql(raw_sql)
    validation_time = time.time() - validation_start

    # Step 4: Execute SQL
    db_start = time.time()

    with engine.connect() as conn:
        result = conn.execute(text(safe_sql))
        columns = list(result.keys())
        rows = [dict(zip(columns, row)) for row in result.fetchall()]

    db_time = time.time() - db_start
    total_time = time.time() - start

    print("\n--- Query Performance ---")
    print(f"Schema:     {schema_time:.3f}s")
    print(f"LLM:        {llm_time:.3f}s")
    print(f"Validation: {validation_time:.3f}s")
    print(f"Database:   {db_time:.3f}s")
    print(f"Total:      {total_time:.3f}s")
    print("-------------------------\n")

    return QueryResult(
        question=question,
        generated_sql=safe_sql,
        columns=columns,
        rows=rows,
        row_count=len(rows),
    )
extra_body={
    "include_reasoning": False
},