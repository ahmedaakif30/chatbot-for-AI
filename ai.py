from flask import Flask, request, jsonify
import requests, os, re
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Server is running!"

# ---------- helpers ----------

def clean(q: str) -> str:
    q = (q or "").strip()
    q = re.sub(r"[?!.]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q

def rewrite_for_topic(q: str) -> str:
    """Map common questions to tighter topics for better hits."""
    l = q.lower()
    if "sea otter" in l or "otters" in l:
        if "predator" in l or "enemy" in l or "hunt" in l or "eats sea otter" in l:
            return "Sea otter predators"
        if "diet" in l or "eat" in l or "food" in l:
            return "Sea otter diet"
        if "habitat" in l or "live" in l or "where do" in l:
            return "Sea otter habitat"
        if "lifespan" in l or "how long" in l or "live for" in l:
            return "Sea otter lifespan"
        if "population" in l or "how many" in l or "count" in l or "left" in l:
            return "Sea otter population"
    return q

def ddg_answer(q: str) -> tuple[str, str]:
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_html": 1, "no_redirect": 1},
            timeout=1.4,
        )
        if not r.ok:
            return "", ""
        j = r.json()
        if j.get("AbstractText"):
            return j["AbstractText"], "DuckDuckGo"
        for it in j.get("RelatedTopics", []):
            if isinstance(it, dict) and it.get("Text"):
                return it["Text"], "DuckDuckGo"
    except Exception:
        pass
    return "", ""

def wiki_title_search(q: str) -> str:
    """Use Wikipedia page search (better than title-only) and grab the top hit."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": q, "limit": 1},
            timeout=1.4,
        )
        if not r.ok:
            return ""
        j = r.json()
        pages = j.get("pages") or []
        if pages:
            return pages[0].get("title", "")
    except Exception:
        pass
    return ""

def wiki_summary_from_title(title: str) -> str:
    try:
        r = requests.get(
            f"https://en.wikipedia.org/api/rest_v1/page/summary/{title}",
            timeout=1.4,
        )
        if not r.ok:
            return ""
        j = r.json()
        return j.get("extract", "")
    except Exception:
        return ""

def wiki_answer(q: str) -> tuple[str, str]:
    title = wiki_title_search(q)
    if not title:
        return "", ""
    extract = wiki_summary_from_title(title)
    return (extract, f"Wikipedia: {title}") if extract else ("", "")

def short(text: str, limit: int = 240) -> str:
    text = " ".join((text or "").split())
    return (text[: limit - 1] + "…") if len(text) > limit else text

def web_lookup(q: str) -> tuple[str, str]:
    q = short(clean(rewrite_for_topic(q)), 120)  # keep focused
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(ddg_answer, q), ex.submit(wiki_answer, q)]
        try:
            for fut in as_completed(futs, timeout=3.4):  # total < 5s
                ans, src = fut.result()
                if ans and ans.strip():
                    return ans, src
        except TimeoutError:
            pass
    return "", ""

# ---------- webhook ----------

@app.route('/webhook', methods=['POST','GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()
    print("DLGFLW QUESTION:", q)

    ans, src = web_lookup(q)
    if not ans:
        ans = "I couldn’t fetch that quickly. Please try again."
        src = ""

    reply = short(ans)
    if src:
        reply = f"{reply} (Source: {src})"

    print("WEBHOOK REPLY:", reply)
    return jsonify({"fulfillmentText": reply}), 200

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
