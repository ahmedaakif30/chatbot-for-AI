from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return "✅ Server is running!"

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    if request.method == 'GET':
        return jsonify({"status": "Webhook ready"}), 200

    data = request.get_json(silent=True) or {}
    print("Received data:", data)  # check logs in Render
    # You can process or respond here
    return jsonify({"ok": True, "message": "Webhook received", "echo": data}), 200


if __name__ == '__main__':
    # Render expects the app to listen on all interfaces, port 10000 or 8080
    import os
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
