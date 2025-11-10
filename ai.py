from flask import Flask, request, jsonify
import requests, os
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Server is running!"

def ddg_answer(q):
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_html": 1, "no_redirect": 1},
            timeout=1.8,  # <= keep fast
        )
        j = r.json() if r.ok else {}
        if j.get("AbstractText"):
            return j["AbstractText"]
        for it in j.get("RelatedTopics", []):
            if isinstance(it, dict) and it.get("Text"):
                return it["Text"]
    except Exception:
        pass
    return ""

def wiki_summary(topic):
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{topic}",
            timeout=1.8,  # <= keep fast
        )
        j = r.json() if r.ok else {}
        return j.get("extract", "")
    except Exception:
        return ""

def short(text, limit=240):
    text = " ".join((text or "").split())
    return (text[:limit-1] + "…") if len(text) > limit else text

def web_lookup(q):
    # run both lookups in parallel, stop at the first non-empty
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(ddg_answer, q), ex.submit(wiki_summary, q)]
        try:
            for fut in as_completed(futs, timeout=3.6):  # total under 5s
                ans = fut.result() or ""
                if ans.strip():
                    return ans
        except TimeoutError:
            pass
    return ""

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()
    print("DLGFLW QUESTION:", q)

    ans = web_lookup(q)
    if not ans:
        ans = "I couldn’t fetch that quickly. Please try rephrasing or ask another question."

    reply = short(ans)
    print("WEBHOOK REPLY:", reply)
    return jsonify({"fulfillmentText": reply}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

