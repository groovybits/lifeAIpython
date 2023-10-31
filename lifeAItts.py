#!/usr/bin/env python

## Life AI Text to Speech module
#
# Chris Kennedy 2023 (C) GPL
#
# Free to use for any use as in truly free software
# as Richard Stallman intended it to be.
#

import zmq
import argparse
from transformers import VitsModel, AutoTokenizer
import torch
import io
import soundfile as sf
from transformers import logging as trlogging
import warnings
import urllib3
import inflect
import re
import logging
import time
import traceback

warnings.simplefilter(action='ignore', category=Warning)
warnings.filterwarnings("ignore", category=urllib3.exceptions.NotOpenSSLWarning)
from urllib3.exceptions import NotOpenSSLWarning
warnings.simplefilter(action='ignore', category=NotOpenSSLWarning)
trlogging.set_verbosity_error()

def clean_text_for_tts(text):
    p = inflect.engine()

    def num_to_words(match):
        number = match.group()
        try:
            words = p.number_to_words(number)
        except inflect.NumOutOfRangeError:
            words = "[number too large]"
        return words

    text = re.sub(r'\b\d+(\.\d+)?\b', num_to_words, text)

    # Add a pause after punctuation
    text = text.replace('.', '. ')
    text = text.replace(',', ', ')
    text = text.replace('?', '? ')
    text = text.replace('!', '! ')

    return text


def main():
    while True:
        header_message = receiver.recv_json()
        """
          header_message = {
            "segment_number": segment_number,
            "mediaid": mediaid,
            "mediatype": mediatype,
            "username": username,
            "source": source,
            "message": message,
            "text": "",
        }"""
        segment_number = header_message["segment_number"]
        text = header_message["text"]

        logger.debug("Text to Speech recieved request:\n%s" % header_message)
        logger.info(f"Text to Speech: recieved text #{segment_number}\n{text}")

        inputs = tokenizer(clean_text_for_tts(text), return_tensors="pt")
        inputs['input_ids'] = inputs['input_ids'].long()

        output = None
        try:
            with torch.no_grad():
                output = model(**inputs).waveform
            waveform_np = output.squeeze().numpy().T
        except Exception as e:
            logger.error(f"{traceback.print_exc()}")
            logger.error(f"Exception: ERROR STT error with output.squeeze().numpy().T on audio: {text}")
            continue
        audiobuf = io.BytesIO()
        sf.write(audiobuf, waveform_np, model.config.sampling_rate, format='WAV')
        audiobuf.seek(0)

        duration = len(waveform_np) / model.config.sampling_rate

        # fill in the header
        header_message["duration"] = duration

        # send the header and the audio
        sender.send_json(header_message, zmq.SNDMORE)
        sender.send(audiobuf.getvalue())
        
        logger.debug(f"Text to Speech: sent audio #{segment_number}\n{header_message}")
        logger.info(f"Text to Speech: sent audio #{segment_number} of {duration} duration. {text}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_port", type=int, default=2000, required=False, help="Port for receiving text input")
    parser.add_argument("--output_port", type=int, default=2001, required=False, help="Port for sending audio output")
    parser.add_argument("--target_lang", type=str, default="eng", help="Target language")
    parser.add_argument("--source_lang", type=str, default="eng", help="Source language")
    parser.add_argument("--audio_format", choices=["wav", "raw"], default="raw", help="Audio format to save as. Choices are 'wav' or 'raw'.")
    parser.add_argument("--input_host", type=str, default="127.0.0.1", required=False, help="Port for receiving text input")
    parser.add_argument("--output_host", type=str, default="127.0.0.1", required=False, help="Port for sending audio output")
    parser.add_argument("--metal", action="store_true", default=False, help="offload to metal mps GPU")
    parser.add_argument("--cuda", action="store_true", default=False, help="offload to metal cuda GPU")
    parser.add_argument("-ll", "--loglevel", type=str, default="info", help="Logging level: debug, info...")

    args = parser.parse_args()

    LOGLEVEL = logging.INFO

    if args.loglevel == "info":
        LOGLEVEL = logging.INFO
    elif args.loglevel == "debug":
        LOGLEVEL = logging.DEBUG
    elif args.loglevel == "warning":
        LOGLEVEL = logging.WARNING
    else:
        LOGLEVEL = logging.INFO

    log_id = time.strftime("%Y%m%d-%H%M%S")
    logging.basicConfig(filename=f"logs/tts-{log_id}.log", level=LOGLEVEL)
    logger = logging.getLogger('GAIB')

    ch = logging.StreamHandler()
    ch.setLevel(LOGLEVEL)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    context = zmq.Context()
    receiver = context.socket(zmq.SUB)
    print("connected to ZMQ in: %s:%d" % (args.input_host, args.input_port))
    receiver.connect(f"tcp://{args.input_host}:{args.input_port}")
    receiver.setsockopt_string(zmq.SUBSCRIBE, "")

    sender = context.socket(zmq.PUB)
    print("binded to ZMQ out: %s:%d" % (args.output_host, args.output_port))
    sender.bind(f"tcp://{args.output_host}:{args.output_port}")

    model = VitsModel.from_pretrained("facebook/mms-tts-eng")
    tokenizer = AutoTokenizer.from_pretrained("facebook/mms-tts-eng")

    if args.metal:
        model.to("mps")
    elif args.cuda:
        model.to("cuda")
    else:
        model.to("cpu")

    main()

