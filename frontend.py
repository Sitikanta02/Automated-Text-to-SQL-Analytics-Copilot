import streamlit as st
import requests
import pandas as pd

# --------------------------------------------------
# Configuration
# --------------------------------------------------

API_URL = "http://127.0.0.1:8000"


# --------------------------------------------------
# Page Configuration
# --------------------------------------------------

st.set_page_config(
    page_title="Analytics Copilot",
    page_icon="🤖",
    layout="wide"
)


# --------------------------------------------------
# Header
# --------------------------------------------------

st.title("🤖 Automated Text-to-SQL Analytics Copilot")

st.write(
    "Ask questions about your database in natural language "
    "and let AI generate and execute SQL for you."
)

st.divider()


# --------------------------------------------------
# User Question
# --------------------------------------------------

question = st.text_area(
    "💬 Ask your database a question",
    placeholder="Example: What are the top 5 products by revenue?",
    height=100
)


# --------------------------------------------------
# Ask Button
# --------------------------------------------------

if st.button("🚀 Ask Copilot", type="primary"):

    if not question.strip():

        st.warning("Please enter a question.")

    else:

        with st.spinner(
            "🤖 Generating SQL and analyzing your data..."
        ):

            try:

                # ------------------------------------------
                # Send request to FastAPI
                # ------------------------------------------

                response = requests.post(
                    f"{API_URL}/query",
                    json={
                        "question": question
                    },
                    timeout=120
                )

                # ------------------------------------------
                # Successful Response
                # ------------------------------------------

                if response.status_code == 200:

                    data = response.json()

                    # --------------------------------------
                    # Generated SQL
                    # --------------------------------------

                    st.subheader("🧠 Generated SQL")

                    st.code(
                        data.get("generated_sql", ""),
                        language="sql"
                    )

                    # --------------------------------------
                    # Query Results
                    # --------------------------------------

                    st.subheader("📊 Query Results")

                    rows = data.get("rows", [])

                    if rows:

                        df = pd.DataFrame(rows)

                        st.dataframe(
                            df,
                            use_container_width=True
                        )

                        # ----------------------------------
                        # Automatic Visualization
                        # ----------------------------------

                        if len(df.columns) >= 2:

                            numeric_columns = list(
                                df.select_dtypes(
                                    include="number"
                                ).columns
                            )

                            # Prefer a meaningful text/category column
                            preferred_label_columns = [
                                "product_name",
                                "customer_name",
                                "country",
                                "category",
                                "department",
                                "order_date"
                            ]

                            label_column = None

                            for column in preferred_label_columns:

                                if column in df.columns:
                                    label_column = column
                                    break

                            # If no preferred column exists,
                            # find the first non-numeric column
                            if label_column is None:

                                non_numeric_columns = [
                                    column
                                    for column in df.columns
                                    if column not in numeric_columns
                                ]

                                if non_numeric_columns:
                                    label_column = non_numeric_columns[0]

                            # ----------------------------------
                            # Display Chart
                            # ----------------------------------

                            if label_column and numeric_columns:

                                st.subheader("📈 Visualization")

                                chart_column = numeric_columns[0]

                                chart_df = df[
                                    [label_column, chart_column]
                                ].copy()

                                chart_df = chart_df.set_index(
                                    label_column
                                )

                                st.bar_chart(
                                    chart_df[chart_column]
                                )

                    else:

                        st.info(
                            "The query returned no results."
                        )

                    # --------------------------------------
                    # Query Information
                    # --------------------------------------

                    st.subheader("ℹ️ Query Information")

                    col1, col2 = st.columns(2)

                    with col1:

                        st.metric(
                            "Rows Returned",
                            data.get("row_count", 0)
                        )

                    with col2:

                        st.metric(
                            "Columns",
                            len(data.get("columns", []))
                        )

                # ------------------------------------------
                # API Error
                # ------------------------------------------

                else:

                    try:
                        error = response.json()

                        st.error(
                            error.get(
                                "detail",
                                "Something went wrong."
                            )
                        )

                    except Exception:

                        st.error(
                            f"API Error: {response.status_code}"
                        )

            # ----------------------------------------------
            # FastAPI Connection Error
            # ----------------------------------------------

            except requests.exceptions.ConnectionError:

                st.error(
                    "❌ Cannot connect to the FastAPI server. "
                    "Make sure uvicorn is running."
                )

            # ----------------------------------------------
            # Timeout Error
            # ----------------------------------------------

            except requests.exceptions.Timeout:

                st.error(
                    "⏳ Request timed out. "
                    "The AI service took too long to respond."
                )

            # ----------------------------------------------
            # Other Errors
            # ----------------------------------------------

            except Exception as e:

                st.error(
                    f"❌ Error: {str(e)}"
                )