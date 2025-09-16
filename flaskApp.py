from flask import Flask, send_from_directory, request, jsonify
import os, shutil, time, threading
from werkzeug.utils import secure_filename

app = Flask(__name__)
UPLOAD_DIR = "./uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

def run_flask():
    app.run(host="10.147.18.141", port=5000)

@app.route("/")
def index():
    return "<h1>Hello</h1><p>This is the backend of our cellpose server, please visit our website.</p>"

@app.route("/testdl")
def test_download():
    return send_from_directory("./test_output/2025-09-16-20-03-51", "img_overlay.png", as_attachment=True)

@app.route("/dl/<timestamp>")
def download(timestamp):
    input_dir = os.path.join("./output", timestamp)
    output_dir = os.path.join("./output/tmp", timestamp)  # 不要加 .zip，make_archive 会自动加
    os.makedirs("./output/tmp", exist_ok=True)  # 确保 tmp 存在
    shutil.make_archive(output_dir, 'zip', input_dir)
    print(f"压缩完成: {output_dir}.zip")
    return send_from_directory("./output/tmp", f"{timestamp}.zip", as_attachment=True)


@app.post("/upload")
def upload():
    files = request.files.getlist("files")  # ← 前端用同一个键名多次 append
    saved = []
    for f in files:
        if not f or f.filename == "":
            continue
        name = secure_filename(f.filename)
        f.save(os.path.join(UPLOAD_DIR, name))
        saved.append(name)
    return jsonify({"ok": True, "count": len(saved), "files": saved})