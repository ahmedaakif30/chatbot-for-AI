from flask import Flask, request, jsonify
import requests, os

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Server is running!"

def ddg_answer(query: str) -> str:
    """Free web lookup via DuckDuckGo Instant Answer."""
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": query, "format": "json", "no_html": 1, "no_redirect": 1},
            timeout=6,
        )
        j = r.json() if r.ok else {}
        # Prefer the short Abstract; fall back to top RelatedTopic snippet
        if j.get("AbstractText"):
            return j["AbstractText"]
        rel = j.get("RelatedTopics") or []
        for item in rel:
            if isinstance(item, dict) and item.get("Text"):
                return item["Text"]
    except Exception:
        pass
    return ""

def wiki_summary(topic: str) -> str:
    """Backup: Wikipedia REST summary (no key, free)."""
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
    text = " ".join(text.split())  # collapse whitespace
    return (text[: limit - 1] + "…") if len(text) > limit else text

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()
    is_fallback = body.get("queryResult", {}).get("intent", {}).get("isFallback", False)

    # If Dialogflow didn’t match training data, fetch from the web.
    if is_fallback and q:
        # 1) Try DuckDuckGo (free)
        ans = ddg_answer(q)
        # 2) If empty, try Wikipedia
        if not ans:
            ans = wiki_summary(q)
        # 3) If still empty, polite message
        if not ans:
            ans = "I couldn’t find a clear answer right now."

        reply = short(ans)  # keep it short & readable
        return jsonify({"fulfillmentText": reply}), 200

    # For non-fallback intents, you can still reply here (optional)
    return jsonify({"fulfillmentText": "Got it!"}), 200

if __name__ == '__main__':
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
