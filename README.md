# 🤖 Automated Text-to-SQL Analytics Copilot

An AI-powered analytics application that allows users to query a relational sales database using natural language.

Instead of writing SQL manually, users can ask questions such as:

> "What are the top 5 products by revenue?"

The application uses an LLM to convert the natural-language question into SQL, validates the generated SQL for safety, executes it against a SQLite database, and displays the results through an interactive Streamlit dashboard.

---

## 🚀 Features

- 💬 Natural-language database queries
- 🤖 AI-powered Text-to-SQL generation
- 🔍 Automatic database schema introspection
- 🔐 SQL safety validation
- 🗄️ SQLite database integration
- ⚡ FastAPI backend
- 📊 Interactive Streamlit frontend
- 📈 Automatic data visualization
- 🧠 Generated SQL displayed to the user
- ❌ Error handling for invalid queries
- 📋 Query result tables
- 🔢 Query statistics
- ⏱️ Query performance measurement

---

## 🏗️ Architecture

```text
                    User
                      │
                      ▼
              ┌───────────────┐
              │   Streamlit   │
              │    Frontend   │
              └───────┬───────┘
                      │
                 HTTP Request
                      │
                      ▼
              ┌───────────────┐
              │    FastAPI    │
              │    Backend    │
              └───────┬───────┘
                      │
             ┌────────┴────────┐
             │                 │
             ▼                 ▼
      Schema Extraction    User Question
             │                 │
             └────────┬────────┘
                      ▼
               ┌─────────────┐
               │   Groq LLM  │
               │ Text → SQL  │
               └──────┬──────┘
                      │
                 Generated SQL
                      │
                      ▼
              ┌───────────────┐
              │ SQL Validator │
              │  Read-Only    │
              └───────┬───────┘
                      │
                Validated SQL
                      │
                      ▼
              ┌───────────────┐
              │ SQLite        │
              │ Database      │
              └───────┬───────┘
                      │
                   Results
                      │
                      ▼
              ┌───────────────┐
              │ Table + Chart │
              │  Visualization│
              └───────────────┘