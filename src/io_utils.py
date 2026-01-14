import os
import logging
import re

def sanitize_filename(name: str) -> str:
    """
    Sanitizes a string to be safe for use as a filename.
    Removes illegal characters, collapses spaces, trims.
    """
    # Remove illegal characters (Windows/Unix commonset)
    # Windows: < > : " / \ | ? *
    # Unix: /
    # We'll just be aggressive.
    clean = re.sub(r'[<>:"/\\|?*]', '', name)
    # Collapse multiple spaces
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def ensure_directory(path: str):
    """Creates directory if it doesn't exist."""
    if not os.path.exists(path):
        os.makedirs(path)

from typing import List

def read_urls(file_path: str) -> List[str]:
    """
    Reads URLs from a text file, filtering empty lines.
    """
    if not os.path.exists(file_path):
        logging.warning(f"⚠️ Input file not found: {file_path}")
        return []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        # Filter empty lines and strip whitespace
        return [line.strip() for line in f if line.strip()]
