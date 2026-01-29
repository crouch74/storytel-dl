import json
import os
import logging
import re
import sys
from typing import List, Dict, Any, Optional
from .utils import run_command, format_time
from .audio import get_audio_duration

logger = logging.getLogger(__name__)

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
    # word_to_num = {
    #     'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5,
    #     'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10,
    #     'eleven': 11, 'twelve': 12
    # }
    
    # Arabic ordinal to digit mapping
    # arabic_to_num = {
    #     'الأول': 1, 'الثاني': 2, 'الثالث': 3, 'الرابع': 4, 'الخامس': 5,
    #     'السادس': 6, 'السابع': 7, 'الثامن': 8, 'التاسع': 9, 'العاشر': 10
    # }
    
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

def clean_chapter_titles(chapters: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Removes common prefixes from chapter titles"""
    if not chapters or len(chapters) < 2:
        return chapters
        
    titles = [c['title'] for c in chapters]
    
    # Find longest common prefix
    prefix = os.path.commonprefix(titles)
    
    if prefix:
        # If the prefix doesn't end with a space or separator, it might be 
        # cutting into a word. Let's try to back up to the last separator.
        # Separators: | , - , : , / , space
        last_sep = -1
        for sep in [" | ", " - ", ": ", " / ", " – "]:
            idx = prefix.rfind(sep)
            if idx > last_sep:
                last_sep = idx + len(sep)
        
        # If no fancy separator, check for a simple space
        if last_sep == -1:
            idx = prefix.rfind(" ")
            if idx != -1:
                last_sep = idx + 1
        
        if last_sep != -1:
            prefix = prefix[:last_sep]
            
        if len(prefix) > 3: # Only strip if it's a substantial prefix
            logger.info(f"🧹 Removing common prefix from chapters: '{prefix}'")
            for c in chapters:
                if c['title'].startswith(prefix):
                    c['title'] = c['title'][len(prefix):].strip()
                    
    return chapters

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
