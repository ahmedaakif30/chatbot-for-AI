from flask import Flask, request, jsonify
import os, re, requests
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

app = Flask(__name__)

# ------------- small utilities ------------------------------------------------

def clean(q: str) -> str:
    """Trim whitespace and trailing punctuation."""
    q = (q or "").strip()
    q = re.sub(r"[?!.]+$", "", q)
    q = re.sub(r"\s+", " ", q)
    return q

def short(text: str, limit: int = 240) -> str:
    """Return a compact, single-line, short message."""
    text = " ".join((text or "").split())
    return (text[: limit - 1] + "…") if len(text) > limit else text

def rewrite_for_topic(q: str) -> str:
    """
    Rewrite some common sea-otter questions to tighter topics for better hits.
    (Keeps total latency < 5s on Dialogflow.)
    """
    l = (q or "").lower()
    if "sea otter" in l or "sea otters" in l or "otters" in l:
        if any(w in l for w in ["predator", "predators", "enemy", "enemies"]):
            return "Sea otter predators"
        if any(w in l for w in ["decline", "drivers", "endangered", "threats",
                                "why decreasing", "why declining", "reasons for decline",
                                "causes of decline"]):
            return "current threats to sea otters"
        if any(w in l for w in ["diet", "eat", "food"]):
            return "Sea otter diet"
        if any(w in l for w in ["habitat", "live", "where do"]):
            return "Sea otter habitat"
        if any(w in l for w in ["lifespan", "how long"]):
            return "Sea otter lifespan"
    return q

# ------------- tiny instant FAQs (zero-latency must-answers) ------------------

PREDATORS_ANSWER = (
    "Main predators of sea otters are great white sharks and orcas (killer whales). "
    "Pups may be taken by bald eagles; on land, occasionally coyotes or bears. "
    "Historically, humans were the largest threat during the fur trade."
)

DRIVERS_ANSWER = (
    "Current drivers of sea otter decline include oil spills; entanglement in fishing gear; "
    "diseases from land runoff (e.g., Toxoplasma); prey depletion/urchin barrens with kelp loss; "
    "predation in some regions (sharks/orcas); pollution and disturbance; and climate-driven habitat change."
)

def rule_answer(q: str) -> str:
    l = (q or "").lower()
    # predators
    if any(t in l for t in [
        "main predators of sea otters", "predators of sea otters", "sea otter predators",
        "who eats sea otters", "what eats sea otters", "who preys on sea otters",
        "enemy of sea otters", "predators of the sea otter"
    ]):
        return PREDATORS_ANSWER

    # drivers/causes of decline
    if any(t in l for t in [
        "drivers of decline", "main drivers of decline", "current threats",
        "why are numbers declining", "causes of decline", "endangerment causes",
        "why are sea otters declining", "reasons for decline",
        "drivers of sea otter decline", "main drivers of sea otter decline today"
    ]):
        return DRIVERS_ANSWER

    return ""

# ------------- fast web lookup (parallel; short timeouts) ---------------------

UA = {"User-Agent": "Mozilla/5.0 (DLGFLW-Webhook/1.0)"}

def ddg_answer(q: str):
    """DuckDuckGo Instant Answer."""
    try:
        r = requests.get(
            "https://api.duckduckgo.com/",
            params={"q": q, "format": "json", "no_html": 1, "no_redirect": 1},
            headers=UA, timeout=1.4,
        )
        if not r.ok:
            return ""
        j = r.json()
        if j.get("AbstractText"):
            return j["AbstractText"]
        for it in j.get("RelatedTopics", []):
            if isinstance(it, dict) and it.get("Text"):
                return it["Text"]
    except Exception:
        pass
    return ""

def wiki_title_search(q: str) -> str:
    """Use Wikipedia page search to get the top page title."""
    try:
        r = requests.get(
            "https://en.wikipedia.org/w/rest.php/v1/search/page",
            params={"q": q, "limit": 1},
            headers=UA, timeout=1.4,
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
            headers=UA, timeout=1.4,
        )
        if not r.ok:
            return ""
        j = r.json()
        return j.get("extract", "")
    except Exception:
        return ""

def wiki_answer(q: str):
    title = wiki_title_search(q)
    if not title:
        return ""
    return wiki_summary_from_title(title) or ""

def web_lookup(q: str) -> tuple[str, str]:
    """
    Run DDG + Wikipedia in parallel and return the first non-empty answer.
    Keeps total under Dialogflow’s ~5s webhook limit even on free hosting.
    """
    q2 = short(clean(rewrite_for_topic(q)), 120)
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(ddg_answer, q2), ex.submit(wiki_answer, q2)]
        try:
            for fut in as_completed(futs, timeout=3.4):  # total budget < 5s
                ans = fut.result() or ""
                if ans.strip():
                    # pick a human-readable source label
                    src = "DuckDuckGo" if fut == futs[0] else "Wikipedia"
                    return ans, src
        except TimeoutError:
            pass
    return "", ""

# ------------- routes ---------------------------------------------------------

@app.route("/")
def home():
    return "✅ Server is running!"

@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()
    print("DLGFLW QUESTION:", q)

    # 1) instant rule answers (avoid timeouts & guarantee coverage)
    rb = rule_answer(q)
    if rb:
        print("WEBHOOK REPLY (rule):", rb)
        return jsonify({"fulfillmentText": rb}), 200

    # 2) otherwise, fast web lookup
    ans, src = web_lookup(q)
    if not ans:
        reply = "I couldn’t fetch that quickly. Please try again."
        print("WEBHOOK REPLY (empty):", reply)
        return jsonify({"fulfillmentText": reply}), 200

    reply = short(ans)
    if src:
        reply = f"{reply} (Source: {src})"
    print("WEBHOOK REPLY:", reply)
    return jsonify({"fulfillmentText": reply}), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
