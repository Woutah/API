# AutoConvert

This repository contains code for the Seminar Audio Processing and Indexing 2021 final project at Leiden University. As a part of this project, we investigate voice style transfer systems. We aim to create an easy-to-use conversion program utilising the [AutoVC](https://github.com/auspicious3000/autovc) voice conversion model.

Some audio samples are posted [here](https://woutah.github.io/AutoConvert/).

## Interface
We implemented an easy-to-use tool which can be used to generate audio  samples on-demand by inputting either `.wav`-files, or by recording these samples directly via a microphone.

The tool can be started by running

```
python record_convert.py --model_path ./path/to/melgan.ckpt --target_embedding_path ./path/to/target_emb.npy --source_embedding_path ./path/to/source_emb.npy
```

Where:

``model_path`` - The location of the trained autoVC model-checkpoint (trained on Melgan spectrograms)

``target_embedding_path`` - The (start) location of `target_embedding.npy`, target embedding can be changed dynamically

``source_embedding_path`` - The location of `source_embedding.npy`, this should be known beforehand

Running the sample results in the following menu:

<img src="./etc/gui_example2.png" width="400" />

A typical conversion process consists of:

- Recording an audio sample 
- Converting it ( source .wav &rarr; source spect &rarr; target spect &rarr; Vocoder &rarr; target .wav )
- Playing it

The results can be saved using the `save` buttons, the target embedding can be loaded dynamically by using `Load Target`, or by generating a random embedding, using the `Randomize Target Embedding` button.

## Live Conversion

The live-converter can be started using:

```
python record_convert.py --model_path ./path/to/melgan.ckpt --target_embedding_path ./path/to/target_emb.npy --source_embedding_path ./path/to/source_emb.npy
```
The arguments are the same as for the aforementation `interface` script


This script first creates a wav-buffer, which is dynamically interpreted to a target-spectrogram-buffer, this target-spectrogram-buffer is then converted back to an audio sample which is dynamically played back. 

Because both librosa and the vocoders operate better on larger sample-sizes, a buffer is built up before live-conversion is attempted, this is why there is a delay of a couple of seconds before the output can be heard. 

Conversion is real-time when ran on a Ryzen 3800x CPU. 

## Installation

Install dependencies using:

```bash
pip install -r requirements.txt
```

Install PyTorch using the command found [here](https://pytorch.org/get-started/locally/)

## Usage
### Conversion
To convert audio files, download the pretrained network weights using the instructions [here](networks/README.md). Next, place speaker audio files in the `input` folder using the following structure:

```
input
+-- speaker1
|   +-- audio1
|   |   ...
|    ...
```

Run the following command to convert a specific source audio file to sound like a target speaker.

```
python convert.py --source speaker1 --target speaker2 --source_wav audio1
```

Using the `--vocoder {"griffin", "wavenet", "melgan"}` tag, the vocoder of the framework can be adapted to any of the following:

* **WaveNet:** The default WaveNet vocoder used by the AutoVC authors. This vocoder achieves good quality with a high inference penalty.
* **Griffin-Lim:** A fast vocoder with a loss of audio quality.
* **MelGAN:** A fast vocoder with decent audio quality. The pretrained model on VCTK is downloadable [here](https://drive.google.com/drive/folders/17EkB4hSKUEDTYEne-dNHtJT724hdivn4). As this vocoder uses a different Mel-spectrogram format, use the retrained AutoVC model downloadable [here](https://drive.google.com/file/d/1VmBJ_vfYhhs0DelSLSAfLkh84MAAhor2/view?usp=sharing), by using the `--model_path <path>` flag.

### Training
To train the autovc model, use the following command:

```
python train.py --input_dir <path_to_data>
```

Where `<path_to_data>` points to a folder in the structure described [above](#conversion). Training can be continued by using the `--model_path <path_to_model>` flag where `<path_to_model>` points to an AutoVC checkpoint.

## Metadata format

### Conversion
Conversion data is converted to the intermediary `metadata.pkl` file used for converting. It consists of the following structure:

```
metadata.pkl
{
    "source" : {
        "speaker1" : {
            "emb" : <speaker_embedding []>
            "utterances" : {
                "utterance1" : [ <part1 []>, ... , <partn []> ]
                ...
            }
        }
        ...
    }
    "target" : {
        "speaker1" : {
            "emb" : <speaker_embedding []>
        }
        ...
    }
}
```

<!-- ```
metadata.pkl
|
+-- source
|   +-- speaker1
|   |   +-- emb
|   |   +-- utterances
|   |       +-- utterance1
|   |       |   +-- part1
|   |       |   |   ...    
|   |       |   ...
|   |       
|   |   ...
|   
+-- target
    +-- speaker1
    |   +-- emb
    |   ...
``` -->

### Training
For training, we follow the metadata format using by [AutoVC](https://github.com/auspicious3000/autovc). The format is as follows:

```
train.pkl
[
    ["speaker_name", <speaker_embedding []>, "utterance_file_path1", ... , "utterance_file_pathn"],
    ...

]
```

## Progress

- [x] Implement easy conversion using audio files
- [x] Split audio files into ~2 second parts for processing by AutoVC
    - [x] Investigate audio scramble 
- [x] Fix slow [WaveNet](https://github.com/r9y9/wavenet_vocoder) vocoder
- [x] Train on larger samples
- [x] Train with more speakers
