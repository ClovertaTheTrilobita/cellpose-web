import asyncio
import base64
import datetime
import json
import os
import redis
import shutil
import time
from omegaconf import OmegaConf
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from flask import Flask, send_from_directory, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename

from cp_train import Cptrain
from cp_run import Cprun

app = Flask(__name__)
CORS(app)

CONFIG_PATH = Path(__file__).parent / "config.yaml"
cfg = OmegaConf.load(CONFIG_PATH)
cfg.data.root_dir = str((CONFIG_PATH.parent / cfg.data.root_dir).resolve())
BASE_DIR = cfg.data.root_dir
UPLOAD_DIR = cfg.data.upload_dir
OUTPUT_DIR = cfg.data.run.output_dir
MODELS_DIR = str((CONFIG_PATH.parent / cfg.model.save_dir).resolve())
TRAIN_DIR  = cfg.data.train.train_dir
TEST_DIR = cfg.data.train.test_dir
BACKEND_IP = cfg.backend.ip
BACKEND_PORT = cfg.backend.port

os.makedirs(UPLOAD_DIR, exist_ok=True)
executor = ThreadPoolExecutor(max_workers=4)
TASKS = {}
r = redis.Redis(host="127.0.0.1", port=6379, db=0)

# 启动测试服务器
def run_dev():
    app.run(host=BACKEND_IP, port=int(BACKEND_PORT))

def set_status(task_id, status, **extra):
    payload = {"status": status, "updated_at": datetime.datetime.utcnow().isoformat(), **extra}
    r.set(f"task:{task_id}", json.dumps(payload), ex=86400)  # 1 天过期

def set_train_status(task_id, status, train_losses, test_losses, **extra):
    payload = {"status": status,
               "updated_at": datetime.datetime.utcnow().isoformat(),
               "train_losses": train_losses.tolist() if hasattr(train_losses, "tolist") else train_losses,
               "test_losses": test_losses.tolist() if hasattr(test_losses, "tolist") else test_losses,
               **extra}
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
    input_dir = os.path.join(OUTPUT_DIR, timestamp)
    output_dir = os.path.join(OUTPUT_DIR, "tmp", timestamp)  # 不要加 .zip，make_archive 会自动加
    os.makedirs(Path(OUTPUT_DIR) / "tmp", exist_ok=True)  # 确保 tmp 存在
    shutil.make_archive(output_dir, 'zip', input_dir)
    print(f"压缩完成: {output_dir}.zip")
    print(OUTPUT_DIR)
    return send_from_directory(f"{OUTPUT_DIR}/tmp/", f"{timestamp}.zip", as_attachment=True)

@app.post("/run_upload")
def run_upload():
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

    print("cpt:" + str(cellprob_threshold))
    print("flow:" + str(flow_threshold))
    print("diameter:" + str(diameter))

    # 将文件保存在本地目录中
    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"-{int(time.time()*1000)%1000:03d}"
    os.makedirs(Path(UPLOAD_DIR) / ts, exist_ok=True)
    files = request.files.getlist("files")
    saved = []
    for f in files:
        if not f or f.filename == "":
            continue
        name = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD_DIR, ts, name))
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

@app.post("/train_upload")
def train_upload():

    def _to_float(x, default):
        try:
            return float(x)
        except (TypeError, ValueError):
            return default

    def _to_int(x, default):
        try:
            return int(x)
        except (TypeError, ValueError):
            return default

    ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"-{int(time.time()*1000)%1000:03d}"
    model_name = request.args.get("model_name") or f"custom_model-{ts}"
    image_filter = request.args.get("image_filter") or "_img"
    mask_filter = request.args.get("mask_filter") or "_masks"
    base_model = request.args.get("base_model") or "cpsam"
    batch_size = _to_int(request.args.get("batch_size"), 8)
    learning_rate = _to_float(request.args.get("learning_rate"), 5e-5)
    n_epochs = _to_int(request.args.get("n_epochs"), 100)
    weight_decay = _to_float(request.args.get("weight_decay"), 0.1)
    normalize = request.args.get(
        "normalize",
        default=True,
        type=lambda v: str(v).strip().lower() in ("1","true","t","yes","y","on")
    )
    compute_flows = request.args.get(
        "compute_flows",
        default=True,
        type=lambda v: str(v).strip().lower() in ("1","true","t","yes","y","on")
    )
    min_train_masks = _to_int(request.args.get(" min_train_masks"), 5)
    nimg_per_epoch = _to_int(request.args.get("nimg_per_epoch"), None)
    rescale = request.args.get(
        "rescale",
        default=False,
        type=lambda v: str(v).strip().lower() in ("1","true","t","yes","y","on")
    )
    scale_range = _to_float(request.args.get("scale_range"), None)
    channel_axis = _to_int(request.args.get("channel_axis"), None)

    train_files = request.files.getlist("train_files")
    test_files = request.files.getlist("test_files")
    os.makedirs(Path(TRAIN_DIR) /  ts, exist_ok=True)
    os.makedirs(Path(TEST_DIR) / ts, exist_ok=True)
    set_status(ts, "pending")
    saved = []
    for f in train_files:
        if not f or f.filename == "":
            continue
        name = secure_filename(f.filename)
        f.save(os.path.join(TRAIN_DIR, ts, name))
        saved.append(os.path.join(TRAIN_DIR, ts, name))

    for f in test_files:
        if not f or f.filename == "":
            continue
        name = secure_filename(f.filename)
        f.save(os.path.join(TEST_DIR, ts, name))
        saved.append(os.path.join(TEST_DIR, ts, name))

    def job():
        return asyncio.run(Cptrain.start_train(
            time=ts,
            model_name=model_name,
            image_filter=image_filter,
            mask_filter=mask_filter,
            base_model=base_model,
            batch_size=batch_size,
            learning_rate=learning_rate,
            n_epochs=n_epochs,
            weight_decay=weight_decay,
            normalize=normalize,
            compute_flows=compute_flows,
            min_train_masks=min_train_masks,
            nimg_per_epoch=nimg_per_epoch,
            rescale=rescale,
            scale_range=scale_range,
            channel_axis=channel_axis,
        ))

    fut = executor.submit(job)

    def done_cb(f):
        try:
            train_losses, test_losses = f.result()
            set_train_status(ts, "success", train_losses, test_losses)
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
    task_dir = Path(OUTPUT_DIR) / task_id
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

@app.get("/models")
def list_models():
    models_list = os.listdir(MODELS_DIR)
    return jsonify({"ok": True, "models": models_list})

@app.get("/result")
def list_results():
    task_id = request.args.get('id')
    st = get_status(task_id)
    if not st:
        return jsonify({"ok": True, "exists": False, "status": "not_found"}), 200
    return jsonify({"ok": True, "exists": True, **st}), 200
