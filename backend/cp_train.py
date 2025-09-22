import os.path
from cellpose import io, models, train
from pathlib import Path
from omegaconf import OmegaConf

CONFIG_PATH = Path(__file__).parent / "config.yaml"
cfg = OmegaConf.load(CONFIG_PATH)
cfg.data.root_dir = str((CONFIG_PATH.parent / cfg.data.root_dir).resolve())
BASE_DIR = cfg.data.root_dir
TEST_TRAIN_DIR = cfg.data.train.test_train_dir
TEST_TEST_DIR = cfg.data.train.test_test_dir
MODELS_DIR = str((CONFIG_PATH.parent / cfg.model.save_dir).resolve())

class Cptrain:

    @classmethod
    def start_train(cls,
                    time: str | None = None,
                    model_name: str | None = None,):

        train_dir = Path(TEST_TRAIN_DIR) / time
        test_dir = Path(TEST_TEST_DIR) / time
        os.makedirs(train_dir, exist_ok=True)
        os.makedirs(test_dir, exist_ok=True)
        io.logger_setup()
        output = io.load_train_test_data(str(train_dir), str(test_dir), image_filter="_img",
                                         mask_filter="_masks", look_one_level_down=False)
        images, labels, image_names, test_images, test_labels, image_names_test = output

        model = models.CellposeModel(gpu=True)

        model_path, train_losses, test_losses = train.train_seg(model.net,
                                                                train_data=images, train_labels=labels,
                                                                test_data=test_images, test_labels=test_labels,
                                                                weight_decay=0.1, learning_rate=1e-5,
                                                                n_epochs=100, model_name=model_name,
                                                                save_path=MODELS_DIR)

        print("模型已保存到:", model_path)