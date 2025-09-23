import os.path
from pathlib import Path
from omegaconf import OmegaConf
import redis
import datetime
import json

CONFIG_PATH = Path(__file__).parent / "config.yaml"
cfg = OmegaConf.load(CONFIG_PATH)
cfg.data.root_dir = str((CONFIG_PATH.parent / cfg.data.root_dir).resolve())
BASE_DIR = cfg.data.root_dir
TRAIN_DIR = cfg.data.train.train_dir
TEST_DIR = cfg.data.train.test_dir
MODELS_DIR = str((CONFIG_PATH.parent / cfg.model.save_dir).resolve())
os.environ["CELLPOSE_LOCAL_MODELS_PATH"] = MODELS_DIR

r = redis.Redis(host="127.0.0.1", port=6379, db=0)

def set_status(task_id, status, **extra):
    payload = {"status": status, "updated_at": datetime.datetime.utcnow().isoformat(), **extra}
    r.set(f"task:{task_id}", json.dumps(payload), ex=86400)  # 1 天过期

def get_status(task_id):
    raw = r.get(f"task:{task_id}")
    return json.loads(raw) if raw else None

from cellpose import io, models, train

class Cptrain:

    @classmethod
    async def start_train(cls,
                    time: str | None = None,
                    model_name: str | None = None,
                    image_filter: str = "_img",
                    mask_filter: str = "_masks",
                    base_model: str = "cpsam"):

        train_dir = Path(TRAIN_DIR) / time
        test_dir = Path(TEST_DIR) / time
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(test_dir, exist_ok=True)
        io.logger_setup()
        output = io.load_train_test_data(str(train_dir), str(test_dir), image_filter=image_filter,
                                         mask_filter=mask_filter, look_one_level_down=False)
        images, labels, image_names, test_images, test_labels, image_names_test = output

        model = models.CellposeModel(gpu=True, pretrained_model=base_model)

        set_status(time, "running")

        model_path, train_losses, test_losses = train.train_seg(model.net,
                                                                train_data=images, train_labels=labels,
                                                                test_data=test_images, test_labels=test_labels,
                                                                weight_decay=0.1, learning_rate=1e-5,
                                                                n_epochs=100, model_name=model_name,
                                                                save_path=MODELS_DIR)

        print("模型已保存到:", model_path)
