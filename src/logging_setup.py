import logging
import sys

def setup_logging(debug: bool = False):
    """
    Configures the root logger to print to stdout with emoji prefixes.
    :param debug: If True, set level to DEBUG, else INFO.
    """
    level = logging.DEBUG if debug else logging.INFO
    
    # Custom formatter to handle the requirement of keeping the message clean,
    # but strictly speaking we just want the message format to be simple.
    # The user requested: "all log messages must start with an emoji relevant to the topic...
    # timestamp... provide both info and debug logs".
    
    # Format: [TIMESTAMP] [LEVEL] MESSAGE
    # The message itself is expected to start with an emoji from the caller.
    
    formatter = logging.Formatter(
        fmt='[%(asctime)s] %(message)s',
        datefmt='%H:%M:%S'
    )
    
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    
    # Clear existing handlers to avoid duplicates if called multiple times
    if root_logger.hasHandlers():
        root_logger.handlers.clear()
        
    root_logger.addHandler(handler)
