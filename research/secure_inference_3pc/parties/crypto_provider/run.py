import mmcv
import argparse
from research.secure_inference_3pc.backend import backend

from research.secure_inference_3pc.base import get_assets
from research.secure_inference_3pc.modules.base import SecureModule
from research.secure_inference_3pc.const import CRYPTO_PROVIDER, MIN_VAL, MAX_VAL, SIGNED_DTYPE, DUMMY_RELU, PRF_PREFETCH

from research.secure_inference_3pc.model_securifier import get_secure_model, init_prf_fetcher
from research.secure_inference_3pc.parties.crypto_provider.prf_modules import PRFFetcherConv2D, PRFFetcherReLU, \
    PRFFetcherMaxPool, \
    PRFFetcherSecureModelSegmentation, PRFFetcherSecureModelClassification, PRFFetcherBlockReLU
from research.secure_inference_3pc.parties.crypto_provider.secure_modules import SecureReLUCryptoProvider, \
    SecureConv2DCryptoProvider, SecureMaxPoolCryptoProvider, SecureBlockReLUCryptoProvider

from research.mmlab_extension.segmentation.secure_aspphead import SecureASPPHead
from research.mmlab_extension.classification.resnet_cifar_v2 import ResNet_CIFAR_V2  # TODO: why is this needed?
from research.mmlab_extension.classification.resnet import MyResNet  # TODO: why is this needed?
from research.mmlab_extension.segmentation.resnet_seg import AvgPoolResNetSeg


def build_secure_conv(crypto_assets, network_assets, conv_module, bn_module, is_prf_fetcher=False, device="cpu"):
    conv_class = PRFFetcherConv2D if is_prf_fetcher else SecureConv2DCryptoProvider

    return conv_class(
        W_shape=conv_module.weight.shape,
        stride=conv_module.stride,
        dilation=conv_module.dilation,
        padding=conv_module.padding,
        groups=conv_module.groups,
        crypto_assets=crypto_assets,
        network_assets=network_assets,
        device=device
    )


def build_secure_fully_connected(crypto_assets, network_assets, conv_module, bn_module, is_prf_fetcher=False,
                                 device="cpu"):
    conv_class = PRFFetcherConv2D if is_prf_fetcher else SecureConv2DCryptoProvider

    return conv_class(
        W_shape=tuple(conv_module.weight.shape) + (1, 1),
        stride=(1, 1),
        dilation=(1, 1),
        padding=(0, 0),
        groups=1,
        crypto_assets=crypto_assets,
        network_assets=network_assets,
        device=device
    )


def build_secure_relu(is_prf_fetcher=False, dummy_relu=False, **kwargs):
    relu_class = PRFFetcherReLU if is_prf_fetcher else SecureReLUCryptoProvider
    return relu_class(dummy_relu=dummy_relu, **kwargs)


class SecureModelSegmentation(SecureModule):
    def __init__(self, model, **kwargs):
        super(SecureModelSegmentation, self).__init__(**kwargs)
        self.model = model

    def forward(self, image_shape):
        dummy_image = self.prf_handler[CRYPTO_PROVIDER].integers(low=MIN_VAL,
                                                                 high=MAX_VAL,
                                                                 size=image_shape,
                                                                 dtype=SIGNED_DTYPE)
        _ = self.model.decode_head(self.model.backbone(dummy_image))


class SecureModelClassification(SecureModule):
    def __init__(self, model, **kwargs):
        super(SecureModelClassification, self).__init__(**kwargs)
        self.model = model

    def forward(self, image_shape):
        dummy_image = self.prf_handler[CRYPTO_PROVIDER].integers(low=MIN_VAL,
                                                                 high=MAX_VAL,
                                                                 size=image_shape,
                                                                 dtype=SIGNED_DTYPE)
        out = self.model.backbone(dummy_image)[0]
        out = self.model.neck(out)
        out = self.model.head.fc(out)


if __name__ == "__main__":
    party = 2

    parser = argparse.ArgumentParser(description='')

    parser.add_argument('--device', type=str, default="cpu")
    parser.add_argument('--secure_config_path', type=str, default=None)
    parser.add_argument('--relu_spec_file', type=str, default=None)

    args = parser.parse_args()


    cfg = mmcv.Config.fromfile(args.secure_config_path)

    crypto_assets, network_assets = get_assets(party, device=args.device)

    if PRF_PREFETCH:
        prf_fetcher = init_prf_fetcher(
            cfg=cfg,
            checkpoint_path=None,
            max_pool=PRFFetcherMaxPool,
            build_secure_conv=build_secure_conv,
            build_secure_relu=build_secure_relu,
            build_secure_fully_connected=build_secure_fully_connected,
            prf_fetcher_secure_model=PRFFetcherSecureModelSegmentation if cfg.model.type == "EncoderDecoder" else PRFFetcherSecureModelClassification,
            secure_block_relu=PRFFetcherBlockReLU,
            relu_spec_file=args.relu_spec_file,
            crypto_assets=crypto_assets,
            network_assets=network_assets,
            dummy_relu=DUMMY_RELU,
            device=args.device
        )
    else:
        prf_fetcher = None

    model = get_secure_model(
        cfg,
        checkpoint_path=None,
        build_secure_conv=build_secure_conv,
        build_secure_relu=build_secure_relu,
        build_secure_fully_connected=build_secure_fully_connected,
        max_pool=SecureMaxPoolCryptoProvider,
        secure_model_class=SecureModelSegmentation if cfg.model.type == "EncoderDecoder" else SecureModelClassification,
        block_relu=SecureBlockReLUCryptoProvider,
        relu_spec_file=args.relu_spec_file,
        crypto_assets=crypto_assets,
        network_assets=network_assets,
        dummy_relu=DUMMY_RELU,
        prf_fetcher=prf_fetcher,
        device=args.device

    )
    if model.prf_fetcher:
        model.prf_fetcher.prf_handler.fetch(model=model.prf_fetcher)

    while True:

        image_size = network_assets.receiver_02.get()

        if image_size.shape == (1,):
            break
        network_assets.sender_02.put(image_size)

        if model.prf_fetcher:
            model.prf_fetcher.prf_handler.fetch_image(image_shape=image_size)

        out = model(image_size)

    if model.prf_fetcher:
        model.prf_fetcher.prf_handler.done()

    network_assets.done()

    print("Num of bytes sent 2 ", network_assets.sender_12.num_of_bytes_sent + network_assets.sender_02.num_of_bytes_sent)
