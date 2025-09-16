from cellpose import models
from cellpose.io import imread, save_masks

def test():
    model = models.CellposeModel(gpu=True)
    files = ['img.png']
    imgs = [imread(f) for f in files]
    masks, flows, styles = model.eval(
        imgs, flow_threshold=0.4, cellprob_threshold=0.0
    )


    for img, mask, flow, name in zip(imgs, masks, flows, files):
        out = name.rsplit('.', 1)[0] + "_output"
        save_masks(imgs, mask, flow, out, png=True)
