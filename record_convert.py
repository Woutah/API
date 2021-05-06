
import pyaudio
import wave
import logging
import argparse
import os
import pickle
from math import ceil

import numpy as np
import soundfile as sf
import torch

from collections import OrderedDict
from autovc.model_bl import D_VECTOR
from autovc.model_vc import Generator
from config import Config
import utility
from data_converter import Converter
from vocoders import MelGan
from data_converter_melgan import MelganConverter
import threading, queue, collections
import librosa
import yaml
import hdfdict
import sklearn 
import time
from NumpyQueue import NumpyQueue, ThreadNumpyQueue
from PyQt5 import QtCore, QtGui, QtWidgets
import pyaudio
log = logging.getLogger(__name__ )
 

FORMAT=pyaudio.paFloat32
CHANNELS = 1
CHUNK = 4000
WAVE_OUTPUT_FILENAME = "./sample_recording.wav"
RECORD_SIZE_FRAMES=512


class VoiceRecoder(QtWidgets.QMainWindow):
    def __init__(self, melgan_config, melgan_stats, device, melgan_converter, generator, speaker_encoder, target_embedding, vocoder, source_embedding, processing_buffer_size=24000 * 20, default_wav_path=None):
        #===============================GUI=======================================

        super(VoiceRecoder, self).__init__()
        
        self.setObjectName("VoiceRecorder")
        self.setWindowTitle("Voice Converter")
        self.resize(500, 300)

        self.central_widget = QtWidgets.QWidget(self)
        self.setCentralWidget(self.central_widget)

        self.layout = QtWidgets.QVBoxLayout()

        #============================Buttons=================================

        
        #=========Recording buttons===========
        self.recording_btn_layout= QtWidgets.QHBoxLayout()
        self.btn_record = QtWidgets.QPushButton(text="Record")
        self.btn_record.clicked.connect(self.record)
        self.recording_btn_layout.addWidget(self.btn_record, 10)
        
        self.btn_play_recording = QtWidgets.QPushButton(text="Play")
        self.btn_play_recording.clicked.connect(self.play_recorded_wav)
        self.recording_btn_layout.addWidget(self.btn_play_recording, 1)

        self.btn_load_recording = QtWidgets.QPushButton(text="Load")
        self.btn_load_recording.clicked.connect(self.load_wav_dialog)
        self.recording_btn_layout.addWidget(self.btn_load_recording, 1)
        self.btn_save_recording = QtWidgets.QPushButton(text="Save")
        self.btn_save_recording.clicked.connect(self.save_result_wav)
        self.recording_btn_layout.addWidget(self.btn_save_recording, 1)


        self.layout.addLayout(self.recording_btn_layout)


        #======Other==================
        self.btn_convert = QtWidgets.QPushButton(text="Convert")
        self.btn_convert.clicked.connect(self.convert)
        self.layout.addWidget(self.btn_convert)

        self.btn_play = QtWidgets.QPushButton(text="Play")
        self.btn_play.clicked.connect(self.play_result_wav)
        self.layout.addWidget(self.btn_play)

        
        self.btn_load_target_embed = QtWidgets.QPushButton(text="Load Target")
        self.btn_load_target_embed.clicked.connect(self.pick_file)
        self.layout.addWidget(self.btn_load_target_embed)

    
        self.btn_set_random_target = QtWidgets.QPushButton(text="Randomize Target Embedding")
        self.btn_set_random_target.clicked.connect(self.randomize_target)
        self.layout.addWidget(self.btn_set_random_target)
        
        self.btn_save_wav = QtWidgets.QPushButton(text="Save Wav")
        self.btn_save_wav.clicked.connect(self.save_result_wav)
        self.layout.addWidget(self.btn_save_wav)

        self.central_widget.setLayout(self.layout)
        # self.head_layout.addLayout(self.layout)
        # self.show()
        # self.layout 



        #==================Melgan properties=========================
        #General properties
        self.melgan_config = melgan_config
        self.sampling_rate = self.melgan_config["sampling_rate"]
        self.hop_size = self.melgan_config["hop_size"]
        self.fft_size = self.melgan_config["fft_size"]
        self.win_length = self.melgan_config["win_length"]
        self.window = self.melgan_config["window"]
        self.num_mels = self.melgan_config["num_mels"]
        self.fmin = self.melgan_config["fmin"]
        self.fmax = self.melgan_config["fmax"]

        #Trim silence
        self.trim_silence = self.melgan_config["trim_silence"]
        self.trim_top_db=self.melgan_config["trim_threshold_in_db"]
        self.trim_frame_length=self.melgan_config["trim_frame_size"]
        self.trim_hop_length=self.melgan_config["trim_hop_size"]
    

        # restore Melgan conversion scaler
        self.scaler = sklearn.preprocessing.StandardScaler()
        self.scaler.mean_ = melgan_stats["mean"]
        self.scaler.scale_ = melgan_stats["scale"]
        self.scaler.n_features_in_ = self.scaler.mean_.shape[0]

        #==================Other========================
        self.device= device
        self.melgan_convert = melgan_converter
        self.generator = generator
        self.speaker_encoder = speaker_encoder
        self.target_embedding = target_embedding
        self.vocoder = vocoder


        # self.source_embed = torch.tensor(np.zeros(256, dtype=np.float32)).to(device)
        self.source_embedding = source_embedding

        self._unprocessed_frames = 0
        log.info("Done initializing LiveConverter")
        # self.unprocessed_frames_counter = threading.Lock()
        self.result_wav = None

        self.recorded_wav = None
        if default_wav_path is not None:
            self.load_wav(default_wav_path)
            # print(self.recorded_wav)
        
        # self.create_result_wav()

    def play_recorded_wav(self):
        if self.recorded_wav is not None:
            utility.play_wav_from_npy(self.recorded_wav)
        else:
            log.error("No recorded wav, can't play")


    def load_wav(self, wav_path):
        if wav_path is None:
            log.error("No path given, could not load wav")
            return
        log.info(f"Trying to load wav at {wav_path}")
        wav = None
        try:
            wav, sr = sf.read(wav_path)
            if sr != self.sampling_rate: #Resampling
                log.info("Unmatching sampling rate, now resampling...")
                wav = librosa.resample(wav, sr, self.sampling_rate)
            wav = np.array(wav, dtype=np.float32)
        except Exception as err:
            log.error(f"Error when loading {wav_path} - {err} - defaulting to original recorded wav")
            return
            # self.recorded_wav = None
        self.recorded_wav = wav 

    def load_wav_dialog(self):
        fname = QtWidgets.QFileDialog.getOpenFileName(self, 'Open file', 
                ".","Recording (*.wav)")
        if fname is not None:
            self.load_wav(fname[0])

    def save_wav_dialog(self, wav, sampling_rate):
        if wav is None:
            log.error(f"Could not save wav, wav is: {wav}")
            return
        

        savename = QtWidgets.QFileDialog.getSaveFileName(self, "Save file", "", ".wav")
        log.info(f"Trying to save wav as {savename}")
        try:
            sf.write(savename[0] + ".wav", wav, sampling_rate) #Try to save it
        except Exception as err:
            log.info(f"Could not save wav using {savename} - {err} - skipping...")
            return
        
        log.info(f"Saved wav as {savename[0]}")

    def save_result_wav(self):
        self.save_wav_dialog(self.result_wav, self.sampling_rate)

    def randomize_target(self):
        # log.info(f"Randomized target embedding to {self.target_embedding}")
        self.target_embedding = np.random.uniform(low=-.15, high=.15, size=256).astype(np.float32)
        log.info(f"Randomized target embedding to {self.target_embedding} with max: {max(self.target_embedding)}, min: {min(self.target_embedding)}")
        # exit(0)

    def pick_file(self):
        fname = QtWidgets.QFileDialog.getOpenFileName(self, 'Open file', 
                ".","Numpy speaker embedding (*.npy)")

        try:
            self.target_embedding = np.load(fname[0])
        except Exception as err:
            log.error(f"Error {err} when loading in {fname}... continuing with original embedding")
            pass
        
        log.info(f"Loaded in target embedding {self.target_embedding[[0, 1]]} ... {self.target_embedding[-2:]} with max: {max(self.target_embedding)}, min: {min(self.target_embedding)}")
    
    def play_result_wav(self):
        log.info("Trying to play converted sound!")
        if self.result_wav is not None:
            utility.play_wav_from_npy(self.result_wav)
        else:
            log.info("No converted sample found")
            return
        log.info("Done playing sound!")

    def record(self):
        #==========================Record a sample=========================
        audio = pyaudio.PyAudio()
        
        # start Recording
        stream = audio.open(format=FORMAT, channels=CHANNELS,
                        rate=self.sampling_rate, input=True,
                        frames_per_buffer=CHUNK)
        print("recording...")
        frames = []
        
        # for i in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
        #     data = stream.read(CHUNK)
        #     frames.append(data)
        data = stream.read(RECORD_SIZE_FRAMES * self.hop_size) 
        self.recorded_wav = np.frombuffer(data, np.float32)
        print("finished recording")
            

        # stop Recording
        stream.stop_stream()
        stream.close()
        audio.terminate()

    def convert(self):
        if self.recorded_wav is None:
            log.error("Error: No recorded wav to convert")
            return
        
        log.info("Now starting conversion...")

        #========================The conversion chain========================
        
        #===========================Librosa/etc audio->spect===================
        source_spect = converter._wav_to_melgan_spec(np.array(self.recorded_wav).flatten(), self.sampling_rate)                  #            1.convert recorded audio to spect
        source_spect = torch.from_numpy(source_spect[np.newaxis, :, :]).to(device)                    # (to torch)


        # source_embed = speaker_encoder(source_spect)                                                    #           2. Source spect --> source embedding
        #============================Autovc spect -> spect=================================
        


        len_pad = ceil(source_spect.size()[1]/32) * 32 - source_spect.size()[1]
        padded_source = torch.nn.functional.pad(input=source_spect, pad=(0, 0, 0, len_pad, 0, 0), mode='constant', value=0) #pad to base32 #TODO: why +1?? 
        with torch.no_grad():
            _, x_identic_psnt, _ = G(padded_source, self.source_embedding, torch.from_numpy(self.target_embedding[np.newaxis, :]).to(device))
        target_spect = x_identic_psnt[0]
        target_spect = torch.nn.functional.pad(input=target_spect, pad=(0, 0, 0, -len_pad, 0, 0), mode='constant', value=0) #pad to base32 #TODO: why +1?? 
        
        #==================VOCODER SYNTHESIS=========================
        target_audio = vocoder.synthesize(target_spect[0])
        self.result_wav = target_audio
        log.info(f"Done converting to sample of size {self.result_wav.shape}")
        # target_audio_np = target_audio[0].cpu().numpy() #load to numpy
        # while True:





if __name__ == "__main__":
    #======================Logging==========================
    logging.basicConfig(level=logging.INFO)
    
    #=======================Device==========================
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

    #=======================Arguments=======================
    parser = argparse.ArgumentParser(description='Transfer voices using pretrained AutoVC')
    # parser.add_argument("--model_path", type=str, default="./checkpoints/20210504_melgan_lencrop514_autovc_1229998.ckpt",
    #                     help="Path to trained AutoVC model")
    parser.add_argument("--model_path", type=str, default="./checkpoints/20210504_melgan_lencrop514_autovc_1229998.ckpt",
                        help="Path to trained AutoVC model")
    # parser.add_argument("--vocoder", type=str, default="griffin", choices=["griffin", "wavenet", "melgan"],
    #                     help="What vocoder to use")
    parser.add_argument("--target_embedding_path", type=str, default="./spectrograms/melgan/p226/p226_emb.npy",
                        help="What embedding to use, path to target embedding .npy file with shape: [256], source embedding is calculated dynamically")
    parser.add_argument("--source_embedding_path", type=str, default="./spectrograms/melgan/Wouter/Wouter_emb.npy",
                        help="What embedding to use, path to target embedding .npy file with shape: [256], source embedding is calculated dynamically")

    # parser.add_argument("--default_wav_path", type=str, default="./input/Wouter/6.wav")
    parser.add_argument("--default_wav_path", type=str, default="./input/this_is_a_test_sentence.wav")

    # parser.add_argument("--spectrogram_type", type=str, choices=["standard", "melgan"], default="standard",
    #                         help="What converter to use, use 'melgan' to convert wavs to 24khz fft'd spectrograms used in the parallel melgan implementation")
    args = parser.parse_args()

    #=======================Data Converter (spectrogram etc.)========================
    # if args.spectrogram_type == "standard":
    #     converter = Converter(device)
    # elif args.spectrogram_type == "melgan":
    converter = MelganConverter(device, Config.dir_paths["melgan_config_path"], Config.dir_paths["melgan_stats_path"])


    #=======================Load in spectrogram converter============================
    G = Generator(**Config.autovc_arch).eval().to(device)
    g_checkpoint = torch.load(args.model_path, map_location=device) 
    G.load_state_dict(g_checkpoint['model'])

    #=======================Load in speaker speaker encoder========================
    network_dir = Config.dir_paths["networks"]
    speaker_encoder_name = Config.pretrained_names["speaker_encoder"]
    speaker_encoder = D_VECTOR(**Config.wavenet_arch).eval().to(device)
    c_checkpoint = torch.load(os.path.join(network_dir, speaker_encoder_name), map_location=device)     

    
    new_state_dict = OrderedDict()
    for key, val in c_checkpoint['model_b'].items():
        new_key = key[7:]
        new_state_dict[new_key] = val
    speaker_encoder.load_state_dict(new_state_dict)
    
    #=======================Load in vocoder==================================

    vocoder = MelGan(device)
    try:
        with open(Config.dir_paths["melgan_config_path"]) as f:
            melgan_config = yaml.load(f, Loader=yaml.Loader)
        
        melgan_stats = hdfdict.load(Config.dir_paths["melgan_stats_path"])
    except Exception as err:
        log.error(f"Unable to load in melgan config or stats ({err})")
        exit(0)


    target_embedding = np.load(args.target_embedding_path) #load in target embedding


    source_embedding = np.load(args.source_embedding_path)
    source_embedding = torch.from_numpy(source_embedding[np.newaxis, :]).to(device)

    #========================Main loop start===========================
    log.info("Now starting application")
    # live_convert(args, device, converter, melgan_config, G, speaker_encoder, vocoder)
    import sys

    app = QtWidgets.QApplication(sys.argv)
    
    mainwin = QtWidgets.QMainWindow()
    

    voice_converter = VoiceRecoder(melgan_config, melgan_stats, device, converter, G, speaker_encoder, target_embedding, vocoder, source_embedding, default_wav_path=args.default_wav_path)

    voice_converter.show()
    app.exec_()
    log.info("Done")
