import os.path
from pathlib import Path
from omegaconf import OmegaConf
import redis
import datetime
import json

from sympy import false

CONFIG_PATH = Path(__file__).parent / "config.yaml"
cfg = OmegaConf.load(CONFIG_PATH)
cfg.data.root_dir = str((CONFIG_PATH.parent / cfg.data.root_dir).resolve())
BASE_DIR = cfg.data.root_dir
TRAIN_DIR = cfg.data.train.train_dir
TEST_DIR = cfg.data.train.test_dir
MODELS_DIR = str((CONFIG_PATH.parent / cfg.model.save_dir).resolve())
os.environ["CELLPOSE_LOCAL_MODELS_PATH"] = MODELS_DIR

r = redis.Redis(host="127.0.0.1", port=6379, db=0)

def set_status(task_id, status, train_losses, test_losses, **extra):
    """
    修改redis数据库中某一任务的运行状态

    Args:
        task_id: 这一任务的时间戳
        status: 任务状态
        train_losses: 此次任务的训练loss
        test_losses: 此次任务的测试loss
        **extra:

    Returns:

    """
    payload = {"status": status,
               "updated_at": datetime.datetime.utcnow().isoformat(),
               "train_losses": train_losses.tolist() if hasattr(train_losses, "tolist") else train_losses,
               "test_losses": test_losses.tolist() if hasattr(test_losses, "tolist") else test_losses,
               **extra}
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
                          base_model: str = "cpsam",
                          train_probs: list[float] = None,
                          test_probs: list[float] = None,
                          batch_size: int = 8,
                          learning_rate = 5e-5,
                          n_epochs: int = 100,
                          weight_decay=0.1,
                          normalize: bool =True,
                          compute_flows: bool = False,
                          min_train_masks: int = 5,
                          nimg_per_epoch: int =None,
                          rescale: bool= False,
                          scale_range=None,
                          channel_axis: int = None,
                          ):
        """
        开始训练

        Args:
            time: 此次任务的时间戳（即任务ID）
            model_name: 训练结果命名
            image_filter:
            mask_filter:
            base_model:
            train_probs:
            test_probs:
            batch_size:
            learning_rate:
            n_epochs:
            weight_decay:
            normalize:
            compute_flows:
            min_train_masks:
            nimg_per_epoch:
            rescale:
            scale_range:
            channel_axis:

        Returns:

        """

        train_dir = Path(TRAIN_DIR) / time
        test_dir = Path(TEST_DIR) / time
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(test_dir, exist_ok=True)
        io.logger_setup()
        output = io.load_train_test_data(str(train_dir), str(test_dir), image_filter=image_filter,
                                         mask_filter=mask_filter, look_one_level_down=False)
        images, labels, image_names, test_images, test_labels, image_names_test = output

        model = models.CellposeModel(gpu=True, pretrained_model=base_model)

        set_status(time, "running", None, None)

        model_path, train_losses, test_losses = train.train_seg(model.net,
                                                                train_data=images, train_labels=labels,
                                                                test_data=test_images, test_labels=test_labels,
                                                                train_probs=train_probs, test_probs=test_probs,
                                                                weight_decay=weight_decay, learning_rate=learning_rate,
                                                                n_epochs=n_epochs, model_name=model_name,
                                                                save_path=BASE_DIR, batch_size=batch_size,
                                                                normalize=normalize, compute_flows=compute_flows, min_train_masks=min_train_masks,
                                                                nimg_per_epoch=nimg_per_epoch, rescale=rescale, scale_range=scale_range, channel_axis=channel_axis
                                                                )

        set_status(time, "done", train_losses, test_losses)
        print("模型已保存到:", model_path)
        return train_losses, test_losses
