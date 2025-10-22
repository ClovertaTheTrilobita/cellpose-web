import os
from PIL import Image
import numpy as np
import datetime
import time
from omegaconf import OmegaConf
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.yaml"
cfg = OmegaConf.load(CONFIG_PATH)
cfg.data.root_dir = str((CONFIG_PATH.parent / cfg.data.root_dir).resolve())
BASE_DIR = cfg.data.root_dir
UPLOAD_DIR = cfg.data.upload_dir
OUTPUT_DIR = cfg.data.run.output_dir
OUTPUT_TEST_DIR = cfg.data.run.test_output_dir
MODELS_DIR = str((CONFIG_PATH.parent / cfg.model.save_dir).resolve())
os.makedirs(MODELS_DIR, exist_ok=True)
os.environ["CELLPOSE_LOCAL_MODELS_PATH"] = MODELS_DIR

from cellpose import models, plot
from cellpose.io import imread, save_masks

class Cprun:

    @classmethod
    def run_test(cls):
        """
        仅测试用

        :return:
        """
        model = models.CellposeModel(gpu=True)
        files = ['test_tif/img.png']
        imgs = [imread(f) for f in files]
        masks, flows, styles = model.eval(
            imgs, flow_threshold=0.4, cellprob_threshold=0.0
        )
        for i, m in enumerate(masks):
            print(
                f"[{i}] mask max={int(getattr(m, 'max', lambda: 0)()) if hasattr(m, 'max') else int(np.max(m))}, unique={np.unique(m)[:5]} ..."
            )

        ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S") + f"-{int(time.time()*1000)%1000:03d}"
        outdir = os.path.join(OUTPUT_TEST_DIR, ts)
        os.makedirs(outdir, exist_ok=True)  # 自动创建目录
        for img, mask, flow, name in zip(imgs, masks, flows, files):
            base = os.path.join(outdir, os.path.splitext(os.path.basename(name))[0])
            #使用内置绘图生成蒙版
            out = base + "_output"
            save_masks(imgs, mask, flow, out, tif=True)

            # 用 plot 生成彩色叠加图（不依赖 skimage）
            rgb = plot.image_to_rgb(img, channels=[0, 0])  # 原图转 RGB
            over = plot.mask_overlay(rgb, masks=mask, colors=None)  # 叠加彩色实例
            Image.fromarray(over).save(base + "_overlay.png")

    @classmethod
    async def run(cls,
                  images: list[str] | str | None = None,
                  time: str | None = None,
                  model: str = "cpsam",
                  diameter: float | None = None,
                  flow_threshold: float = 0.4,
                  cellprob_threshold: float = 0.0, ):
        """
        运行 cellpose 分割

        Args:
            images: [list] 图片存储路径
            time: [str] 开始运行的时间，相当于本次运行的ID，用于存储运行结果
            model: [str] 图像分割所使用的模型
            diameter: [float]  diameters are used to rescale the image to 30 pix cell diameter.
            flow_threshold: [float] flow error threshold (all cells with errors below threshold are kept) (not used for 3D). Defaults to 0.4.
            cellprob_threshold: [float] all pixels with value above threshold kept for masks, decrease to find more and larger masks. Defaults to 0.0.

        Returns:

        """

        if time is None:
            return [False, "No time received"]

        if images is None:
            return [False, "No images received"]

        message = [f"Using {model} model"]

        # 设定模型参数
        model = models.CellposeModel(gpu=True, model_type=model)
        files = images
        imgs = [imread(f) for f in files] # 获取目录中的每一个文件
        masks, flows, styles = model.eval(
            imgs,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
            diameter=diameter
        )

        ts = time
        outdir = os.path.join(OUTPUT_DIR, ts)
        os.makedirs(outdir, exist_ok=True)  # 自动创建目录
        for img, mask, flow, name in zip(imgs, masks, flows, files):
            base = os.path.join(outdir, os.path.splitext(os.path.basename(name))[0])
            # 使用内置绘图生成蒙版
            out = base + "_output"
            save_masks(imgs, mask, flow, out, tif=True)

            # 用 plot 生成彩色叠加图
            rgb = plot.image_to_rgb(img, channels=[0, 0])  # 原图转 RGB
            over = plot.mask_overlay(rgb, masks=mask, colors=None)  # 叠加彩色实例
            Image.fromarray(over).save(base + "_overlay.png")

        message.append(f"Output saved to: {outdir}")
        message.append(outdir)
        return [True, message]
