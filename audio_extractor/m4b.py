import os
import logging
from typing import List, Dict, Any, Optional
from .utils import run_command

logger = logging.getLogger(__name__)

def create_m4b(input_path: str, output_path: str, chapters: List[Dict[str, Any]], title: Optional[str] = None, author: Optional[str] = None):
    """Creates M4B file with embedded metadata and chapters"""
    meta_file = f"{input_path}.metadata"
    
    # Ensure output directory exists
    output_dir = os.path.dirname(os.path.abspath(output_path))
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        
    # Prepare FFMETADATA
    try:
        if not title:
            title = os.path.splitext(os.path.basename(output_path))[0]
            
        with open(meta_file, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            f.write(f"title={title}\n")
            if author:
                f.write(f"artist={author}\n")
                f.write(f"album_artist={author}\n")
            
            for c in chapters:
                f.write("\n[CHAPTER]\n")
                f.write("TIMEBASE=1/1000\n")
                f.write(f"START={int(c['start'] * 1000)}\n")
                f.write(f"END={int(c['end'] * 1000)}\n")
                f.write(f"title={c['title']}\n")
        
        # ffmpeg -i input -i metadata -map_metadata 1 -c:a aac -b:a 64k output.m4b
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-i", meta_file,
            "-map_metadata", "1",
            "-c:a", "aac", "-b:a", "128k", # Good quality
            "-f", "mp4",
            output_path
        ]
        
        logger.info(f"🎬 Creating M4B: {output_path}...")
        res = run_command(cmd)
        if res.returncode == 0:
            logger.info(f"✅ Successfully created M4B: {output_path}")
        else:
            logger.error(f"❌ Failed to create M4B: {res.stderr}")
            
    finally:
        if os.path.exists(meta_file):
            os.remove(meta_file)
