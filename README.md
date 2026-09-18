# Text-to-SQL Analytics Copilot

Ask plain-English questions about an e-commerce database. The service:
translates the question to SQL with an LLM, checks the SQL against a
safety guardrail, runs it, and returns the SQL plus the results.

## What's in the box

| File | Purpose |
|---|---|
| `database.py` | SQLAlchemy models (`customers`, `products`, `orders`, `order_items`) + mock data seeding |
| `copilot_service.py` | Schema introspection, LLM prompt, SQL safety validator |
| `main.py` | FastAPI app (`/query`, `/schema`, `/health`) |
| `requirements.txt` | Dependencies |
| `.env.example` | Config template |
| `test_client.py` | Script to hit the running API with sample questions |

## Database schema

```
customers (customer_id PK, full_name, email, city, country, signup_date)
products  (product_id PK, product_name, category, unit_price, stock_quantity)
orders    (order_id PK, customer_id FK -> customers, order_date, status)
order_items (order_item_id PK, order_id FK -> orders, product_id FK -> products,
             quantity, price_at_purchase)
```

`order_items` is the link table between `orders` and `products` — this
gives the LLM a realistic multi-table join to reason about, the same
pattern you'd see in a real e-commerce database.

## 1. Setup

```bash
cd text_to_sql_copilot
python3 -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
```

Copy the env template and add your LLM API key:

```bash
cp .env.example .env
```

Edit `.env`:
- **OpenAI**: set `LLM_API_KEY`, leave `LLM_BASE_URL` unset.
- **Groq** (free tier, fast): set `LLM_API_KEY` to a Groq key and
  `LLM_BASE_URL=https://api.groq.com/openai/v1`, `LLM_MODEL=llama-3.3-70b-versatile`.
- Any other OpenAI-compatible endpoint works the same way — just set
  `LLM_BASE_URL`.

## 2. Run

```bash
uvicorn main:app --reload
```

On first startup, `database.py` automatically creates `ecommerce.db`
(SQLite) and seeds it with ~40 customers, 30 products, 150 orders, and
their line items. Subsequent restarts skip seeding since the data
already exists — delete `ecommerce.db` to reset.

Server runs at `http://127.0.0.1:8000`.

## 3. Test it

**Option A — Swagger UI**
Open `http://127.0.0.1:8000/docs`, expand `POST /query`, click
"Try it out", and enter:

```json
{ "question": "What are the top 5 best-selling products by revenue?" }
```

**Option B — the test script**

```bash
python test_client.py
```

**Option C — curl**

```bash
curl -X POST http://127.0.0.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "How many customers are there in each country?"}'
```

Example response:

```json
{
  "question": "How many customers are there in each country?",
  "generated_sql": "SELECT country, COUNT(*) AS customer_count FROM customers GROUP BY country ORDER BY customer_count DESC",
  "columns": ["country", "customer_count"],
  "rows": [{"country": "India", "customer_count": 12}, ...],
  "row_count": 8
}
```

Check `GET /schema` any time to see exactly what schema description is
being sent to the LLM.

## 4. Safety guardrails — how destructive SQL is blocked

The LLM's system prompt instructs it to only write `SELECT` statements,
but **the prompt is not the security boundary** — an LLM is not a
trusted party. Every generated query passes through `validate_sql()` in
`copilot_service.py` before it ever touches the database:

1. **Statement type check** — parses the SQL with `sqlparse` and rejects
   anything that isn't classified as `SELECT`.
2. **Single-statement check** — rejects stacked queries like
   `SELECT ...; DROP TABLE ...;`.
3. **Keyword denylist** — a second, independent scan for
   `DROP / DELETE / INSERT / UPDATE / ALTER / TRUNCATE / PRAGMA /
   ATTACH / EXEC` etc. anywhere in the query, including inside
   subqueries.
4. **Comment blocking** — rejects `--` and `/*` since comment injection
   is a classic technique for smuggling a second statement past naive
   parsers.

Anything that fails returns a `400` with the reason and the rejected
SQL — nothing unsafe is ever executed. This was tested directly:
`DROP TABLE`, stacked statements, and comment-based injection are all
blocked; legitimate multi-table `SELECT ... JOIN ... GROUP BY` queries
pass.

## 5. Known limitations (be aware of these before calling it "production")

- **No query result row cap enforcement at the DB layer** — the prompt
  asks the LLM to add `LIMIT`, but a well-behaved LLM isn't a
  guarantee. For real production use, wrap execution with a hard
  `LIMIT` injection or a statement timeout.
- **No auth** — the `/query` endpoint is open. Add an API key or OAuth
  layer before exposing this beyond localhost.
- **No rate limiting** — each request calls the LLM API, which costs
  money and can be abused. Add rate limiting (e.g. `slowapi`) for any
  public deployment.
- **Read-only guardrail is regex/parser-based, not DB-permission-based**
  — the more robust version of this is a database user/role that
  physically only has `SELECT` grants, so even a total bypass of the
  Python validator can't mutate data. Recommended before production.
- **No conversation memory** — each question is independent; there's no
  multi-turn "and now filter that by..." follow-up handling.

## 6. Switching to Postgres

Set `DATABASE_URL` in `.env`:

```
DATABASE_URL=postgresql+psycopg2://user:password@localhost:5432/ecommerce
```

Uncomment `psycopg2-binary` in `requirements.txt` and reinstall. No
code changes needed — `database.py` and `copilot_service.py` both work
through SQLAlchemy's engine abstraction.
