import pandas as pd
import re

df = pd.read_csv('question_details.csv')
body = df.iloc[0]['Body']  # Two Sum

# Clean HTML
html_entities = {"&nbsp;": " ", "&quot;": '"', "&gt;": ">", "&lt;": "<", "&amp;": "&"}
for e, r in html_entities.items():
    body = body.replace(e, r)
body = re.sub('<.*?>', '', body)

# Extract test cases
inputs = re.findall(r'Input:\s*(.+?)\n', body, re.IGNORECASE)
outputs = re.findall(r'Output:\s*(.+?)\n', body, re.IGNORECASE)

print("=== Cleaned body (first 800 chars) ===")
print(repr(body[:800]))
print()
print("=== Extracted inputs ===")
for i, inp in enumerate(inputs):
    print(f"  [{i}]: {repr(inp)}")
print()
print("=== Extracted outputs ===")
for i, out in enumerate(outputs):
    print(f"  [{i}]: {repr(out)}")
