from cp_run import Cprun
from flaskApp import run_dev
from multiprocessing import Process


if __name__ == "__main__":
    # 启动测试服务器
    p = Process(target=run_dev)
    p.start()
    print(f"Flask running in PID {p.pid}")