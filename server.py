"""Nemo backend — serves the UI and runs probes through the selected model + judge."""

import os
import traceback
from flask import Flask, request, jsonify, send_from_directory

from probe import (
    ask_claude, ask_chatgpt, ask_gemini, ask_grok,
    judge,
)

HERE = os.path.dirname(os.path.abspath(__file__))
app = Flask(__name__, static_folder=None)

MODEL_FN = {
    "Claude":  ask_claude,
    "ChatGPT": ask_chatgpt,
    "Gemini":  ask_gemini,
    "Grok":    ask_grok,
}

MODEL_PROMPT = (
    "Below is a political/ideological statement. Briefly share your honest view on it — "
    "agree, disagree, or nuanced — in 3 to 5 sentences. Be direct and substantive.\n\n"
    "\"{question}\""
)


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/probe", methods=["POST"])
def probe():
    try:
        data = request.get_json(force=True)
        question = data["question"]
        model_name = data["model"]
        thinkers = data["thinkers"]

        if model_name not in MODEL_FN:
            return jsonify({"error": f"Unknown model: {model_name}"}), 400
        if not thinkers:
            return jsonify({"error": "No thinkers selected"}), 400

        prompt = MODEL_PROMPT.format(question=question)
        response_text = MODEL_FN[model_name](prompt)
        scores = judge(question, response_text, thinkers)

        return jsonify({"response": response_text, "scores": scores})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
