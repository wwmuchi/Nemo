"""Nemo backend — serves the UI and runs probes through the selected model + judge."""

import os
import threading
import time
import traceback
import uuid
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

# ============ Job store ============
# Jobs run on a background thread so the browser can navigate away and resume.
JOBS = {}
JOBS_LOCK = threading.Lock()
JOB_TTL_SECONDS = 15 * 60  # GC finished jobs after this long


def _gc_jobs():
    now = time.time()
    with JOBS_LOCK:
        for jid in list(JOBS.keys()):
            j = JOBS[jid]
            if j.get("finished_at") and (now - j["finished_at"]) > JOB_TTL_SECONDS:
                del JOBS[jid]


def _run_probe_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return
    try:
        prompt = MODEL_PROMPT.format(question=job["question"])
        response_text = MODEL_FN[job["model"]](prompt)
        scores = judge(job["question"], response_text, job["thinkers"])
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is None:
                return
            j["response"] = response_text
            j["scores"] = scores
            j["status"] = "done"
            j["finished_at"] = time.time()
    except Exception as e:
        traceback.print_exc()
        with JOBS_LOCK:
            j = JOBS.get(job_id)
            if j is None:
                return
            j["error"] = str(e)
            j["status"] = "error"
            j["finished_at"] = time.time()


@app.route("/")
def index():
    return send_from_directory(HERE, "index.html")


@app.route("/compass")
@app.route("/compass/")
def compass():
    return send_from_directory(os.path.join(HERE, "compass"), "index.html")


@app.route("/compass/<path:filename>")
def compass_assets(filename):
    return send_from_directory(os.path.join(HERE, "compass"), filename)


@app.route("/scores")
@app.route("/scores/")
def scores():
    return send_from_directory(os.path.join(HERE, "scores"), "index.html")


@app.route("/scores/<path:filename>")
def scores_assets(filename):
    return send_from_directory(os.path.join(HERE, "scores"), filename)


@app.route("/images/<path:filename>")
def shared_images(filename):
    return send_from_directory(os.path.join(HERE, "images"), filename)


@app.route("/probe", methods=["POST"])
def probe_start():
    """Kick off a probe job on a background thread; return its id immediately."""
    try:
        data = request.get_json(force=True)
        question = data.get("question")
        model_name = data.get("model")
        thinkers = data.get("thinkers")

        if model_name not in MODEL_FN:
            return jsonify({"error": f"Unknown model: {model_name}"}), 400
        if not thinkers:
            return jsonify({"error": "No thinkers selected"}), 400

        _gc_jobs()

        job_id = uuid.uuid4().hex[:12]
        with JOBS_LOCK:
            JOBS[job_id] = {
                "id": job_id,
                "status": "running",
                "question": question,
                "model": model_name,
                "thinkers": thinkers,
                "response": None,
                "scores": None,
                "error": None,
                "started_at": time.time(),
                "finished_at": None,
            }

        threading.Thread(target=_run_probe_job, args=(job_id,), daemon=True).start()
        return jsonify({"job_id": job_id, "status": "running"})

    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500


@app.route("/probe/status/<job_id>")
def probe_status(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
    if not job:
        return jsonify({"error": "unknown job"}), 404
    return jsonify(job)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5050, debug=False)
