from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import os, re, requests, random
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError

app = Flask(__name__)
CORS(app)  # allow calls from your bot.html during development / production

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

HELP_ANSWER = (
    "If you see a sea otter that looks sick, injured, or in trouble:\n"
    "• Keep a safe distance and do not touch or move it.\n"
    "• Keep dogs and people away from the animal.\n"
    "• Call your local wildlife rescue / marine mammal center or stranding hotline.\n"
    "• Note the exact location and what the otter was doing so you can tell rescuers.\n"
    "Never try to feed or keep a wild sea otter as a pet."
)

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

    # Help / rescue questions
    if "sea otter" in l and any(
        w in l for w in ["help", "save", "injured", "hurt", "rescue", "what can i do"]
    ):
        return HELP_ANSWER

    # Predators
    if any(t in l for t in [
        "main predators of sea otters", "predators of sea otters", "sea otter predators",
        "who eats sea otters", "what eats sea otters", "who preys on sea otters",
        "enemy of sea otters", "predators of the sea otter"
    ]):
        return PREDATORS_ANSWER

    # Drivers / causes of decline
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
    """
    q2 = short(clean(rewrite_for_topic(q)), 120)
    with ThreadPoolExecutor(max_workers=2) as ex:
        futs = [ex.submit(ddg_answer, q2), ex.submit(wiki_answer, q2)]
        try:
            for fut in as_completed(futs, timeout=3.4):
                ans = fut.result() or ""
                if ans.strip():
                    src = "DuckDuckGo" if fut == futs[0] else "Wikipedia"
                    return ans, src
        except TimeoutError:
            pass
    return "", ""

# ------------- extra filters so it doesn’t answer everything ------------------

def is_sea_otter_question(q: str) -> bool:
    """Only answer questions that mention sea otters / otters."""
    l = (q or "").lower()
    return any(w in l for w in ["sea otter", "sea otters", "otter", "otters"])

SEA_OTTER_ONLY_MESSAGES = [
    "I’m focused on sea otters right now. Try asking me something about sea otters or their habitat. 🦦",
    "I can’t answer that one, but I can help with sea otter facts, threats, or how to help them. 🦦",
    "This bot is only trained for sea otter questions. Please ask me something about sea otters. 🌊🦦",
]

def seems_relevant(ans: str, q: str) -> bool:
    """
    Simple relevance check:
    - If question mentions otters but answer does not, treat as not relevant.
    """
    l_ans = (ans or "").lower()
    l_q = (q or "").lower()
    if "otter" in l_q and "otter" not in l_ans:
        return False
    return True

# ------------- core Q&A logic, shared by webhook + UI ------------------------

def answer_question(q: str) -> str:
    q = (q or "").strip()
    print("QUESTION:", q)

    # 0) Non–sea otter question → gently refuse
    if not is_sea_otter_question(q):
        reply = random.choice(SEA_OTTER_ONLY_MESSAGES)
        print("REPLY (non-otter):", reply)
        return reply

    # 1) rule-based instant answers
    rb = rule_answer(q)
    if rb:
        print("REPLY (rule):", rb)
        return rb

    # 2) web lookup (DuckDuckGo + Wikipedia)
    ans, src = web_lookup(q)

    # 3) If nothing or seems irrelevant → proper fallback
    if not ans or not seems_relevant(ans, q):
        reply = (
            "I couldn’t find a good answer right now. "
            "Try rephrasing your question, or ask me another sea otter question. 🦦"
        )
        print("REPLY (fallback):", reply)
        return reply

    # 4) Normal good answer
    reply = short(ans)
    if src:
        reply = f"{reply} (Source: {src})"
    print("REPLY:", reply)
    return reply

# ------------- routes ---------------------------------------------------------

# Serve your HTML UI
@app.route("/ui")
def ui():
    # "static/bot.html" in your repo
    return send_from_directory("static", "bot.html")

# Optional: simple text at root
@app.route("/")
def home():
    return "✅ Kelp Guardian backend is running. Visit /ui for the chat UI."

# Dialogflow webhook (if you still want to use it)
@app.route("/webhook", methods=["GET", "POST"])
def webhook():
    if request.method == "GET":
        return jsonify({"status": "Webhook ready"}), 200

    body = request.get_json(silent=True) or {}
    q = (body.get("queryResult", {}).get("queryText") or "").strip()
    reply = answer_question(q)
    return jsonify({"fulfillmentText": reply}), 200

# Endpoint used by your custom UI
@app.route("/chat", methods=["POST"])
def chat():
    data = request.get_json(silent=True) or {}
    q = (data.get("text") or "").strip()
    if not q:
        return jsonify({"error": "Missing text"}), 400

    reply = answer_question(q)
    return jsonify({"reply": reply}), 200

@app.route("/ping")
def ping():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
