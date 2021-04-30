# coding: utf-8
"""
Synthesis waveform from trained WaveNet.

Modified from https://github.com/r9y9/wavenet_vocoder
"""

import torch
from tqdm import tqdm
import librosa
from autovc.hparams import hparams
from wavenet_vocoder import builder
import yaml

from parallel_wavegan.models import MelGANGenerator
from parallel_wavegan.utils import load_model, download_pretrained_model

#torch.set_num_threads(4)
# use_cuda = torch.cuda.is_available()
# device = torch.device("cuda" if use_cuda else "cpu")

def build_model_melgan():
    download_pretrained_model("vctk_multi_band_melgan.v2", "melgan")
    # vocoder_conf = "melgan/vctk_multi_band_melgan.v2/config.yml"
    # with open(vocoder_conf) as f:
    #     config = yaml.load(f, Loader=yaml.Loader)
        
    # pytorch_melgan = MelGANGenerator(**config["generator_params"])
    # pytorch_melgan.remove_weight_norm()
    pytorch_melgan = load_model("melgan/vctk_multi_band_melgan.v2/checkpoint-1000000steps.pkl")
    # pytorch_melgan.load_state_dict(torch.load(
    #     "./networks/checkpoint-melgan.pkl", map_location="cpu")["model"]["generator"])
    return pytorch_melgan


def build_model():
    
    model = getattr(builder, hparams.builder)(
        out_channels=hparams.out_channels,
        layers=hparams.layers,
        stacks=hparams.stacks,
        residual_channels=hparams.residual_channels,
        gate_channels=hparams.gate_channels,
        skip_out_channels=hparams.skip_out_channels,
        cin_channels=hparams.cin_channels,
        gin_channels=hparams.gin_channels,
        weight_normalization=hparams.weight_normalization,
        n_speakers=hparams.n_speakers,
        dropout=hparams.dropout,
        kernel_size=hparams.kernel_size,
        upsample_conditional_features=hparams.upsample_conditional_features,
        upsample_scales=hparams.upsample_scales,
        freq_axis_kernel_size=hparams.freq_axis_kernel_size,
        scalar_input=True,
        legacy=hparams.legacy,
    )
    return model



def melgan(model, device, c=None):
    model.eval()
    
    Tc = c.shape[0]
    upsample_factor = hparams.hop_size
    # Overwrite length according to feature size
    length = Tc * upsample_factor

    # B x C x T
    c = torch.FloatTensor(c)# .unsqueeze(0)[0]

    # initial_input = torch.zeros(1, 1, 1).fill_(0.0)

    # # Transform data to GPU
    # initial_input = initial_input.to(device)
    c = None if c is None else c.to(device)

    print(c.shape)
    with torch.no_grad():
        y_hat = model.inference(c)

    y_hat = y_hat.view(-1).cpu().data.numpy()

    return y_hat

def wavegen(model, device, c=None, tqdm=tqdm):
    """Generate waveform samples by WaveNet.
    
    """

    model.eval()
    model.make_generation_fast_()

    Tc = c.shape[0]
    upsample_factor = hparams.hop_size
    # Overwrite length according to feature size
    length = Tc * upsample_factor

    # B x C x T
    c = torch.FloatTensor(c.T).unsqueeze(0)

    initial_input = torch.zeros(1, 1, 1).fill_(0.0)

    # Transform data to GPU
    initial_input = initial_input.to(device)
    c = None if c is None else c.to(device)

    with torch.no_grad():
        y_hat = model.incremental_forward(
            initial_input, c=c, g=None, T=length, tqdm=tqdm, softmax=True, quantize=True,
            log_scale_min=hparams.log_scale_min)

    y_hat = y_hat.view(-1).cpu().data.numpy()

    return y_hat