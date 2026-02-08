import logging
import os

# Setup a file logger
logger = logging.getLogger("debug_logger")
logger.setLevel(logging.INFO)
fh = logging.FileHandler("c:/Anti Gravity/streaming_platform/upload_debug.log")
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
fh.setFormatter(formatter)
logger.addHandler(fh)

def log(msg):
    logger.info(msg)
    print(msg) # duplicte to stdout
