from cp_run import Cprun
from flaskApp import run_flask
from multiprocessing import Process


if __name__ == "__main__":
    # Cprun.run_test()
    p = Process(target=run_flask)
    p.start()
    print(f"Flask running in PID {p.pid}")