from flask import Flask, request, jsonify
import requests, os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Server is running!"

def ddg_answer(query: str) -> str:
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1},
            timeout=6,
        )
        j = r.json() if r.ok else {}
        if j.get("AbstractText"):
            return j["AbstractText"]
        for item in j.get("RelatedTopics", []):
            if isinstance(item, dict) and item.get("Text"):
                return item["Text"]
    except Exception:
        pass
    return ""

def wiki_summary(topic: str) -> str:
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}",
            timeout=6,
        )
        j = r.json() if r.ok else {}
        return j.get("extract", "")
    except Exception:
        return ""

def short(text: str, limit: int = 240) -> str:
    if not text:
        return ""
    text = " ".join(text.split())
    return (text[: limit - 1] + "…") if len(text) > limit else text

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()

    if q:
        ans = ddg_answer(q) or wiki_summary(q) or "I couldn’t find a clear answer right now."
        return jsonify({"fulfillmentText": short(ans)}), 200

    return jsonify({"fulfillmentText": "Got it!"}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
