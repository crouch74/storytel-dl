import subprocess
import logging
from typing import List

logger = logging.getLogger(__name__)

def is_url(path: str) -> bool:
    """Checks if the path is a URL"""
    return path.startswith(("http://", "https://", "www."))

def format_time(seconds: float) -> str:
    """Formats seconds to HH:MM:SS.mmm"""
    ms = int((seconds % 1) * 1000)
    s = int(seconds % 60)
    m = int((seconds // 60) % 60)
    h = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def run_command(cmd: List[str], capture_output=True, text=True) -> subprocess.CompletedProcess:
    """Wrapper for subprocess.run"""
    logger.debug(f"Running command: {' '.join(cmd)}")
    try:
        res = subprocess.run(cmd, capture_output=capture_output, text=text, check=False)
        if res.returncode != 0:
            logger.debug(f"Command failed with return code {res.returncode}")
            if res.stderr:
                logger.debug(f"Stderr: {res.stderr}")
        return res
    except Exception as e:
        logger.error(f"Error running command {' '.join(cmd)}: {e}")
        # Create a dummy CompletedProcess to avoid attribute errors if caller expects one
        return subprocess.CompletedProcess(cmd, 1, "", str(e))
