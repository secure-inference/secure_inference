import torch
import numpy as np
from mmseg.models.builder import HEADS
from mmseg.models.decode_heads import ASPPHead
from research.secure_inference_3pc.modules.base import DummyShapeTensor

@HEADS.register_module()
class SecureASPPHead(ASPPHead):
    """Rethinking Atrous Convolution for Semantic Image Segmentation.

    This head is the implementation of `DeepLabV3
    <https://arxiv.org/abs/1706.05587>`_.

    Args:
        dilations (tuple[int]): Dilation rates for ASPP module.
            Default: (1, 6, 12, 18).
    """

    def __init__(self, dilations=(1, 6, 12, 18), **kwargs):
        super(SecureASPPHead, self).__init__(dilations, **kwargs)

    def cls_seg(self, feat):

        output = self.conv_seg(feat)
        return output

    def _forward_feature(self, inputs):
        """Forward function for feature maps before classifying each pixel with
        ``self.cls_seg`` fc.

        Args:
            inputs (list[Tensor]): List of multi-level img features.

        Returns:
            feats (Tensor): A tensor of shape (batch_size, self.channels,
                H, W) which is feature map for last layer of decoder head.
        """
        x = self._transform_inputs(inputs)
        tmp = self.image_pool(x)

        # tmp = np.mean(x, axis=(2, 3), keepdims=True, dtype=x.dtype)  # TODO: use gloval_average which was already implemented
        if type(tmp) == DummyShapeTensor:
            aspp_outs = [
                DummyShapeTensor((tmp[0], tmp[1], x[2], x[3]))
            ]
        else:
            aspp_outs = [
                tmp.repeat(x.shape[2], axis=2).repeat(x.shape[3], axis=3) # TODO: check if there is a better way to do this
            ]
        aspp_outs.extend(self.aspp_modules(x))
        # aspp_outs = torch.cat(aspp_outs, dim=1)
        if type(aspp_outs[0]) == DummyShapeTensor:
            aspp_outs = DummyShapeTensor((aspp_outs[0][0], sum(x[1] for x in aspp_outs), aspp_outs[0][2], aspp_outs[0][3]))
        else:
            aspp_outs = np.concatenate(aspp_outs, axis=1)
        feats = self.bottleneck(aspp_outs)
        return feats
    # def _forward_feature(self, inputs):
    #     """Forward function for feature maps before classifying each pixel with
    #     ``self.cls_seg`` fc.
    #
    #     Args:
    #         inputs (list[Tensor]): List of multi-level img features.
    #
    #     Returns:
    #         feats (Tensor): A tensor of shape (batch_size, self.channels,
    #             H, W) which is feature map for last layer of decoder head.
    #     """
    #     x = self._transform_inputs(inputs)
    #     tmp = self.image_pool(x)
    #
    #     # tmp = np.mean(x, axis=(2, 3), keepdims=True, dtype=x.dtype)  # TODO: use gloval_average which was already implemented
    #     aspp_outs = [
    #         tmp # TODO: check if there is a better way to do this
    #     ]
    #     aspp_outs.extend(self.aspp_modules(x))
    #     if type(aspp_outs[0]) == DummyShapeTensor:
    #         aspp_outs = DummyShapeTensor((aspp_outs[0][0], sum(x[1] for x in aspp_outs), aspp_outs[0][2], aspp_outs[0][3]))
    #     else:
    #         aspp_outs = np.concatenate(aspp_outs, axis=1)
    #     feats = self.bottleneck(aspp_outs)
    #     return feats
