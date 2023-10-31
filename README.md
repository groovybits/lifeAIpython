# Life AI - Bring your words to life using AI

Mudular python processes using zeromq to communicate between them. This allows mutiple chat models together and mixing of them into a mixer and out to twitch or where ever with ffmpeg/rtmp or anything ffmpeg can do. the nice part is using ffmpeg and packing audio/video into rtmp directly without OBS, and avoid all the overhead of need to decode it locally for broadcasting/streaming 😉.

Can build out endless prompt injection sources, news/twitch/voice-whisper listener/commandline/javascript web interface (that could have the video stream back and shared like youtube).

That’s the goal, you’ll see I am listing the parts as I build them, sort of have the core with llm/tts/stableDiffusion done + image subtitle burn in and prompt groomer for image gen, and generic for music usage (adding music tomorrow). twitch should be easy, I am parting out the parts of the consciousChat <https://github.com/groovybits/consciousChat> that seems more of a poc and experiment, nice, but this will remove the overhead and monolith design. It started to become too much to deal with putting it all into one app and threading everything. now each of these modules/programs are easy to understand for anyone and bypass python threading limitaitons.

## This uses the following models from huggingface

- <https://huggingface.co/facebook/mms-tts-eng> Facebook mms-tts-eng a model that is multilingual for TTS
- <https://huggingface.co/TheBloke/zephyr-7B-alpha-GGUF> A 7B parameter GPT-like model fine-tuned on a mix of publicly available, synthetic datasets.
- <https://huggingface.co/runwayml/stable-diffusion-v1-5> Stable Diffusion 1.5
- <https://huggingface.co/facebook/musicgen-small> Facebook MusicGen Music generation model
- <https://github.com/MycroftAI/mimic3> Mimic3 Text to Speech (optionally in place of Facebook mms-tts-eng).
- <https://github.com/ggerganov/llama.cpp/tree/master/examples/server> llama.cpp (install and run server for API access locally)

## modules

- [ZMQ Text Client](zmqTextClient.py) Send text into lifeAI for simulation seeding.
- [ZMQ News Client](lifeAInewsCast.py) Send news feeds into lifeAI for simulation seeding.
- [ZMQ Twitch Chat](lifeAItwitchChat.py) Twitch Chat sent to lifeAI for responses.
- [ZMQ Twitch Stream](lifeAITwitchStream.py) Twitch RTMP directly stream and avoid desktop capture.
- [ZMQ TTS Listener](zmqTTSlisten.py) Listen for TTS Audio WAV file output.
- [ZMQ TTM Listener](zmqTTMlisten.py) Listen for TTM Audio WAV file output.
- [ZMQ TTI Listener](zmqTTIlisten.py) Listen for TTI Image PIL file output.
- [Text to AI Speech](lifeAItts.py)   Facebook MMS-TTS Text to Speech Conversion.
- [Text to AI Music](lifeAIttm.py)    Facebook Music Generation.
- [Text to AI Image](lifeAItti.py)    Stable Diffusion Text to Image Generation.
- [Prompt Optimizer](lifeAIpromptOptimizer.py) Optimize prompt or turn text into a prompt.
- [Subtitle Burner](lifeAIsubTitleBurnIn.py) Burn-In subtitles in Anime style white/black bold.

## Installation

```text
# Create a virtual environment (type `deactivate` to exit it)
cd lifeAIpython
python3 -m venv lifeAI
source lifeAI/bin/activate

# Upgrade pip in venv
pip install --upgrade pip

# Install dependencies
pip install -r requirements.txt

# Python Twitch Stream
git clone https://github.com/317070/python-twitch-stream.git
cd python-twitch-stream
pip install .

# Install Mimic3 TTS in place of FB TTS-MMS (requires Python 3.11 from Brew on MacOS X)
# Use lifeAIttsMimic3.py instead of lifeAItts.py
git clone https://github.com/MycroftAI/mimic3.git
cd mimic3/
PYTHON=python3.11 make install
source .venv/bin/activate
mimic3-server # (API Server)
curl -X POST --data 'Hello world.' --output - localhost:59125/api/tts > out.wav

# Get and install llama.cpp
git clone https://github.com/ggerganov/llama.cpp.git
cd llama.cpp
cmake .
make
sudo make install
cd examples/server/
server -m /Volumes/BrahmaSSD/LLM/models/GGUF/zephyr-7b-beta.Q8_0.gguf -t 60 -c 0 --mlock
```

## Running lifeAI

```text
# Run llama.cpp server for localhost API server and llama.cpp LLM handling
server -m /Volumes/BrahmaSSD/LLM/models/GGUF/zephyr-7b-beta.Q8_0.gguf -t 60 -c 0 --mlock

# Test llama.cpp API
curl --request POST --url http://127.0.0.1:8080/completion  \
             --header "Content-Type: application/json" \
             --data '{"prompt": "Building a website can be done in 10 simple steps:","n_predict": 128}'

# ZMQ input Client to send messages through the pipeline for testing
./zmqTextClient.py --message "An apple on a laptop." --segment_number 1 --username "User"

# ZMQ Twitch input Client
./lifeAItwitchClient.py

# ZMQ News feed Client Mediastack (Coming soon)

# ZMQ Whisper speech to text Client (Coming soon)

# LLM Text track
./lifeAIllm.py

# TTS Speech audio
## ./lifeAItts.py # Easier to use, doesn't voice words properly
./lifeAIttsMimic3.py # pretty good local model

# TTI Images for video stream frames
./lifeAItti.py

# Prompt Optimizer for image and other media generation
./lifeAIpromptOptimization.py

# Subtitle Burn In for image subtitles hardsubs
./lifeAIsubTitleBurnIn.py

# Music generation
./lifeAIpromptOptimize.py --input_port 2000 --output_port 4001 --qprompt MusicDescription --aprompt MusicPrompt --topic 'music generation'
./lifeAIttm.py
./zmqTTMlisten.py --save_file

# Muxer and Frame Sync frontend (TODO)
./lifeAIframeSync.py (times all the streams for RTMP audio and video sync with everything timed together)

# ZMQ listener clients for listening, probing and viewing ascii image output
## Stored in audio/ and images/ as wav and png files with burn-in with filename
## metadata inclusion and episode_id, index, prompt string
./zmqTTSlisten.py
./zmqTTMlisten.py
./zmqTTIlisten.py

# Twitch RTMP direct stream without desktop OBS/capture overhead
./lifeAItwitchServe.py

# YouTube direct stream (TODO)

##
```

## Chris Kennedy (C) 2023 GPL free as in free software, use at your own risk. Do not believe anything the LLM generates without your own validation. We are not responsible for how you use this software.
