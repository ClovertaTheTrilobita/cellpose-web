from cellpose import models, plot
from cellpose.io import imread, save_masks
from PIL import Image
import numpy as np
import os, datetime
from typing import Literal

from sympy import false


class Cprun:
    # def __init__(self, model: str | Literal["cpsam"], images: list[str] | str):
    #     self.model = model
    #     self.images = images

    @classmethod
    def run_test(cls):
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

        ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        outdir = os.path.join(os.path.dirname(__file__), "test_output", ts)
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
                  time: datetime.datetime | None = None,
                  model: str | str = "cpsam",
                  diameter: float | None = None,
                  flow_threshold: float | float = 0.4,
                  cellprob_threshold: float | float = 0.0, ):

        if time is None:
            return [False, "No time received"]

        if images is None:
            return [False, "No images received"]

        message = [f"Using {model} model"]

        model = models.CellposeModel(gpu=True, model_type=model)
        files = images
        imgs = [imread(f) for f in files]
        masks, flows, styles = model.eval(
            imgs,
            flow_threshold=flow_threshold,
            cellprob_threshold=cellprob_threshold,
            diameter=diameter
        )

        ts = datetime.datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
        outdir = os.path.join(os.path.dirname(__file__), "run_output", ts)
        os.makedirs(outdir, exist_ok=True)  # 自动创建目录
        for img, mask, flow, name in zip(imgs, masks, flows, files):
            base = os.path.join(outdir, os.path.splitext(os.path.basename(name))[0])
            # 使用内置绘图生成蒙版
            out = base + "_output"
            save_masks(imgs, mask, flow, out, tif=True)

            # 用 plot 生成彩色叠加图（不依赖 skimage）
            rgb = plot.image_to_rgb(img, channels=[0, 0])  # 原图转 RGB
            over = plot.mask_overlay(rgb, masks=mask, colors=None)  # 叠加彩色实例
            Image.fromarray(over).save(base + "_overlay.png")

        message.append(f"Output saved to: {outdir}")
        return [True, message]