import os
import subprocess
import logging
from typing import Any, Dict, List

def convert_to_m4b(input_path: str, output_path: str, markers: List[Dict[str, Any]], metadata: Dict[str, Any]) -> bool:
    """
    Converts an audio file to M4B and embeds chapter markers using ffmpeg.
    
    :param input_path: Path to the source MP3 file
    :param output_path: Path to the target M4B file
    :param markers: List of marker dictionaries with 'title' and 'startTime' (ms)
    :param metadata: Dictionary of book metadata for embedding
    :return: True if successful, False otherwise
    """
    if not os.path.exists(input_path):
        logging.error(f"❌ Input file not found for conversion: {input_path}")
        return False

    # Create FFMETADATA file
    metadata_file = f"{input_path}.metadata"
    try:
        with open(metadata_file, "w", encoding="utf-8") as f:
            f.write(";FFMETADATA1\n")
            f.write(f"title={metadata.get('title') or ''}\n")
            f.write(f"artist={metadata.get('author') or ''}\n")
            f.write(f"album={metadata.get('title') or ''}\n")
            f.write(f"genre={', '.join(metadata.get('genres') or [])}\n")
            f.write(f"description={metadata.get('description') or ''}\n")
            
            # Add chapters
            if markers:
                # Sort markers by startTime
                sorted_markers = sorted(markers, key=lambda x: x.get('startTime', 0))
                
                for i in range(len(sorted_markers)):
                    m = sorted_markers[i]
                    start = m.get('startTime', 0) # in ms
                    title = m.get('title') or f"Chapter {i+1}"
                    
                    # End time is either next marker or unknown
                    # ffmpeg metadata uses 'TIMEBASE=1/1000' for ms
                    f.write("\n[CHAPTER]\n")
                    f.write("TIMEBASE=1/1000\n")
                    f.write(f"START={start}\n")
                    
                    if i + 1 < len(sorted_markers):
                        end = sorted_markers[i+1].get('startTime', start)
                        f.write(f"END={end}\n")
                    else:
                        # For the last chapter, let ffmpeg handle it or set a very large number
                        # Better to not specify END if possible, but FFMETADATA requires it.
                        # We don't easily know the total duration here without ffprobe.
                        # Using 0 for END on the last chapter might work or we can probe.
                        # Most players handle missing END or large END.
                        # Let's try to get duration via ffprobe if possible, or just use a very large value.
                        f.write(f"END={start + 10000000}\n") # fallback high value
                    
                    f.write(f"title={title}\n")

        # ffmpeg command
        # -i input -i metadata -map_metadata 1 -c:a aac -b:a 64k (standard for audiobooks) output
        # If input is already m4b/mp4, we can copy the stream to save time and quality
        is_m4b = input_path.lower().endswith(('.m4b', '.mp4', '.m4a'))
        
        if is_m4b:
            audio_codec = ["-c:a", "copy"]
        else:
            audio_codec = ["-c:a", "aac", "-b:a", "64k"]
        
        cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-i", metadata_file,
            "-map_metadata", "1",
            *audio_codec,
            "-f", "mp4", # M4B is technically MP4
            output_path
        ]
        
        logging.info(f"⚙️ Converting {os.path.basename(input_path)} to M4B...")
        # Run ffmpeg. We don't use text=True to avoid encoding issues with non-UTF8 output from ffmpeg
        result = subprocess.run(cmd, capture_output=True)
        
        if result.returncode == 0:
            logging.info(f"✅ Successfully converted to M4B: {os.path.basename(output_path)}")
            return True
        else:
            stderr_msg = result.stderr.decode('utf-8', errors='replace')
            logging.error(f"❌ ffmpeg failed: {stderr_msg}")
            return False
            
    except Exception as e:
        logging.error(f"❌ Error during M4B conversion: {e}")
        return False
    finally:
        if os.path.exists(metadata_file):
            os.remove(metadata_file)

def fix_markers_locally(input_path: str) -> bool:
    """
    Extracts metadata from a file, fixes 'None' or empty chapter titles, and re-embeds it.
    This is a fully local operation.
    """
    if not os.path.exists(input_path):
        return False

    metadata_file = f"{input_path}.meta_extract"
    output_path = f"{input_path}.fixed_tmp.m4b"
    
    try:
        # 1. Extract metadata
        extract_cmd = ["ffmpeg", "-y", "-i", input_path, "-f", "ffmetadata", metadata_file]
        subprocess.run(extract_cmd, capture_output=True, check=True)
        
        # 2. Parse and fix
        with open(metadata_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            
        fixed_lines = []
        chapter_count = 0
        in_chapter = False
        has_title = False
        
        for line in lines:
            if line.strip() == "[CHAPTER]":
                # If we were in a chapter and didn't find a title, add one before starting new chapter
                if in_chapter and not has_title:
                    fixed_lines.append(f"title=Chapter {chapter_count}\n")
                
                in_chapter = True
                chapter_count += 1
                has_title = False
                fixed_lines.append(line)
            elif in_chapter and line.startswith("title="):
                title_val = line.split("=", 1)[1].strip()
                if not title_val or title_val.lower() == "none":
                    fixed_lines.append(f"title=Chapter {chapter_count}\n")
                else:
                    fixed_lines.append(line)
                has_title = True
            else:
                fixed_lines.append(line)
        
        # Final check for last chapter
        if in_chapter and not has_title:
            fixed_lines.append(f"title=Chapter {chapter_count}\n")

        with open(metadata_file, "w", encoding="utf-8") as f:
            f.writelines(fixed_lines)
            
        # 3. Re-embed
        # We use -codec copy to avoid re-encoding
        embed_cmd = [
            "ffmpeg", "-y",
            "-i", input_path,
            "-i", metadata_file,
            "-map_metadata", "1",
            "-codec", "copy",
            output_path
        ]
        
        res = subprocess.run(embed_cmd, capture_output=True)
        if res.returncode == 0:
            # Swap files
            os.remove(input_path)
            os.rename(output_path, input_path)
            return True
        else:
            logging.error(f"❌ Failed to re-embed metadata: {res.stderr.decode(errors='replace')}")
            return False
            
    except Exception as e:
        logging.error(f"❌ Error fixing markers locally for {input_path}: {e}")
        return False
    finally:
        if os.path.exists(metadata_file):
            os.remove(metadata_file)
        if os.path.exists(output_path):
            os.remove(output_path)
