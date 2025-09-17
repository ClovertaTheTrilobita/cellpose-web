import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
from flask import Flask, send_from_directory, request, jsonify
import os, shutil, time, threading, datetime, json, redis
from werkzeug.utils import secure_filename
from flask_cors import CORS
from pathlib import Path
from cp_run import Cprun

app = Flask(__name__)
CORS(app)
BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=4)
TASKS = {}
r = redis.Redis(host="127.0.0.1", port=6379, db=0)

# 启动测试服务器
def run_dev():
    app.run(host="10.147.18.141", port=5000)

def set_status(task_id, status, **extra):
    payload = {"status": status, "updated_at": datetime.datetime.utcnow().isoformat(), **extra}
    r.set(f"task:{task_id}", json.dumps(payload), ex=86400)  # 1 天过期

def get_status(task_id):
    raw = r.get(f"task:{task_id}")
    return json.loads(raw) if raw else None

@app.route("/")
def index():
    return "<h1>Hello</h1><p>This is the backend of our cellpose server, please visit our website.</p>"

@app.get("/testdl")
def test_download():
    return send_from_directory("test_output/2025-09-16-20-03-51", "img_overlay.png", as_attachment=True)

@app.get("/dl")
def download():
    timestamp = request.args.get("id")
    input_dir = os.path.join(BASE_DIR, "output", timestamp)
    output_dir = os.path.join(BASE_DIR, "output/tmp", timestamp)  # 不要加 .zip，make_archive 会自动加
    os.makedirs(BASE_DIR / "output/tmp", exist_ok=True)  # 确保 tmp 存在
    shutil.make_archive(output_dir, 'zip', input_dir)
    print(f"压缩完成: {output_dir}.zip")
    return send_from_directory("output/tmp", f"{timestamp}.zip", as_attachment=True)

@app.post("/upload")
def upload():
    """
    接收上传的文件，并将其发送给cellpose。
    :return:
    """

    # 从请求中获取参数，若没有则设定为默认值
    model = request.args.get("model") or request.form.get("model") or "cpsam"

    def _to_float(x, default):
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    flow_threshold = _to_float(request.args.get("flow_threshold") or request.form.get("flow_threshold"), 0.4)
    cellprob_threshold = _to_float(request.args.get("cellprob_threshold") or request.form.get("cellprob_threshold"),
                                   0.0)
    diameter_raw = request.args.get("diameter") or request.form.get("diameter")
    diameter = _to_float(diameter_raw, None) if diameter_raw not in (None, "") else None

    # 将文件保存在本地目录中
    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"-{int(time.time()*1000)%1000:03d}"
    os.makedirs(UPLOAD_DIR / ts, exist_ok=True)
    files = request.files.getlist("files")
    saved = []
    for f in files:
        if not f or f.filename == "":
            continue
        name = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD_DIR / ts, name))
        saved.append(os.path.join(UPLOAD_DIR, ts, name))

    # 新建一个线程，防止返回被阻塞
    def job():
        return asyncio.run(Cprun.run(
            images=saved, model=model,
            cellprob_threshold=cellprob_threshold,
            flow_threshold=flow_threshold,
            diameter=diameter, time=ts
        ))

    # 将线程状态存入redis
    set_status(ts, "running")
    fut = executor.submit(job)

    def done_cb(f):
        try:
            f.result()
            set_status(ts, "success")
        except Exception as e:
            set_status(ts, "failed", error=str(e))

    fut.add_done_callback(done_cb)

    return jsonify({"ok": True, "count": len(saved), "id": ts})

@app.get("/status")
def status():
    """
    检查某一cellpose任务是否完成

    :return:
    """
    task_id = request.args.get('id')
    st = get_status(task_id)
    if not st:
        return jsonify({"ok": True, "exists": False, "status": "not_found"}), 200
    return jsonify({"ok": True, "exists": True, **st}), 200

@app.get("/preview")
def preview():
    task_id = request.args.get('id')
    task_dir = BASE_DIR / "output" / task_id
    if not task_dir.exists():
        return jsonify({"ok": False, "error": "task not found"}), 200

    # 找出所有 *_overlay.png 文件
    files = sorted(task_dir.glob("*_overlay.png"))

    if not files:
        return jsonify({"ok": False, "error": "no overlay images"}), 200

    result = []
    for path in files:
        data = path.read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        result.append({
            "filename": path.name,
            "image": encoded
        })

    return jsonify({"ok": True, "count": len(result), "images": result})