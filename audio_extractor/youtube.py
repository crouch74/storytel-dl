import os
import sys
import json
import logging
import glob
import uuid
from typing import List, Dict, Any, Optional, Tuple
from .utils import run_command
from .audio import get_audio_duration, concatenate_audio_files
from .chapters import clean_chapter_titles

logger = logging.getLogger(__name__)

def download_youtube_audio(url: str, output_dir: str = ".", cookies_from_browser: Optional[str] = None, cookies_file: Optional[str] = None, list_formats: bool = False) -> Optional[Tuple[str, List[Dict[str, Any]], str, str, Optional[str]]]:
    """Downloads audio from YouTube (single video or playlist) and extracts chapters"""
    # Sanitize URL: remove backslashes that might come from shell escaping (e.g. \?, \&)
    url = url.replace("\\?", "?").replace("\\&", "&").replace("\\=", "=")
    
    logger.info(f"📺 Downloading from YouTube: {url}")
    
    # Try to find a working yt-dlp.
    yt_dlp_cmd = None
    py_versions = [sys.executable, "python3", "python3.11", "python3.10", "python3.9"]
    
    for py in py_versions:
        check_cmd = [py, "-m", "yt_dlp", "--version"]
        res = run_command(check_cmd)
        if res.returncode == 0:
            yt_dlp_cmd = [py, "-m", "yt_dlp"]
            break
    
    if not yt_dlp_cmd:
        if run_command(["yt-dlp", "--version"]).returncode == 0:
            yt_dlp_cmd = ["yt-dlp"]
    
    if not yt_dlp_cmd:
        logger.error("❌ yt-dlp not found or incompatible. Please install it: pip install yt-dlp")
        return None

    # 1. Get metadata and entries
    logger.info("🎬 Extracting metadata (this may take a moment for playlists)...")
    cmd_meta = yt_dlp_cmd + [
        "--dump-single-json", "--skip-download",
        "--no-cache-dir",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=web,tv",
        url
    ]
    
    if cookies_from_browser:
        cmd_meta += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd_meta += ["--cookies", cookies_file]
    res_meta = run_command(cmd_meta)
    
    if res_meta.returncode != 0:
        logger.error(f"❌ Failed to get YouTube metadata: {res_meta.stderr}")
        return None

    try:
        info = json.loads(res_meta.stdout)
    except json.JSONDecodeError:
        logger.error("❌ Failed to parse YouTube metadata.")
        if res_meta.stderr:
            logger.debug(f"Metadata stderr: {res_meta.stderr}")
        return None

    # Handle format listing if requested or if no formats found
    formats = info.get("formats", [])
    selected_format = "ba/best"
    
    if list_formats:
        print("\n📊 Available YouTube formats:")
        print(f"{'ID':<5} {'EXT':<5} {'RESOLUTION':<15} {'FILESIZE':<10} {'TBR':<6} {'PROTO':<6} {'ACODEC':<15}")
        print("-" * 75)
        
        # Filter for interesting formats (audio or common video)
        for f in formats:
            fid = str(f.get("format_id", "N/A"))
            ext = str(f.get("ext", "N/A"))
            res = str(f.get("resolution", "audio only"))
            size = f.get("filesize_approx") or f.get("filesize")
            size_str = f"{size/(1024*1024):.1f}M" if size else "N/A"
            tbr = str(f.get("tbr", "N/A"))
            proto = str(f.get("protocol", "N/A"))
            acodec = str(f.get("acodec", "N/A"))
            
            # Highlight audio-only formats or common combined formats
            if f.get("vcodec") == "none":
                print(f"⭐ {fid:4} {ext:4} {res:15} {size_str:10} {tbr:<6} {proto:<6} {acodec:15}")
            else:
                print(f"  {fid:4} {ext:4} {res:15} {size_str:10} {tbr:<6} {proto:<6} {acodec:15}")
        
        choice = input("\n👉 Enter format ID to download (default: bestaudio): ").strip()
        if choice:
            selected_format = choice
            logger.info(f"🎯 Selected format: {selected_format}")

    is_playlist = info.get("_type") == "playlist"
    entries = info.get("entries", [info]) if is_playlist else [info]
    
    # Store original index to match filenames later, regardless of reordering
    for i, e in enumerate(entries):
        if e: # entries can contain Nones for deleted videos
            e['_original_index'] = i + 1
    
    playlist_items_str = ""
    if is_playlist:
        print(f"\n📋 Playlist found: {info.get('title', 'Unknown')}")
        print(f"Found {len(entries)} videos.")
        print("-" * 60)
        for i, entry in enumerate(entries):
            if not entry:
                print(f"{i+1:3d}. [Deleted/Unknown]")
                continue
            title = entry.get('title', 'Unknown')
            duration = entry.get('duration')
            dur_str = f"{int(duration//60)}:{int(duration%60):02d}" if duration else "N/A"
            print(f"{i+1:3d}. [{dur_str}] {title}")
        print("-" * 60)
        
        print("OPTIONS:")
        print(" - Press Enter to download ALL in original order.")
        print(" - Enter specific indices to keep (e.g. '1,3,5').")
        print(" - Enter indices in ANY ORDER to rearrange (e.g. '3,1,2').")
        
        selection_input = input("👉 Selection: ").strip()
        
        if selection_input:
            try:
                # Parse indices
                selected_indices = [int(x.strip()) for x in selection_input.split(",") if x.strip().isdigit()]
                
                if not selected_indices:
                    logger.warning("⚠️ No valid indices found. Downloading all.")
                else:
                    reordered_entries = []
                    # Validate indices
                    valid_indices = []
                    for idx in selected_indices:
                        if 1 <= idx <= len(entries):
                            reordered_entries.append(entries[idx-1])
                            valid_indices.append(str(idx))
                        else:
                            logger.warning(f"⚠️ Index {idx} out of bounds, skipping.")
                    
                    if not reordered_entries:
                        logger.error("❌ No valid videos selected!")
                        return None
                    
                    # We need to tell yt-dlp which items to download. 
                    # Order in --playlist-items doesn't strictly dictate download order, 
                    # but we handle the final merge order manually in Python.
                    # We just need to ensure the unique set of files is downloaded.
                    unique_indices = sorted(list(set(valid_indices)))
                    playlist_items_str = ",".join(unique_indices)
                    
                    entries = reordered_entries
                    logger.info(f"✅ Selected {len(entries)} videos in custom order.")
                    
            except ValueError:
                logger.warning("⚠️ Invalid input. Downloading all.")
    playlist_title = info.get("title", "YouTube Audio")
    uploader = info.get("uploader", info.get("uploader_id", "Unknown Author"))
    
    # Generate a unique session ID using playlist/video ID + UUID
    # This ensures concurrent downloads don't interfere with each other
    playlist_id = info.get("id", "unknown")
    session_uuid = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for brevity
    session_id = f"{playlist_id}_{session_uuid}"
    logger.debug(f"Session ID: {session_id}")
    
    # Check if combined file already exists in output_dir
    safe_title = "".join([c if c.isalnum() else "_" for c in playlist_title])
    
    # Calculate order hash to ensure we don't reuse cached files with different video order
    # This is critical if the user reorders the playlist
    id_list = [e.get('id', 'unknown') for e in entries]
    import hashlib
    order_hash = hashlib.md5(",".join(id_list).encode()).hexdigest()[:8]
    
    final_path = os.path.join(output_dir, f"{safe_title}_{order_hash}.mp3")
    
    if os.path.exists(final_path):
        logger.info(f"♻️  File already exists, skipping download: {final_path}")
        # Recalculate chapters from info
        all_chapters = []
        current_offset = 0.0
        for entry in entries:
            if not entry: continue
            duration = float(entry.get("duration") or 0)
            yt_chapters = entry.get("chapters") or []
            if not yt_chapters:
                all_chapters.append({
                    "start": current_offset,
                    "end": current_offset + duration,
                    "title": entry.get("title", f"Part {len(all_chapters) + 1}")
                })
            else:
                for c in yt_chapters:
                    all_chapters.append({
                        "start": float(c["start_time"]) + current_offset,
                        "end": float(c["end_time"]) + current_offset,
                        "title": c.get("title", f"Chapter {len(all_chapters) + 1}")
                    })
            current_offset += duration
            
        # Check for any likely cover
        found_covers = glob.glob(os.path.join(output_dir, "*.jpg"))
        cover_path = found_covers[0] if found_covers else None
        
        # If no cover found, try to fetch just the thumbnail
        if not cover_path:
            logger.info("🖼️  Audio exists but cover missing. Fetching thumbnail...")
            cover_temp = os.path.join(output_dir, f"cover_{session_id}")
            cmd_cover = yt_dlp_cmd + [
                "--write-thumbnail", "--skip-download", "--convert-thumbnails", "jpg",
                "--playlist-items", "1",
                "-o", cover_temp,
                url
            ]
            if cookies_from_browser:
                cmd_cover += ["--cookies-from-browser", cookies_from_browser]
            if cookies_file:
                cmd_cover += ["--cookies", cookies_file]
                
            run_command(cmd_cover)
            
            # Check for result (yt-dlp appends extension)
            possible_covers = glob.glob(f"{cover_temp}.*")
            if possible_covers:
                cover_path = possible_covers[0]
                logger.info(f"✅ Downloaded cover: {cover_path}")
            else:
                logger.warning("⚠️ Failed to download cover.")
                
        return final_path, all_chapters, playlist_title, uploader, cover_path

    # 2. Download audio with session-specific filenames
    logger.info(f"📡 Downloading {'playlist' if is_playlist else 'audio'} ({len(entries)} items)...")
    
    if is_playlist:
        # Use session ID to ensure uniqueness across concurrent downloads
        template = os.path.join(output_dir, f"yt_part_{session_id}_%(playlist_index)03d_%(id)s.%(ext)s")
    else:
        template = os.path.join(output_dir, f"yt_download_{session_id}_%(id)s.%(ext)s")

    cmd_dl = yt_dlp_cmd + [
        "-f", selected_format, "-x", "--audio-format", "mp3", 
        "-o", template,
        "--no-cache-dir",
        "--geo-bypass",
        "--concurrent-fragments", "5",
        "--js-runtimes", "node",
        "--remote-components", "ejs:github",
        "--extractor-args", "youtube:player_client=web,tv",
        "--write-thumbnail", "--convert-thumbnails", "jpg"
    ]
    
    if is_playlist and playlist_items_str:
        cmd_dl += ["--playlist-items", playlist_items_str]
        
    cmd_dl.append(url)
    
    if cookies_from_browser:
        cmd_dl += ["--cookies-from-browser", cookies_from_browser]
    if cookies_file:
        cmd_dl += ["--cookies", cookies_file]
    
    # Use capture_output=False to show the yt-dlp progress bar
    res_dl = run_command(cmd_dl, capture_output=False)
    if res_dl.returncode != 0:
        logger.error(f"❌ yt-dlp download failed: {res_dl.stderr}")
        return None

    # 3. Process downloads and merge - use session-specific pattern
    downloaded_files = []
    cover_path = None
    
    if is_playlist:
        # Resolve filenames based on the reordered entries
        # We look for files matching the ORIGINAL index of each entry
        for entry in entries:
            orig_idx = entry.get('_original_index')
            if orig_idx:
                # Find file matching: yt_part_{session_id}_{orig_idx:03d}_*.mp3
                pattern = os.path.join(output_dir, f"yt_part_{session_id}_{orig_idx:03d}_*.mp3")
                matches = glob.glob(pattern)
                if matches:
                    downloaded_files.append(matches[0])
                else:
                    logger.warning(f"⚠️ Missing file for entry {orig_idx}: {entry.get('title')}")
            else:
                 # Single video case or missing index logic (fallback)
                 pass

        # Try to find any cover from this session
        covers = glob.glob(os.path.join(output_dir, f"yt_part_{session_id}_*.jpg"))
        if covers:
            cover_path = covers[0]
    else:
        downloaded_files = glob.glob(os.path.join(output_dir, f"yt_download_{session_id}_*.mp3"))
        covers = glob.glob(os.path.join(output_dir, f"yt_download_{session_id}_*.jpg"))
        if covers:
             cover_path = covers[0]

    if not downloaded_files:
        logger.error("❌ Could not find downloaded audio files.")
        return None

    all_chapters = []
    current_offset = 0.0
    
    # Process each downloaded file to build chapters
    for i, file_path in enumerate(downloaded_files):
        duration = get_audio_duration(file_path)
        # Use the ordered entry corresponding to this file
        entry = entries[i] if (i < len(entries)) else info
        
        yt_chapters = entry.get("chapters") or []
        
        if not yt_chapters:
            all_chapters.append({
                "start": current_offset,
                "end": current_offset + duration,
                "title": entry.get("title", f"Part {i+1}")
            })
        else:
            for c in yt_chapters:
                all_chapters.append({
                    "start": float(c["start_time"]) + current_offset,
                    "end": float(c["end_time"]) + current_offset,
                    "title": c.get("title", f"Chapter {len(all_chapters) + 1}")
                })
        
        current_offset += duration

    # Merge files
    if concatenate_audio_files(downloaded_files, final_path):
        logger.info(f"✅ Successfully combined and saved as: {final_path}")
        
        # Clean up chapter titles by removing common prefixes (useful for playlists)
        if is_playlist and len(all_chapters) > 1:
            all_chapters = clean_chapter_titles(all_chapters)
            
        return final_path, all_chapters, playlist_title, uploader, cover_path
    else:
        logger.error("❌ Failed to concatenate audio files.")
        return (downloaded_files[0] if downloaded_files else None), all_chapters, playlist_title, uploader, cover_path
