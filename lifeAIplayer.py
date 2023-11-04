#!/usr/bin/env python

## Life AI Player ZMQ client
#
# Chris Kennedy 2023 (C) GPL
#
# Free to use for any use as in truly free software
# as Richard Stallman intended it to be.
#

import io
import zmq
import argparse
import soundfile as sf
from PIL import Image
import re
import os
import cv2
import numpy as np
import logging
import time
import soundfile as sf
import pygame
import queue
import threading
from queue import PriorityQueue
from PIL import Image, ImageDraw, ImageFont
import cv2
import textwrap
import json
from collections import deque
from pydub import AudioSegment

# Queue to store the last images
past_images_queue = deque(maxlen=8)  # Assuming 6 images for each side

def create_16_9_image(center_image, side_images, target_width, target_height):
    # Scale the main image to fit the height of the 16:9 image
    main_image_scaled = center_image.resize((target_height, target_height), Image.LANCZOS)

    # Create a new image with the target 16:9 dimensions
    final_image = Image.new('RGB', (target_width, target_height))

    # Calculate the total width of the side images (on one side)
    side_width_total = (target_width - target_height) // 2

    # Resize side images to 2/3 of their original 512x512 size
    small_side_size = int(512 * 2 / 3)
    resized_side_images = [img.resize((small_side_size, small_side_size), Image.LANCZOS) for img in side_images]

    # Calculate the number of small images that can fit on each side
    # This assumes that you can fit 3 images stacked vertically
    num_side_images = 3

    # Paste the side images to fill the sides
    for i in range(num_side_images):
        # Calculate the vertical position for each small image
        y_position = i * small_side_size

        # Paste on the left side
        final_image.paste(resized_side_images[i], (0, y_position))

        # Paste on the right side
        final_image.paste(resized_side_images[i], (target_width - small_side_size, y_position))

    # Paste the scaled main image in the center
    final_image.paste(main_image_scaled, (side_width_total, 0))

    return final_image

def create_16_9_nonlinear_image(center_image, side_images, target_width, target_height):
    # Scale the main image to fit the height of the 16:9 image
    main_image_scaled = center_image.resize((target_height, target_height), Image.LANCZOS)

    # Create a new image with the target 16:9 dimensions
    final_image = Image.new('RGB', (target_width, target_height))

    # Calculate the total width of the side images (on one side)
    side_width_total = (target_width - target_height) // 2

    # Paste the side images to fill the sides
    for index, side_image in enumerate(side_images):
        # Calculate the position of each side image (3 on each side)
        x_position = (index % 3) * side_image.width if index < 6 else target_width - (index % 3 + 1) * side_image.width
        y_position = (index // 6) * side_image.height

        # Paste the side image into the final image
        final_image.paste(side_image, (x_position, y_position))

    # Paste the scaled main image in the center
    final_image.paste(main_image_scaled, (side_width_total, 0))

    return final_image

def create_filmstrip_middle_image(center_image, side_images):
    # Assuming side_images is a list of 6 images, 3 for left and 3 for right
    left_images = side_images[:3]
    right_images = side_images[3:]
    
    # Combine the left images, the center image, and the right images horizontally
    images_to_combine = left_images + [center_image] + right_images
    combined_width = sum(img.size[0] for img in images_to_combine)
    combined_height = max(img.size[1] for img in images_to_combine)

    # Create a new image with the combined dimensions
    wide_image = Image.new('RGB', (combined_width, combined_height))

    # Paste the images into the wide_image
    x_offset = 0
    for img in images_to_combine:
        wide_image.paste(img, (x_offset, 0))
        x_offset += img.size[0]
    
    return wide_image

# Main function to process the new image
def process_new_image(new_image, text, args):
    target_width = args.width  # This should be set to the desired width for 16:9 aspect ratio
    target_height = args.height  # This should be set to the height corresponding to the 16:9 aspect ratio
    
    # Check if we have enough images to fill the sides
    if len(past_images_queue) >= 8:
        # Use the 6 most recent images for each side
        side_images = list(past_images_queue)
        final_image = create_16_9_image(new_image, side_images, target_width, target_height)
        final_image = add_text_to_image(final_image, text)
    else:
        # Not enough images, just add text to the new_image
        final_image = add_text_to_image(new_image, text)

    # Add the new image to the queue for future use
    past_images_queue.appendleft(new_image)

    return final_image

## Japanese writing on images
def draw_japanese_text_on_image(image_np, text, position, font_path, font_size):
    # Convert to a PIL Image
    image_pil = Image.fromarray(cv2.cvtColor(image_np, cv2.COLOR_BGR2RGB))

    # Prepare drawing context
    draw = ImageDraw.Draw(image_pil)
    font = ImageFont.truetype(font_path, font_size)

    # Define the border width for the text
    border_width = 5

    # Get text size using getbbox
    x, y = position
    bbox = font.getbbox(text)
    text_width, text_height = bbox[2], bbox[3]
    y = y - text_height
    x = x + text_width / 2

    # Draw text border (outline)
    for i in range(-border_width, border_width + 1):
        for j in range(-border_width, border_width + 1):
            draw.text((x + i, y + j), text, font=font, fill=(0, 0, 0))  # Black border

    # Draw text on image
    draw.text((x, y), text, font=font, fill=(255, 255, 255))  # White fill

    # Convert back to NumPy array
    image_np = cv2.cvtColor(np.array(image_pil), cv2.COLOR_RGB2BGR)

    return image_np

def add_text_to_image(image, text):
    if image is not None:
        logger.info(f"Adding text to image: {text}")

        # Maintain aspect ratio and add black bars
        width, height = image.size
        desired_ratio = width / height
        current_ratio = width / height

        # Convert the PIL Image to a NumPy array for OpenCV operations
        image = np.array(image)
        image = cv2.cvtColor(image, cv2.COLOR_RGB2BGR)  # Convert from RGB to BGR for OpenCV

        if current_ratio > desired_ratio:
            new_width = int(height * desired_ratio)
            padding = max(0, (new_width - width) // 2)
            image = cv2.copyMakeBorder(image, 0, 0, padding, padding, cv2.BORDER_CONSTANT, value=[0, 0, 0])
        else:
            new_height = int(width / desired_ratio)
            padding = max(0, (new_height - height) // 2)
            image = cv2.copyMakeBorder(image, padding, padding, 0, 0, cv2.BORDER_CONSTANT, value=[0, 0, 0])

        # Resize to the desired resolution
        # Calculate the scaling factors
        x_scale = args.width / image.shape[1]
        y_scale = args.height / image.shape[0]
        scale_factor = min(x_scale, y_scale)

        # Compute new width and height while maintaining the aspect ratio
        new_width = int(image.shape[1] * scale_factor)
        new_height = int(image.shape[0] * scale_factor)

        # Resize the image
        image = cv2.resize(image, (new_width, new_height), interpolation=cv2.INTER_LINEAR)

        # If the resized image doesn't match the desired resolution, pad with black
        if new_width != args.width or new_height != args.height:
            top_padding = (args.height - new_height) // 2
            bottom_padding = args.height - new_height - top_padding
            left_padding = (args.width - new_width) // 2
            right_padding = args.width - new_width - left_padding
            image = cv2.copyMakeBorder(image, top_padding, bottom_padding, left_padding, right_padding, cv2.BORDER_CONSTANT, value=[0, 0, 0])

        width, height = image.shape[1], image.shape[0]
        current_ratio = width / height

        def contains_japanese(text):
            for char in text:
                if any([start <= ord(char) <= end for start, end in [
                    (0x3040, 0x309F),  # Hiragana
                    (0x30A0, 0x30FF),  # Katakana
                    (0x4E00, 0x9FFF),  # Kanji
                    (0x3400, 0x4DBF)   # Kanji (extension A)
                ]]):
                    return True
            return False

        wrap_width = 30
        is_wide = False
        if current_ratio > 512/512:
            wrap_width = 45
            is_wide = True
        wrapped_text = textwrap.wrap(text, width=wrap_width, fix_sentence_endings=False, break_long_words=False, break_on_hyphens=False)  # Adjusted width
        y_pos = height - 40  # Adjusted height from bottom

        font_size = 1
        font_thickness = 2  # Adjusted for bolder font
        border_thickness = 8  # Adjusted for bolder border

        if is_wide:
            font_size = 2
            font_thickness = 4
            border_thickness = 15
        elif width < 600:  # Assuming smaller images have widths less than 600, adjust if necessary
            font_size = 1
            font_thickness = 3
            border_thickness = 10

        for line in reversed(wrapped_text):
            text_width, _ = cv2.getTextSize(line, cv2.FONT_HERSHEY_DUPLEX, font_size, font_thickness)[0]
            x_pos = (width - text_width) // 2  # Center the text
            if contains_japanese(line):
                image = draw_japanese_text_on_image(image, line, (x_pos, y_pos), args.japanesefont,60)
            else:
                cv2.putText(image, line, (x_pos, y_pos), cv2.FONT_HERSHEY_DUPLEX, font_size, (0, 0, 0), border_thickness)
                cv2.putText(image, line, (x_pos, y_pos), cv2.FONT_HERSHEY_DUPLEX, font_size, (255, 255, 255), font_thickness)
            y_pos -= 60

        ## Convert back from numpy array
        image = Image.fromarray(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    return image  # returning the modified image

def play_audio(audio_samples, pygame_player):  
    audiobuf = io.BytesIO(audio_samples)
    if audiobuf:
        ## Speak WAV TTS Output using pygame
        pygame_player.mixer.music.load(audiobuf)
        pygame_player.mixer.music.play()
        while pygame_player.mixer.music.get_busy():
            pygame_player.time.Clock().tick(10)

def image_to_ascii(image):
    image = image.resize((args.width, int((image.height/image.width) * args.width * 0.55)), Image.LANCZOS)
    image = image.convert('L')  # Convert to grayscale

    pixels = list(image.getdata())
    ascii_chars = ["@", "#", "S", "%", "?", "*", "+", ";", ":", ",", "."]
    ascii_image = [ascii_chars[pixel//25] for pixel in pixels]
    ascii_image = ''.join([''.join(ascii_image[i:i+args.width]) + '\n' for i in range(0, len(ascii_image), args.width)])
    return ascii_image

def render(image):
    # Convert PIL Image to NumPy array
    image_np = np.array(image)

    # Convert RGB to BGR (OpenCV uses BGR format)
    image_bgr = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

    cv2.imshow('GAIB The Groovy AI Bot', image_bgr)

    k = cv2.waitKey(10)
    if k == ord('f'):
        cv2.setWindowProperty('GAIB The Groovy AI Bot', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    elif k == ord('m'):
        cv2.setWindowProperty('GAIB The Groovy AI Bot', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
    elif k == ord('q') or k == 27:
        cv2.destroyAllWindows()

def save_json(header, mediaid):
    assets_dir = "assets"
    os.makedirs(assets_dir, exist_ok=True)
    with open(f"{assets_dir}/{mediaid}.json", 'w') as json_file:
        json.dump(header, json_file, indent=4)

def save_asset(asset, mediaid, segment_number, asset_type):
    directory = f"{asset_type}/{mediaid}"
    os.makedirs(directory, exist_ok=True)
    file_path = f"{directory}/{segment_number}"

    if asset_type == "audio":
        file_path += ".wav"
        with open(file_path, 'wb') as file:
            file.write(asset)
    elif asset_type == "images":
        file_path += ".png"
        img_byte_arr = io.BytesIO()
        asset.save(img_byte_arr, format="PNG")  # Save it as PNG or JPEG depending on your preference
        asset = img_byte_arr.getvalue()

        with open(file_path, 'wb') as f:
            f.write(asset)
    elif asset_type == "music":
        file_path += ".wav"
        with open(file_path, 'wb') as file:
            file.write(asset)

class BackgroundMusic(threading.Thread):
    def __init__(self):
        super().__init__()
        self.pygame = pygame
        self.pygame.mixer.init(frequency=32000, size=-16, channels=1, buffer=1024)
        self.pygame.init()
        self.audio_buffer = None
        self.running = True
        self.lock = threading.Lock()  # Lock to synchronize access to audio_buffer

    def run(self):
        while self.running:
            with self.lock:
                if self.audio_buffer:
                    self.play_audio(self.audio_buffer)
                    self.audio_buffer = None  # Reset audio_buffer to prevent replaying the same buffer
            self.pygame.time.Clock().tick(1)  # Limit the while loop to 1 iteration per second

    def get_audio_duration(audio_samples):
        audio_segment = AudioSegment.from_file(io.BytesIO(audio_samples), format="wav")
        duration_ms = len(audio_segment)  # Duration in milliseconds
        duration_s = duration_ms / 1000.0  # Convert to seconds
        return duration_s

    def play_audio(self, audio_samples):
        audiobuf = io.BytesIO(audio_samples)
        duration = self.get_audio_duration(audio_samples)
        if audiobuf:
            try:
                self.pygame.mixer.music.load(audiobuf)
                #self.pygame.mixer.music.set_volume(args.volume)  # Set the volume
                self.pygame.mixer.music.play(-1)  # -1 instructs Pygame to loop the audio indefinitely
                #while self.pygame.mixer.music.get_busy():
                #    self.pygame.time.Clock().tick(10)
                #time.sleep(duration)
            except Exception as e:
                logger.error(f"Error playing audio: {e}")

    def change_track(self, audio):
        with self.lock:
            try:
                self.pygame.mixer.music.stop()  # Stop the currently playing audio
                self.audio_buffer = audio
            except Exception as e:
                logger.error(f"Error changing track: {e}")

    def stop(self):
        self.running = False
        self.pygame.mixer.music.stop()

def playback(image, audio, pygame_player):
    # play both audio and display image with audio blocking till finished
    render(image)
    play_audio(audio, pygame_player)

def main():
    ## Main routine
    pygame_speek = pygame
    pygame_speek.mixer.init(frequency=22500, size=-16, channels=1, buffer=1024)
    pygame_speek.init()

    last_image_header = None
    last_image_segment = None

    # Instantiate and start the background music thread
    bg_music = BackgroundMusic()
    bg_music.start()

    while True:
        header_message = socket.recv_json()

        segment_number = header_message["segment_number"]
        timestamp = header_message["timestamp"]
        mediaid = header_message["mediaid"]
        
        message = header_message["message"]
        text = header_message["text"]
        
        optimized_prompt = text
        if 'optimized_text' in header_message:
            optimized_prompt = header_message["optimized_text"]

        type = header_message["stream"]
        if type == "music":
            # Now, receive the binary audio data
            music = socket.recv()

            # Print the header
            print(f"Received music segment {type} #{segment_number} {timestamp}: {mediaid} {len(text)} characters")
            
            save_json(message, mediaid)  # or image_message, if it's the one to be saved

            # Save audio asset
            save_asset(music, mediaid, segment_number, "music")
        
            # queue the header and music together
            bg_music.change_track(music)

        if type == "speek":
            # Now, receive the binary audio data
            audio = socket.recv()

            # Print the header
            print(f"Received audio segment {type} #{segment_number} {timestamp}: {mediaid} {len(text)} characters")

            # queue the header and audio together
            audio_buffer.put((header_message, audio))

        ## Image
        if type == "image":
            # Now, receive the binary audio data
            image = socket.recv()

            # Print the header
            print(f"Received image segment {type} #{segment_number} {timestamp}: {mediaid} {len(text)} characters")

            try:
                # Convert the bytes back to a PIL Image object
                image = Image.open(io.BytesIO(image))

                print(f"Image Prompt: {optimized_prompt}\Original Text: {text}\nOriginal Question:{message}")

                # queue the header and image together
                image_buffer.put((header_message, image))
            except Exception as e:
                logger.error(f"Error converting image to ascii: {e}")

        ## get an audio sample and header, get the text field from it, then get an image and header and burn in the text from the audio header to the image and render it while playing the audio
        if not audio_buffer.empty() and (not image_buffer.empty() or last_image_header is not None):
            audio_message, audio_asset = audio_buffer.get()
            image_message = None
            image_asset = None
            if last_image_header is not None:
                image_message = last_image_header
                image_asset = last_image_segment
                last_image_header = None
                last_image_segment = None
            else:
                image_message, image_asset = image_buffer.get()

            text = audio_message["text"]
            optimized_prompt = text
            if 'optimized_text' in audio_message:
                optimized_prompt = audio_message["optimized_text"]

            if audio_message['timestamp'] < image_message['timestamp']:
                logger.info(f"Audio segment #{audio_message['segment_number']} is older than image segment #{image_message['segment_number']}, dropping audio segment.")
                #continue

            if audio_message['timestamp'] > image_message['timestamp']:
                logger.info(f"Audio segment #{audio_message['segment_number']} is newer than image segment #{image_message['segment_number']}, dropping image segment.")
                #continue

            # Convert the PIL Image to a NumPy array for OpenCV operations
            image_np = np.array(image)
            image_np = cv2.cvtColor(image_np, cv2.COLOR_RGB2BGR)

            if args.burn_prompt:
                #image_np = add_text_to_image(image_asset, optimized_prompt)
                image_np = process_new_image(image_asset, optimized_prompt)
            else:
                #image_np = add_text_to_image(image_asset, text)
                image_np = process_new_image(image_asset, text, args)


            ## write out json into a directory assets/{mediaid}.json with it pretty pretty printed, 
            ## write out assets to file locations audio/ and images/ as mediaid/segment_number.wav 
            ## and mediaid/segment_number.png too.
            ## audio_message and image_message are the headers, image_np and audio_asset are the assets
            # Save JSON header
            save_json(audio_message, mediaid)  # or image_message, if it's the one to be saved

            # Save audio asset
            save_asset(audio_asset, mediaid, segment_number, "audio")

            # Save image asset
            save_asset(image_np, mediaid, segment_number, "images")

            # Play audio and display image
            playback(image_np, audio_asset, pygame_speek)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--input_port", type=int, required=False, default=6003, help="Port for receiving image as PIL numpy arrays")
    parser.add_argument("--input_host", type=str, required=False, default="127.0.0.1", help="Host for receiving image as PIL numpy arrays")
    parser.add_argument("-ll", "--loglevel", type=str, default="info", help="Logging level: debug, info...")
    parser.add_argument("-f", "--freq", type=int, default=22050, help="Sampling frequency for audio playback")
    parser.add_argument("-c", "--channels", type=int, default=1, help="Number of channels for audio playback")
    parser.add_argument("--burn_prompt", action="store_true", default=False, help="Burn in the prompt that created the image")
    parser.add_argument("--width", type=int, default=1920, help="Width of the output image")
    parser.add_argument("--height", type=int, default=1080, help="Height of the output image")
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
    logging.basicConfig(filename=f"logs/lifeAIplayer-{log_id}.log", level=LOGLEVEL)
    logger = logging.getLogger('lifeAIplayer')

    ch = logging.StreamHandler()
    ch.setLevel(LOGLEVEL)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    context = zmq.Context()
    socket = context.socket(zmq.SUB)
    logger.info("connected to ZMQ in: %s:%d" % (args.input_host, args.input_port))
    socket.connect(f"tcp://{args.input_host}:{args.input_port}")
    socket.setsockopt_string(zmq.SUBSCRIBE, "")

    audio_buffer = queue.Queue()
    image_buffer = queue.Queue()

    main()

