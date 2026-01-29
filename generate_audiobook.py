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
    parser.add_argument("--cookies-from-browser", help="Browser to extract cookies from (e.g., 'chrome', 'firefox', 'safari')")
    parser.add_argument("--cookies", help="Path to a cookies.txt file")
    
    args = parser.parse_args()
    
    # Use list-formats by default unless no-interactive is set
    args.list_formats = True
    
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
        result = download_youtube_audio(args.input, output_dir=tmp_dir, cookies_from_browser=args.cookies_from_browser, cookies_file=args.cookies, list_formats=args.list_formats)
        if not result:
            sys.exit(1)
        args.input, chapters, yt_title, yt_author = result
        if chapters:
            logger.info(f"⭐ Found {len(chapters)} chapters on YouTube.")
            use_yt_chapters = input("Use these YouTube chapters? [Y/n]: ").strip().lower() != 'n'
            if not use_yt_chapters:
                chapters = []

        # Ask for author and title for YouTube sources
        print("\n📝 Please provide metadata for the YouTube source:")
        author = input(f"Enter Author Name [{yt_author}]: ").strip() or yt_author
        title = input(f"Enter Book Title [{yt_title}]: ").strip() or yt_title
        
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

    # 6. Create M4B
    print(f"📦 Finalizing... Output will be: {output_path}")
    create_m4b(args.input, output_path, final_chapters, title=title, author=author)

if __name__ == "__main__":
    main()
