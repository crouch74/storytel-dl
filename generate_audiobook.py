#!/usr/bin/env python3
import argparse
import os
import sys
import logging
from typing import List, Dict, Any, Optional

from audio_extractor.utils import is_url
from audio_extractor.audio import get_audio_duration, detect_silence
from audio_extractor.chapters import (
    extract_metadata_chapters, 
    detect_chapters_from_transcription,
    filter_short_chapters,
    validate_chapters
)
from audio_extractor.youtube import download_youtube_audio
from audio_extractor.m4b import create_m4b

# Set up logger
logger = logging.getLogger(__name__)

def ask_user(prompt: str, default: bool = True, auto: bool = False) -> bool:
    if auto:
        return default
    suffix = " [Y/n]" if default else " [y/N]"
    response = input(f"{prompt}{suffix}: ").strip().lower()
    if not response:
        return default
    return response == 'y'

def get_input(prompt: str, default_val: str = "", auto: bool = False) -> str:
    if auto:
        return default_val
    val = input(f"{prompt} [{default_val}]: ").strip()
    return val if val else default_val

def process_item(input_source: str, args: argparse.Namespace):
    logger.info(f"\n🚀 Processing: {input_source}")
    
    current_input = input_source
    chapters = []
    author = None
    title = None
    cover_path = args.cover
    
    # Reset per-item variables that might be set in args (like explicit output path shouldn't survive across batch items unless it's a dir)
    output_target = args.out 
    
    if is_url(current_input):
        tmp_dir = ".tmp"
        os.makedirs(tmp_dir, exist_ok=True)
        # Assuming download_youtube_audio returns: path, chapters, title, author, cover_path
        result = download_youtube_audio(
            current_input, 
            output_dir=tmp_dir, 
            cookies_from_browser=args.cookies_from_browser, 
            cookies_file=args.cookies, 
            list_formats=args.list_formats and not args.auto
        )
        
        if not result:
            logger.error(f"❌ Failed to download: {current_input}")
            return
            
        current_input, yt_chapters, yt_title, yt_author, yt_cover = result
        
        # Use YouTube cover if found and no user override
        if not cover_path and yt_cover:
            cover_path = yt_cover
            
        if yt_chapters:
            logger.info(f"⭐ Found {len(yt_chapters)} chapters on YouTube.")
            if ask_user("Use these YouTube chapters?", True, args.auto):
                chapters = yt_chapters
                if ask_user("Rename chapters sequentially (Chapter 1, Chapter 2...)?", False, args.auto):
                    for i, ch in enumerate(chapters):
                        ch['title'] = f"Chapter {i+1}"
                    logger.info("✅ Renamed chapters sequentially.")

        # Metadata
        if not args.auto:
            print("\n📝 Please provide metadata for the YouTube source:")
        
        author = get_input("Enter Author Name", yt_author, args.auto)
        title = get_input("Enter Book Title", yt_title, args.auto)
        
        # Enforce path structure for YouTube downloads: author/title/title.m4b
        safe_author = author.replace("/", "-").replace("\\", "-")
        safe_title = title.replace("/", "-").replace("\\", "-")
        
        base_dir = output_target or "."
        # If output_target is a specific file (ends in .m4b), use it, otherwise treat as dir
        if output_target and output_target.lower().endswith(".m4b") and not args.batch:
            pass # Use as is
        else:
            output_target = os.path.join(base_dir, safe_author, safe_title, f"{safe_title}.m4b")
            
        logger.info(f"📍 Output path set to: {output_target}")

    # Local file checks
    if not os.path.exists(current_input):
        logger.error(f"❌ Input file not found: {current_input}")
        return

    # Determine final output path if not yet set (local file case)
    if not output_target:
        output_target = os.path.splitext(current_input)[0] + ".m4b"
        
    # Attempt to find local cover if not set
    if not cover_path and not is_url(input_source):
        # Check specific names in the directory of input file
        input_dir = os.path.dirname(os.path.abspath(current_input))
        for cand in ["cover.jpg", "cover.png", "folder.jpg", "folder.png"]:
            cand_path = os.path.join(input_dir, cand)
            if os.path.exists(cand_path):
                cover_path = cand_path
                break

    # If still no cover and interactive, ask
    if not cover_path and not args.auto:
         cp = input("🖼️  No cover found. Enter path/URL to cover image (or Enter to skip): ").strip()
         if cp:
             cover_path = cp # Simplify: assuming local path for now. dealing with URL covers would require downloading.
             
    # --- Chapter Extraction Strategies ---
    if not chapters:
        # 1. Metadata
        chapters = extract_metadata_chapters(current_input)
        if chapters:
            logger.info(f"⭐ Found {len(chapters)} chapters in metadata.")
            if not ask_user("Use these chapters?", True, args.auto):
                chapters = []

    # 2. Transcription
    if not chapters and args.transcription:
        chapters = detect_chapters_from_transcription(
            current_input, 
            model_name=args.whisper_model,
            language=args.language
        )
            
    # 3. Silence
    if not chapters:
        logger.info("🔇 Trying silence-based detection...")
        chapters = detect_silence(current_input, args.silence_db, args.silence_len)
        
    # Default fallback
    if not chapters:
        logger.warning("⚠️ Could not find or detect any chapters. Defaulting to a single chapter.")
        duration = get_audio_duration(current_input)
        chapters = [{
            "start": 0.0,
            "end": duration,
            "title": "Full Audio" if not title else title
        }]
        
    # Fix durations
    duration = get_audio_duration(current_input)
    if chapters and duration > 0:
        chapters[-1]['end'] = duration

    # 4. Filter
    chapters = filter_short_chapters(chapters, args.min_chapter_len)

    # 5. Validation (interactive edit)
    # Only run interactive validation if NOT auto
    final_chapters = chapters
    if not args.auto:
        final_chapters = validate_chapters(chapters)
    
    if not final_chapters:
        logger.info("🚫 Aborted.")
        return

    # Ensure output reaches end
    if final_chapters and duration > 0:
        final_chapters[-1]['end'] = duration

    # 6. Create M4B
    print(f"📦 Finalizing... Output will be: {output_target}")
    create_m4b(
        current_input, 
        output_target, 
        final_chapters, 
        title=title, 
        author=author, 
        cover_path=cover_path,
        normalize=args.normalize
    )

def main():
    parser = argparse.ArgumentParser(description="Audiobook Chapter Extractor")
    parser.add_argument("input", nargs='?', help="Path to input MP3 file or YouTube URL (optional if --batch is used)")
    parser.add_argument("--batch", help="Path to a text file with a list of URLs/paths to process")
    parser.add_argument("--out", help="Path to output M4B file (or base directory for batch/YouTube)")
    parser.add_argument("--cover", help="Path to cover image")
    
    parser.add_argument("--normalize", action="store_true", help="Normalize audio loudness to -16 LUFS")
    parser.add_argument("--auto", action="store_true", help="Run non-interactively (accept defaults)")
    
    parser.add_argument("--silence-db", type=int, default=-35, help="Silence detection threshold in dB (default: -35)")
    parser.add_argument("--silence-len", type=float, default=2.0, help="Minimum silence length in seconds (default: 2.0)")
    parser.add_argument("--transcription", action="store_true", help="Use speech transcription to detect chapter markers")
    parser.add_argument("--whisper-model", default="tiny", choices=["tiny", "base", "small", "medium", "large"], 
                        help="Whisper model size (default: tiny)")
    parser.add_argument("--language", help="Audio language code (e.g., 'en', 'ar'). Auto-detected if not specified.")
    parser.add_argument("--min-chapter-len", type=float, default=20.0, help="Minimum chapter length in seconds (default: 20.0)")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    parser.add_argument("--cookies-from-browser", help="Browser to extract cookies from (e.g., 'chrome', 'firefox', 'safari')")
    parser.add_argument("--cookies", help="Path to a cookies.txt file")
    
    args = parser.parse_args()
    
    # Defaults
    args.list_formats = True
    
    # Configure logging
    log_level = logging.DEBUG if args.debug else logging.INFO
    logging.basicConfig(
        level=log_level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s' if args.debug else '%(message)s'
    )
    
    inputs = []
    
    if args.input:
        inputs.append(args.input)
        
    if args.batch:
        if os.path.exists(args.batch):
            with open(args.batch, 'r') as f:
                lines = [l.strip() for l in f.readlines()]
                for line in lines:
                    if line and not line.startswith("#"):
                        inputs.append(line)
        else:
            logger.error(f"❌ Batch file not found: {args.batch}")
            sys.exit(1)
            
    if not inputs:
        parser.print_help()
        sys.exit(1)
        
    logger.info(f"📋 Queued {len(inputs)} item(s) for processing.")
    
    for i, item in enumerate(inputs):
        logger.info(f"--- Item {i+1}/{len(inputs)} ---")
        try:
            process_item(item, args)
        except Exception as e:
            logger.error(f"❌ Error processing {item}: {e}")
            if args.debug:
                raise e

if __name__ == "__main__":
    main()
