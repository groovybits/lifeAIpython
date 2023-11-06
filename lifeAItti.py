#!/usr/bin/env python

## Life AI Stable Diffusion module
#
# Chris Kennedy 2023 (C) GPL
#
# Free to use for any use as in truly free software
# as Richard Stallman intended it to be.
#

import zmq
import argparse
import io

from diffusers import StableDiffusionPipeline
import torch
from transformers import logging as trlogging
import re
import logging
import time

trlogging.set_verbosity_error()

def clean_text(text):
    # Remove URLs
    text = re.sub(r'http[s]?://\S+', '', text)
    
    # Remove image tags or Markdown image syntax
    text = re.sub(r'\!\[.*?\]\(.*?\)', '', text)
    text = re.sub(r'<img.*?>', '', text)
    
    # Remove HTML tags
    text = re.sub(r'<.*?>', '', text)
    
    # Remove any inline code blocks
    text = re.sub(r'`.*?`', '', text)
    
    # Remove any block code segments
    text = re.sub(r'```.*?```', '', text, flags=re.DOTALL)
    
    # Remove special characters and digits (optional, be cautious)
    text = re.sub(r'[^a-zA-Z0-9\s.?,!\n]', '', text)
    
    # Remove extra whitespace
    text = ' '.join(text.split())
    return text

def main():
    last_image = None
    retry = False
    latency = 0
    max_latency = args.max_latency
    throttle = False
    header_message = None
    while True:
        if throttle:
            start = time.time()
            combine_time = max(0, (latency / 1000) - max_latency)

            # read and combine the messages for 60 seconds into a single message
            while time.time() - start < combine_time:
                header_message = receiver.recv_json()
                header_message["stream"] = "image"

                sender.send_json(header_message, zmq.SNDMORE)
                sender.send(last_image)

            logger.info(f"TTM: Throttling for {combine_time} seconds.")

        # Receive a message
        if retry:
            logger.error(f"Retrying...")
            retry = False
        else:
            header_message = receiver.recv_json()

        # get variables from header
        segment_number = header_message["segment_number"]
        optimized_prompt = ""
        if "optimized_text" in header_message:
            optimized_prompt = header_message["optimized_text"]
        else:
            optimized_prompt = header_message["text"]
            logger.error(f"TTI: No optimized text, using original text.")

        # Clean text
        optimized_prompt = clean_text(optimized_prompt[:300])

        logger.debug(f"Text to Image recieved optimized prompt:\n{header_message}.")
        logger.info(f"Text to Image recieved text #{segment_number}:\n - {optimized_prompt}")

        image = None
        if args.latency == 0 or last_image == None or time.time() - header_message["timestamp"] <= args.latency:
            # 2. Forward embeddings and negative embeddings through text encoder
            if args.extend_prompt:
                max_length = pipe.tokenizer.model_max_length

                # 3. Forward
                input_ids = pipe.tokenizer(optimized_prompt, return_tensors="pt").input_ids
                input_ids = input_ids.to("mps")

                negative_ids = pipe.tokenizer("", truncation=False, padding="max_length", max_length=input_ids.shape[-1], return_tensors="pt").input_ids                                                                                                     
                negative_ids = negative_ids.to("mps")

                concat_embeds = []
                neg_embeds = []
                for i in range(0, input_ids.shape[-1], max_length):
                    concat_embeds.append(pipe.text_encoder(input_ids[:, i: i + max_length])[0])
                    neg_embeds.append(pipe.text_encoder(negative_ids[:, i: i + max_length])[0])

                prompt_embeds = torch.cat(concat_embeds, dim=1)
                negative_prompt_embeds = torch.cat(neg_embeds, dim=1)

                image = pipe(prompt_embeds=prompt_embeds, negative_prompt_embeds=negative_prompt_embeds).images[0]
            else:
                image = pipe(clean_text(optimized_prompt)).images[0]

            # Convert PIL Image to bytes
            img_byte_arr = io.BytesIO()
            image.save(img_byte_arr, format='PNG')  # Save it as PNG or JPEG depending on your preference
            image = img_byte_arr.getvalue()

            # check if image is more than 75k
            if len(image) < 75000:
                logger.error(f"Image is too small, retrying...")
                retry = True
                continue

            last_image = image

        header_message["stream"] = "image"

        sender.send_json(header_message, zmq.SNDMORE)
        sender.send(last_image)

        logger.info(f"Text to Image sent image #{segment_number} {header_message['timestamp']} of {len(last_image)} bytes.")

        # measure latency and see if we need to throttle output
        latency = round(time.time() * 1000) - header_message['timestamp']
        if latency > (max_latency * 1000):
            logger.error(f"TTM: Message is too old {latency/1000}, throttling for the next{latency/1000} seconds.")
            throttle = True

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_port", type=int, default=3001, required=False, help="Port for receiving text input")
    parser.add_argument("--output_port", type=int, default=6002, required=False, help="Port for sending image output")
    parser.add_argument("--input_host", type=str, default="127.0.0.1", required=False, help="Port for receiving text input")
    parser.add_argument("--output_host", type=str, default="127.0.0.1", required=False, help="Port for sending image output")
    parser.add_argument("--nsfw", action="store_true", default=False, help="Disable NSFW filters, caution!!!")
    parser.add_argument("--metal", action="store_true", default=False, help="offload to metal mps GPU")
    parser.add_argument("--cuda", action="store_true", default=False, help="offload to metal cuda GPU")
    parser.add_argument("-ll", "--loglevel", type=str, default="info", help="Logging level: debug, info...")
    parser.add_argument("-m", "--model", type=str, default="runwayml/stable-diffusion-v1-5", help="Model ID to use")
    parser.add_argument("--latency", type=int, default=0, help="Latency in seconds to wait for a message")
    parser.add_argument("--extend_prompt", action="store_true", help="Extend prompt past 77 token limit.")
    parser.add_argument("--max_latency", type=int, default=10, help="Max latency for messages before they are throttled / combined")

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
    logging.basicConfig(filename=f"logs/tti-{log_id}.log", level=LOGLEVEL)
    logger = logging.getLogger('TTI')

    ch = logging.StreamHandler()
    ch.setLevel(LOGLEVEL)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    model_id = args.model

    ## Disable NSFW filters
    pipe = None
    if args.nsfw:
        pipe = StableDiffusionPipeline.from_pretrained(model_id,
                                                        torch_dtype=torch.float16,
                                                        safety_checker = None,
                                                        requires_safety_checker = False)
    else:
        pipe = StableDiffusionPipeline.from_pretrained(model_id, torch_dtype=torch.float16)

    ## Offload to GPU Metal
    if args.metal:
        pipe = pipe.to("mps")
    elif args.cuda:
        pipe = pipe.to("cuda")
    else:
        pipe = pipe.to("mps")

    context = zmq.Context()
    receiver = context.socket(zmq.SUB)
    logger.info("connected to ZMQ in: %s:%d" % (args.input_host, args.input_port))
    receiver.connect(f"tcp://{args.input_host}:{args.input_port}")
    receiver.setsockopt_string(zmq.SUBSCRIBE, "")

    sender = context.socket(zmq.PUSH)
    logger.info("binded to ZMQ out: %s:%d" % (args.output_host, args.output_port))
    sender.connect(f"tcp://{args.output_host}:{args.output_port}")
    main()

