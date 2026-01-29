import os
import logging
import re
from typing import List, Dict, Any, Optional
from .utils import run_command

logger = logging.getLogger(__name__)

def get_audio_duration(file_path: str) -> float:
    """Gets audio duration in seconds using ffprobe"""
    cmd = [
        "ffprobe", "-v", "error", "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1", file_path
    ]
    res = run_command(cmd)
    try:
        duration = float(res.stdout.strip())
        logger.debug(f"Audio duration for {file_path}: {duration}s")
        return duration
    except (ValueError, AttributeError):
        logger.debug(f"Could not get duration for {file_path}")
        return 0.0

def detect_silence(file_path: str, noise_threshold: int = -30, duration: float = 2.0) -> List[Dict[str, Any]]:
    """Detects silence in audio to find potential chapter boundaries"""
    logger.info(f"🔍 Analyzing audio for silence (threshold: {noise_threshold}dB, duration: {duration}s)...")
    
    # ffprobe -i input -af silencedetect=n=-30dB:d=2 -f null -
    cmd = [
        "ffmpeg", "-i", file_path, "-af", f"silencedetect=n={noise_threshold}dB:d={duration}",
        "-f", "null", "-"
    ]
    res = run_command(cmd, capture_output=True, text=True)
    
    # Output is in stderr
    output = res.stderr
    
    # Regex to find silence_start and silence_end
    # [silencedetect @ 0x...] silence_start: 123.456
    # [silencedetect @ 0x...] silence_end: 125.678 | silence_duration: 2.222
    
    starts = re.findall(r"silence_start: ([\d.]+)", output)
    ends = re.findall(r"silence_end: ([\d.]+)", output)
    
    if not ends:
        logger.warning("No silence detected with current parameters.")
        return []

    logger.debug(f"Detected {len(starts)} silence starts and {len(ends)} silence ends.")

    # Map silence ends to chapter start times
    # We treat the end of a silence as the start of a new chapter
    total_duration = get_audio_duration(file_path)
    
    chapters = []
    current_start = 0.0
    
    for i, end in enumerate(ends):
        end_val = float(end)
        if end_val > current_start + 1.0: # Minimum 1s chapter
            chapters.append({
                "start": current_start,
                "end": end_val,
                "title": f"Chapter {len(chapters) + 1}"
            })
            current_start = end_val
            
    # Add last chapter
    if current_start < total_duration:
        chapters.append({
            "start": current_start,
            "end": total_duration,
            "title": f"Chapter {len(chapters) + 1}"
        })
        
    return chapters

def concatenate_audio_files(file_list: List[str], output_path: str) -> bool:
    """Concatenates multiple audio files into one using ffmpeg"""
    if not file_list:
        return False
    if len(file_list) == 1:
        if os.path.exists(output_path):
            os.remove(output_path)
        os.rename(file_list[0], output_path)
        return True
        
    # Create a concat list file
    list_file = f"{output_path}.list.txt"
    try:
        with open(list_file, "w", encoding="utf-8") as f:
            for file_path in file_list:
                # ffmpeg requires escaping single quotes in filenames for the concat demuxer
                # Use absolute path for safety
                abs_path = os.path.abspath(file_path)
                safe_file = abs_path.replace("'", "'\\''")
                f.write(f"file '{safe_file}'\n")
        
        logger.info(f"🔗 Concatenating {len(file_list)} files into {output_path}...")
        # First try stream copy concatenation
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", list_file, "-c", "copy", output_path
        ]
        res = run_command(cmd)
        
        if res.returncode != 0:
            logger.warning("⚠️ Stream copy concatenation failed, trying with re-encoding...")
            # If copy fails (e.g. different parameters), try re-encoding
            cmd = [
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", list_file, "-c:a", "libmp3lame", "-q:a", "2", output_path
            ]
            res = run_command(cmd)
            
        return res.returncode == 0
    finally:
        if os.path.exists(list_file):
            os.remove(list_file)
        # Clean up individual parts
        for f in file_list:
            # Check if file exists and isn't the output file we just created
            if os.path.exists(f) and os.path.abspath(f) != os.path.abspath(output_path):
                try:
                    os.remove(f)
                except:
                    pass
