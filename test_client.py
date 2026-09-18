import requests

url = "http://127.0.0.1:8000/query"

questions = [
    "How many customers are there?",
    "How many customers are there in each country?",
    "Show the names of customers and the orders they placed.",
    "What is the total revenue from all orders?",
    "What are the top 5 products by revenue?",
    "Which customers have spent the most money?"
]

for i, question in enumerate(questions, 1):

    print("\n" + "=" * 70)
    print(f"QUERY {i}")
    print("=" * 70)

    print("Question:", question)

    try:
        response = requests.post(
            url,
            json={"question": question}
        )

        print("Status:", response.status_code)

        data = response.json()

        if response.status_code == 200:

            print("\nGenerated SQL:")
            print(data.get("generated_sql"))

            print("\nColumns:")
            print(data.get("columns"))

            print("\nResults:")
            for row in data.get("rows", []):
                print(row)

        else:
            print("\nError:")
            print(data)

    except Exception as e:
        print("\nConnection error:", e)