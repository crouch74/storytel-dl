#!/usr/bin/env python3
import argparse
import os
import subprocess
import json
import sys
import re
import logging
import glob
from typing import List, Dict, Any, Optional, Tuple

# Set up logger
logger = logging.getLogger(__name__)

def is_url(path: str) -> bool:
    """Checks if the path is a URL"""
    return path.startswith(("http://", "https://", "www."))

def download_youtube_audio(url: str, output_dir: str = ".") -> Optional[Tuple[str, List[Dict[str, Any]]]]:
    """Downloads audio from YouTube and extracts chapters using yt-dlp"""
    # Sanitize URL: remove backslashes that might come from shell escaping (e.g. \?, \&)
    url = url.replace("\\?", "?").replace("\\&", "&").replace("\\=", "=")
    
    logger.info(f"📺 Downloading from YouTube: {url}")
    
    # Try to find a working yt-dlp. Newer YouTube features require recent yt-dlp,
    # which often requires Python 3.9+. We prioritize newer python versions.
    yt_dlp_cmd = None
    
    # List of python commands to try (in order of preference)
    # Note: We put sys.executable later because if it's Python < 3.9, 
    # it might have an outdated yt-dlp that fails on recent YouTube changes.
    py_versions = ["python3.11", "python3.10", "python3.9", sys.executable, "python3"]
    
    for py in py_versions:
        # Check if this python can run yt-dlp and what version it is
        check_cmd = [py, "-m", "yt_dlp", "--version"] if py != "yt-dlp" else ["yt-dlp", "--version"]
        res = run_command(check_cmd)
        if res.returncode == 0:
            version_str = res.stdout.strip()
            logger.debug(f"Found yt-dlp version {version_str} using {py}")
            # If we are on an old python (like 3.8), we might want a newer one if available
            # but for now, we'll take the first one that works.
            yt_dlp_cmd = [py, "-m", "yt_dlp"] if py != "yt-dlp" else ["yt-dlp"]
            break
    
    if not yt_dlp_cmd:
        # Final fallback to raw 'yt-dlp' binary
        if run_command(["yt-dlp", "--version"]).returncode == 0:
            yt_dlp_cmd = ["yt-dlp"]
    
    if not yt_dlp_cmd:
        logger.error("❌ yt-dlp not found or incompatible. Please install it: pip install yt-dlp")
        logger.error("Note: yt-dlp now requires Python 3.9 or newer for latest YouTube support.")
        return None

    # We use a temporary filename template
    template = os.path.join(output_dir, "yt_download_%(id)s.%(ext)s")
    
    # 1. Get metadata and chapters
    logger.info("🎬 Extracting metadata...")
    cmd_meta = yt_dlp_cmd + [
        "--print-json", "--skip-download", "--no-playlist", 
        "--no-cache-dir",
        "--extractor-args", "youtube:player_client=android,web",
        url
    ]
    res_meta = run_command(cmd_meta)
    
    chapters = []
    title = "YouTube Audio"
    
    if res_meta.returncode == 0:
        try:
            info = json.loads(res_meta.stdout)
            title = info.get("title", title)
            yt_chapters = info.get("chapters") or []
            for c in yt_chapters:
                chapters.append({
                    "start": float(c["start_time"]),
                    "end": float(c["end_time"]),
                    "title": c.get("title", f"Chapter {len(chapters) + 1}")
                })
            logger.debug(f"Found {len(chapters)} chapters in YouTube metadata.")
        except json.JSONDecodeError:
            logger.error("Failed to parse YouTube metadata.")

    # Check if file already exists in output_dir
    safe_title = "".join([c if c.isalnum() else "_" for c in title])
    final_path = os.path.join(output_dir, f"{safe_title}.mp3")
    
    if os.path.exists(final_path):
        logger.info(f"♻️  File already exists in {output_dir}, skipping download: {final_path}")
        return final_path, chapters

    # 2. Download audio
    logger.info("📡 Downloading audio...")
    cmd_dl = yt_dlp_cmd + [
        "-f", "bestaudio/best", "-x", "--audio-format", "mp3", 
        "-o", template,
        "--no-playlist",
        "--no-cache-dir",
        "--geo-bypass",
        "--no-check-certificates",
        "--prefer-free-formats",
        "--add-header", "User-Agent:Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "--extractor-args", "youtube:player_client=android,web",
        url
    ]
    res_dl = run_command(cmd_dl)
    
    if res_dl.returncode != 0:
        logger.error(f"❌ yt-dlp download failed: {res_dl.stderr}")
        return None

    # Find the downloaded file
    # We look for files starting with yt_download_ and ending with .mp3
    downloaded_files = glob.glob(os.path.join(output_dir, "yt_download_*.mp3"))
    if not downloaded_files:
        logger.error("❌ Could not find downloaded audio file.")
        return None
    
    # Use the most recent one or the one matching the template logic
    audio_path = downloaded_files[0]
    
    try:
        # final_path already calculated above
        if os.path.exists(final_path):
            os.remove(final_path)
        os.rename(audio_path, final_path)
        logger.info(f"✅ Downloaded and saved as: {final_path}")
        return final_path, chapters
    except Exception as e:
        logger.error(f"Error renaming file: {e}")
        return audio_path, chapters

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
        return subprocess.CompletedProcess(cmd, 1, "", str(e))

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

def extract_metadata_chapters(file_path: str) -> List[Dict[str, Any]]:
    """Extracts existing chapters from metadata using ffprobe"""
    cmd = [
        "ffprobe", "-v", "quiet", "-print_format", "json", "-show_chapters", file_path
    ]
    res = run_command(cmd)
    try:
        data = json.loads(res.stdout)
        chapters = data.get("chapters", [])
        logger.debug(f"Raw chapters from metadata: {len(chapters)} found")
        return [
            {
                "start": float(c["start_time"]),
                "end": float(c["end_time"]),
                "title": c.get("tags", {}).get("title", f"Chapter {i+1}")
            }
            # Add index i to the list comprehension
            for i, c in enumerate(chapters)
        ]
    except (json.JSONDecodeError, KeyError, ValueError):
        return []

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


def detect_chapters_from_transcription(
    file_path: str, 
    model_name: str = "tiny",
    language: Optional[str] = None
) -> List[Dict[str, Any]]:
    """Detects chapters by transcribing audio and finding chapter markers using Whisper"""
    try:
        import whisper
    except ImportError:
        print("❌ Whisper not installed. Run: pip install openai-whisper")
        return []
    
    logger.info(f"🎙️ Transcribing audio with Whisper (model: {model_name})...")
    logger.info("   This may take a few minutes depending on audio length...")
    
    try:
        model = whisper.load_model(model_name)
        result = model.transcribe(
            file_path, 
            language=language,
            word_timestamps=True,
            verbose=False
        )
    except Exception as e:
        print(f"❌ Transcription failed: {e}")
        return []
    
    # Chapter marker patterns for various languages
    chapter_patterns = [
        # English patterns
        (r'\b(chapter|part|section)\s*(\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve)\b', 'en'),
        (r'\b(prologue|epilogue|introduction|preface|afterword)\b', 'en'),
        # Arabic patterns
        (r'(الفصل|الباب|الجزء)\s*(الأول|الثاني|الثالث|الرابع|الخامس|السادس|السابع|الثامن|التاسع|العاشر|\d+)', 'ar'),
        (r'(مقدمة|خاتمة|تمهيد)', 'ar'),
    ]
    
    # Word number to digit mapping (English)
    word_to_num = {
        'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
        'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
        'eleven': 11, 'twelve': 12
    }
    
    # Arabic ordinal to digit mapping
    arabic_to_num = {
        'الأول': 1, 'الثاني': 2, 'الثالث': 3, 'الرابع': 4, 'الخامس': 5,
        'السادس': 6, 'السابع': 7, 'الثامن': 8, 'التاسع': 9, 'العاشر': 10
    }
    
    chapters = []
    total_duration = get_audio_duration(file_path)
    
    # Process each segment from Whisper
    segments = result.get("segments", [])
    
    for segment in segments:
        text = segment.get("text", "").strip().lower()
        start_time = segment.get("start", 0)
        
        for pattern, lang in chapter_patterns:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                # Build chapter title
                matched_text = match.group(0)
                
                # Normalize the title
                title = matched_text.strip().title()
                
                # Avoid duplicate chapters at very close timestamps
                if chapters and abs(start_time - chapters[-1]["start"]) < 5.0:
                    continue
                
                chapters.append({
                    "start": start_time,
                    "end": start_time,  # Will be fixed later
                    "title": title
                })
                print(f"   📖 Found: '{title}' at {format_time(start_time)}")
                logger.debug(f"Transcription match: '{matched_text}' -> '{title}' at {start_time}s")
                break
    
    if not chapters:
        print("⚠️ No chapter markers found in transcription.")
        return []
    
    # Sort chapters by start time
    chapters.sort(key=lambda x: x["start"])
    
    # Fix end times: each chapter ends when the next begins
    for i in range(len(chapters) - 1):
        chapters[i]["end"] = chapters[i + 1]["start"]
    
    # Last chapter goes to the end of the file
    if chapters:
        chapters[-1]["end"] = total_duration
    
    print(f"✅ Found {len(chapters)} chapters via transcription.")
    return chapters


def format_time(seconds: float) -> str:
    """Formats seconds to HH:MM:SS.mmm"""
    ms = int((seconds % 1) * 1000)
    s = int(seconds % 60)
    m = int((seconds // 60) % 60)
    h = int(seconds // 3600)
    return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"

def filter_short_chapters(chapters: List[Dict[str, Any]], min_len: float) -> List[Dict[str, Any]]:
    """Merges chapters shorter than min_len into neighboring chapters"""
    if not chapters or min_len <= 0:
        return chapters

    logger.info(f"🧹 Filtering chapters shorter than {min_len}s...")
    
    filtered = []
    for c in chapters:
        if not filtered:
            filtered.append(c)
            continue
            
        # Check if the current chapter being added is too short
        chapter_duration = c['end'] - c['start']
        if chapter_duration < min_len:
            # Merge this short chapter into the previous one
            logger.debug(f"Merging short chapter '{c['title']}' ({chapter_duration:.1f}s) into '{filtered[-1]['title']}'")
            filtered[-1]['end'] = c['end']
        else:
            filtered.append(c)
            
    # Handle the case where the first chapter is too short but couldn't be merged backward
    if len(filtered) > 1:
        first_duration = filtered[0]['end'] - filtered[0]['start']
        if first_duration < min_len:
            logger.debug(f"Merging short first chapter '{filtered[0]['title']}' into '{filtered[1]['title']}'")
            filtered[1]['start'] = filtered[0]['start']
            filtered.pop(0)

    # Re-index titles if they are generic "Chapter N"
    for i, c in enumerate(filtered):
        if re.match(r"^Chapter \d+$", c['title']):
            c['title'] = f"Chapter {i+1}"
            
    return filtered

def validate_chapters(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Interactive CLI to review and edit chapters"""
    if not chapters:
        print("❌ No chapters found to validate.")
        return []

    while True:
        print("\n📋 Detected Chapters:")
        for i, c in enumerate(chapters, 1):
            duration = c['end'] - c['start']
            print(f"  [{i}] {c['title']:30} | Start: {format_time(c['start'])} | Duration: {format_time(duration)}")
        
        print("\nOptions:")
        print("  [v] Proceed with these chapters")
        print("  [e <index>] Edit title (e.g., 'e 1')")
        print("  [d <index>] Delete chapter")
        print("  [a <time> <title>] Add chapter (e.g., 'a 05:30 Intro')")
        print("  [r] Reset/Abort")
        
        choice = input("\n👉 Choose an option: ").strip().lower()
        
        if choice == 'v':
            return sorted(chapters, key=lambda x: x['start'])
        elif choice == 'r':
            return []
        elif choice.startswith('e '):
            try:
                parts = choice.split(maxsplit=2)
                idx = int(parts[1]) - 1
                if 0 <= idx < len(chapters):
                    new_title = input(f"Enter new title for Chapter {idx+1}: ").strip()
                    if new_title:
                        chapters[idx]['title'] = new_title
                else:
                    print("⚠️ Invalid index.")
            except (ValueError, IndexError):
                print("⚠️ Invalid format. Use 'e <index>'.")
        elif choice.startswith('d '):
            try:
                parts = choice.split()
                idx = int(parts[1]) - 1
                if 0 <= idx < len(chapters):
                    del chapters[idx]
                    print(f"🗑️ Chapter {idx+1} removed.")
                else:
                    print("⚠️ Invalid index.")
            except (ValueError, IndexError):
                print("⚠️ Invalid format. Use 'd <index>'.")
        elif choice.startswith('a '):
            try:
                # a 05:30 New Chapter
                parts = choice.split(maxsplit=2)
                time_str = parts[1]
                title = parts[2] if len(parts) > 2 else "New Chapter"
                
                # Parse time (MM:SS or HH:MM:SS)
                t_parts = list(map(float, time_str.split(':')))
                if len(t_parts) == 1:
                    start_time = t_parts[0]
                elif len(t_parts) == 2:
                    start_time = t_parts[0] * 60 + t_parts[1]
                elif len(t_parts) == 3:
                    start_time = t_parts[0] * 3600 + t_parts[1] * 60 + t_parts[2]
                else:
                    raise ValueError
                
                chapters.append({
                    "start": start_time,
                    "end": start_time + 10, # Temporary end
                    "title": title
                })
                # Re-sort and fix ends
                chapters.sort(key=lambda x: x['start'])
                for i in range(len(chapters) - 1):
                    chapters[i]['end'] = chapters[i+1]['start']
                # Last chapter end handled by total duration elsewhere or just high value
                print(f"➕ Added chapter at {time_str}")
            except (ValueError, IndexError):
                print("⚠️ Invalid format. Use 'a <time> <title>' where time is SS, MM:SS or HH:MM:SS.")
        else:
            print("⚠️ Invalid option.")

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

def main():
    parser = argparse.ArgumentParser(description="Audiobook Chapter Extractor")
    parser.add_argument("input", help="Path to input MP3 file")
    parser.add_argument("--out", help="Path to output M4B file (defaults to same name)")
    parser.add_argument("--silence-db", type=int, default=-35, help="Silence detection threshold in dB (default: -35)")
    parser.add_argument("--silence-len", type=float, default=2.0, help="Minimum silence length in seconds (default: 2.0)")
    parser.add_argument("--transcription", action="store_true", help="Use speech transcription to detect chapter markers")
    parser.add_argument("--whisper-model", default="tiny", choices=["tiny", "base", "small", "medium", "large"], 
                        help="Whisper model size (default: tiny)")
    parser.add_argument("--language", help="Audio language code (e.g., 'en', 'ar'). Auto-detected if not specified.")
    parser.add_argument("--min-chapter-len", type=float, default=20.0, help="Minimum chapter length in seconds (default: 20.0)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' if args.debug else '%(message)s'
    )
    
    original_input = args.input
    chapters = []
    author = None
    title = None
    
    if is_url(args.input):
        tmp_dir = ".tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        result = download_youtube_audio(args.input, output_dir=tmp_dir)
        if not result:
            sys.exit(1)
        args.input, chapters = result
        if chapters:
            logger.info(f"⭐ Found {len(chapters)} chapters on YouTube.")
            use_yt_chapters = input("Use these YouTube chapters? [Y/n]: ").strip().lower() != 'n'
            if not use_yt_chapters:
                chapters = []

        # Ask for author and title for YouTube sources
        print("\n📝 Please provide metadata for the YouTube source:")
        # Use filename as default title suggestion
        default_title = os.path.splitext(os.path.basename(args.input))[0].replace("_", " ")
        author = input(f"Enter Author Name [Unknown Author]: ").strip() or "Unknown Author"
        title = input(f"Enter Book Title [{default_title}]: ").strip() or default_title
        
        # Enforce the requested path structure: author/title/title.m4b
        # Sanitize for path usage
        safe_author = author.replace("/", "-").replace("\\", "-")
        safe_title = title.replace("/", "-").replace("\\", "-")
        
        base_dir = args.out or "."
        args.out = os.path.join(base_dir, safe_author, safe_title, f"{safe_title}.m4b")
        logger.info(f"📍 Output path set to: {args.out}")

    if not os.path.exists(args.input):
        print(f"❌ Input file not found: {args.input}")
        sys.exit(1)

    output_path = args.out or os.path.splitext(args.input)[0] + ".m4b"
    
    logger.info("\n🎧 Audiobook Chapter Extractor")
    logger.info(f"📁 Input: {args.input}")
    
    if not chapters:
        # 1. Try metadata first
        chapters = extract_metadata_chapters(args.input)
        if chapters:
            print(f"⭐ Found {len(chapters)} chapters in metadata.")
            use_meta = input("Use these chapters? [Y/n]: ").strip().lower() != 'n'
            if not use_meta:
                chapters = []
    
    # 2. Try transcription-based detection if enabled
    if not chapters and args.transcription:
        chapters = detect_chapters_from_transcription(
            args.input, 
            model_name=args.whisper_model,
            language=args.language
        )
            
    # 3. Try silence detection as fallback
    if not chapters:
        logger.info("🔇 Trying silence-based detection...")
        chapters = detect_silence(args.input, args.silence_db, args.silence_len)
        
    if not chapters:
        logger.warning("⚠️ Could not find or detect any chapters. Defaulting to a single chapter.")
        duration = get_audio_duration(args.input)
        chapters = [{
            "start": 0.0,
            "end": duration,
            "title": "Full Audio" if not title else title
        }]
        
    # Ensure last chapter reaches the end of the file
    duration = get_audio_duration(args.input)
    if chapters and duration > 0:
        chapters[-1]['end'] = duration

    # 4. Filter short chapters
    chapters = filter_short_chapters(chapters, args.min_chapter_len)

    # 5. Interactive validation
    final_chapters = validate_chapters(chapters)
    
    if not final_chapters:
        print("🚫 Aborted by user.")
        sys.exit(0)
        
    # Ensure output reaches the end of file for the very last chapter after edits
    if final_chapters and duration > 0:
        final_chapters[-1]['end'] = duration

    # 4. Create M4B
    print(f"📦 Finalizing... Output will be: {output_path}")
    create_m4b(args.input, output_path, final_chapters, title=title, author=author)

if __name__ == "__main__":
    main()
