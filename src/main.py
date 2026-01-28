import argparse
import os
import sys
import getpass
import json
import logging
import re
from typing import Optional, Tuple, List, Dict, Any
from dotenv import load_dotenv, set_key
from tqdm import tqdm

from src import logging_setup, crypto_utils, io_utils, storytel_api, metadata, audio_utils

ENV_FILE = ".env"

def prompt_credentials() -> Tuple[str, str]:
    print("\n🔐 Service Credentials Required")
    username = input("   Storytel Username: ").strip()
    password = getpass.getpass("   Storytel Password: ").strip()
    return username, password

def save_credentials(username: str, password: str):
    # We save plain password? The request says: "Save provided values into a .env file... Never print password."
    # TS code loads from env. Saving to .env is standard.
    # Note: crypto_utils encrypts it for the API, but we store the original in .env so we can use it next time? 
    # Or do we store the encrypted one?
    # TS code: `const password = process.env.STORYTEL_PASSWORD || ''; const encryptedPassword = encryptPassword(password);`
    # So we must store the PLAIN password in .env for it to work across sessions (unless we change logic to store encrypted, but that breaks compatibility if the key changes, though key is hardcoded). 
    # Standard practice for these tools is storing plain in .env or asking user.
    # I will store plain.
    set_key(ENV_FILE, "STORYTEL_USERNAME", username)
    set_key(ENV_FILE, "STORYTEL_PASSWORD", password)
    logging.info("🔐 Collected credentials interactively and saved to .env")

def fix_chapters_in_folder(root_dir: str):
    """
    Recursively scans for audio files and fixes markers locally using ffmpeg.
    No API calls required.
    """
    logging.info(f"🛠️  Repairing markers in {root_dir}")
    
    count = 0
    for root, dirs, files in os.walk(root_dir):
        for f_name in files:
            if f_name.endswith((".m4b", ".mp4", ".m4a")):
                path = os.path.join(root, f_name)
                logging.info(f"⚙️ Checking chapters in: {f_name}")
                if audio_utils.fix_markers_locally(path):
                    logging.info(f"✅ Repaired locally: {f_name}")
                    count += 1
    
    logging.info(f"✨ Done. Locally repaired {count} files.")

def main():
    parser = argparse.ArgumentParser(description="Storytel Downloader CLI")
    parser.add_argument("--mode", choices=["audio", "ebook", "both", "fix-chapters"], default="both", help="Download mode")
    parser.add_argument("--input", default=os.path.join("..", "audiobook_urls.txt"), help="Path to input file")
    parser.add_argument("--out", default="./library", help="Output directory root")
    parser.add_argument("--interactive", action="store_true", help="Enable interactive mode")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    
    args = parser.parse_args()
    
    logging_setup.setup_logging(args.debug)
    
    # --- Interactive / Credentials Setup ---
    username = os.getenv("STORYTEL_USERNAME")
    password = os.getenv("STORYTEL_PASSWORD")
    
    # Load .env if exists
    load_dotenv(ENV_FILE)
    # Re-read after load_dotenv
    username = os.getenv("STORYTEL_USERNAME") or username
    password = os.getenv("STORYTEL_PASSWORD") or password
    
    credentials_loaded_from_env = bool(username and password)
    
    if args.interactive:
        print("🛠️  Interactive Mode")
        
        # Mode Selection
        print(f"   Current Mode: {args.mode}")
        new_mode = input("   Enter mode (audio/ebook/both/fix-chapters) [leave empty to keep]: ").strip().lower()
        if new_mode in ["audio", "ebook", "both", "fix-chapters"]:
            args.mode = new_mode
            
        # Input File
        print(f"   Input File: {args.input}")
        new_input = input("   Enter input path [leave empty to keep]: ").strip()
        if new_input:
            args.input = new_input
            
        # Output Dir
        print(f"   Output Dir: {args.out}")
        new_out = input("   Enter output directory [leave empty to keep]: ").strip()
        if new_out:
            args.out = new_out
            
    # Check credentials again, if missing prompt
    if not username or not password:
        username, password = prompt_credentials()
        save_credentials(username, password)
    elif credentials_loaded_from_env:
        logging.info("🔐 Loaded credentials from .env")

    encrypted_password = crypto_utils.encrypt_password(password)
    
    # --- Mode handling ---
    if args.mode == "fix-chapters":
        fix_chapters_in_folder(args.out)
        return

    # --- Login ---
    try:
        jwt = storytel_api.login(username, encrypted_password)
    except Exception:
        logging.critical("❌ Login failed. Exiting.")
        sys.exit(1)
        
    # --- Process URLs ---
    if args.mode == "fix-chapters":
        fix_chapters_in_folder(args.out, jwt)
        return

    if not os.path.exists(args.input):
        logging.error(f"❌ Input file not found: {args.input}")
        sys.exit(1)
        
    urls = io_utils.read_urls(args.input)
    logging.info(f"📂 Found {len(urls)} initial URLs/IDs to process.")
    
    # --- Resolve author/series URLs to book IDs ---
    resolved_books = [] # List of dicts: {"id": ..., "title": ..., "authors": ...}
    
    for url in urls:
        url = url.strip()
        if not url: continue
        
        entity_type = None
        if "/authors/" in url:
            entity_type = "AUTHOR"
        elif "/series/" in url:
            entity_type = "SERIES"
            
        if entity_type:
            # Match ID in author/series URL
            match = re.search(r'[-/](\d+)(?:\?|#|$)', url)
            if match:
                entity_id = match.group(1)
                # Try to extract locale from URL, default to 'eg'
                locale_match = re.search(r'locale=([a-z]{2})', url)
                locale = locale_match.group(1) if locale_match else "eg"
                
                logging.info(f"🔍 Expanding {entity_type} {entity_id} (locale={locale})")
                
                # Define required format identifiers based on mode
                mode_map = {
                    "audio": ["ABOOK"],
                    "ebook": ["EBOOK"],
                    "both": ["ABOOK", "EBOOK"]
                }
                required_formats = mode_map.get(args.mode, ["ABOOK", "EBOOK"])
                
                cursor = ""
                while True:
                    try:
                        data = storytel_api.get_dynamic_book_list(entity_id, entity_type=entity_type, locale=locale, cursor=cursor)
                        dynamic_list = data.get("dynamicBookList", {})
                        items = dynamic_list.get("items", [])
                        for item in items:
                            book_id = item.get("id")
                            if not book_id: continue
                            
                            formats = item.get("formats", [])
                            # Skip if none of the book's formats match our desired mode
                            if not any(f in required_formats for f in formats):
                                logging.debug(f"⏭️  Skipping {item.get('title')} (Format {formats} not in {required_formats})")
                                continue

                            # Store enough info for selection
                            authors = [a.get("name") for a in item.get("authors", [])]
                            resolved_books.append({
                                "id": book_id,
                                "title": item.get("title", "Unknown Title"),
                                "authors": ", ".join(authors) if authors else "Unknown",
                                "available_formats": formats
                            })
                        
                        cursor = dynamic_list.get("nextPageCursor")
                        if not cursor:
                            break
                        logging.debug(f"⏭️  Fetching next page (cursor: {cursor})")
                    except Exception as e:
                        logging.error(f"❌ Failed to expand {entity_type} {entity_id}: {e}")
                        break
            else:
                logging.warning(f"⚠️ Could not extract {entity_type} ID from URL: {url}")
        else:
            # Assume it's a book
            match = re.search(r'[-/](\d+)(?:\?|#|$)', url)
            book_id = None
            if match:
                book_id = match.group(1)
            elif url.isdigit():
                book_id = url
            
            if book_id:
                # We don't have titles for direct IDs without fetching, but we can placeholder
                resolved_books.append({"id": book_id, "title": f"Book ID: {book_id}", "authors": ""})
            else:
                logging.warning(f"⚠️ Skipping invalid URL/ID: {url}")
    
    # Unique the IDs while preserving order
    seen = set()
    final_books = []
    for b in resolved_books:
        if b["id"] not in seen:
            final_books.append(b)
            seen.add(b["id"])

    # --- Interactive Selection ---
    if args.interactive and len(final_books) > 1:
        print(f"\n📚 Found {len(final_books)} books. Select which ones to download:")
        print("   (Enter indices separated by space, or 'all', or a range like '1-5')")
        for i, b in enumerate(final_books, 1):
            fmts = b.get("available_formats", [])
            fmt_str = "/".join([f.title() for f in fmts]) if fmts else "ID"
            print(f"   [{i}] {b['title']} (by {b['authors']}) [{fmt_str}]")
        
        selection_str = input("\n👉 Selection [default: all]: ").strip().lower()
        if selection_str and selection_str != 'all':
            selected_indices = set()
            parts = selection_str.replace(',', ' ').split()
            for part in parts:
                if '-' in part:
                    try:
                        start, end = map(int, part.split('-'))
                        for idx in range(start, end + 1):
                            if 1 <= idx <= len(final_books):
                                selected_indices.add(idx - 1)
                    except ValueError: pass
                else:
                    try:
                        idx = int(part)
                        if 1 <= idx <= len(final_books):
                            selected_indices.add(idx - 1)
                    except ValueError: pass
            
            if selected_indices:
                final_books = [final_books[i] for i in sorted(list(selected_indices))]
            else:
                print("   ⚠️ Invalid selection, downloading all by default.")

    book_ids = [b["id"] for b in final_books]
    logging.info(f"📚 Total books to process: {len(book_ids)}")
    
    # Main Progress Bar
    pbar = tqdm(book_ids, desc="Books", unit="book")
    
    summary_processed = 0
    summary_failed = 0
    
    for book_id in pbar:
        pbar.set_postfix_str(f"ID: {book_id}")
        
        try:
            logging.info(f"🔎 Processing Book ID: {book_id}")
            
            # Fetch Details
            details = storytel_api.get_book_details(book_id, jwt)
            if not details:
                # 404 or failed
                summary_failed += 1
                continue
                
            # Fetch Markers for chapters
            markers = storytel_api.get_audiobook_markers(book_id, jwt)
                
            summary_processed += 1
            
            title = details.get("title") or f"book_{book_id}"
            
            # Determine Author for folder structure
            # Logic: <library_root>/<Author>/<Book Title>/
            # Need to re-extract author similar to metadata.py logic or rely on metadata.py to return it? 
            # metadata.py is for creating the JSON. I should duplicate or share the extraction logic.
            # Let's keep it simple and extract inline as I have the dict.
            author_data = details.get("authors", [])
            author_name = "Unknown Author"
            if isinstance(author_data, list) and author_data:
                author_name = author_data[0].get("name") or "Unknown Author"
            elif isinstance(details.get("author"), dict):
                 author_name = details["author"].get("name") or "Unknown Author"
                 
            # Sanitize paths
            safe_author = io_utils.sanitize_filename(author_name)
            safe_title = io_utils.sanitize_filename(title)
            
            book_dir = os.path.join(args.out, safe_author, safe_title)
            io_utils.ensure_directory(book_dir)
            
            formats_status = []
            
            # Formats loop
            # "Iterate formats -> download"
            # TS logic loops over details.formats
            
            available_formats = details.get("formats", [])
            # Map formats to expected keys
            
            desired_modes = []
            if args.mode in ["audio", "both"]:
                desired_modes.append("abook")
            if args.mode in ["ebook", "both"]:
                desired_modes.append("ebook")

            # Check what's available for this book
            download_actions = [] 
            
            for fmt in available_formats:
                ftype = fmt.get("type")
                if ftype in desired_modes:
                    download_actions.append(fmt)
            
            # Nested progress for current book formats?
            # "Optionally nested progress bar per book for formats"
            
            for fmt in download_actions:
                ftype = fmt.get("type")
                
                status_entry = {
                    "type": ftype,
                    "source": url,
                    "downloaded": False,
                    "filename": None
                }
                
                try:
                    if ftype == "abook":
                        mp3_fname = f"{safe_title}.mp3" 
                        m4b_fname = f"{safe_title}.m4b"
                        target_path = os.path.join(book_dir, mp3_fname)
                        m4b_path = os.path.join(book_dir, m4b_fname)
                        
                        if os.path.exists(m4b_path):
                            logging.info(f"⏭️ Skipping audio download for {book_id}: {m4b_fname} already exists")
                            status_entry["downloaded"] = True
                            status_entry["filename"] = m4b_fname
                        else:
                            if os.path.exists(target_path):
                                logging.info(f"⏭️ Skipping audio download for {book_id}: {mp3_fname} already exists, proceeding to conversion")
                            else:
                                storytel_api.download_audiobook(book_id, jwt, target_path)
                            
                            # Convert to M4B if we have markers or just for better format
                            book_metadata = metadata.extract_metadata_dict(details, formats_status)
                            
                            current_fname = mp3_fname
                            if audio_utils.convert_to_m4b(target_path, m4b_path, markers, book_metadata):
                                # Remove original mp3 and update status
                                if os.path.exists(target_path):
                                    os.remove(target_path)
                                current_fname = m4b_fname
                                
                            status_entry["downloaded"] = True
                            status_entry["filename"] = current_fname
                        
                    elif ftype == "ebook":
                        fname = f"{safe_title}.epub"
                        target_path = os.path.join(book_dir, fname)
                        if os.path.exists(target_path):
                            logging.info(f"⏭️ Skipping ebook download for {book_id}: {fname} already exists")
                            status_entry["downloaded"] = True
                            status_entry["filename"] = fname
                        else:
                            storytel_api.download_ebook(book_id, jwt, target_path)
                            status_entry["downloaded"] = True
                            status_entry["filename"] = fname
                        
                except Exception as e:
                    logging.error(f"❌ Failed to download {ftype} for {book_id}: {e}")
                    # Continue to next format
                    pass
                
                formats_status.append(status_entry)
            
            # --- Cover Image Download ---
            cover_data = details.get("cover", {})
            cover_url = cover_data.get("url")
            if cover_url:
                cover_path = os.path.join(book_dir, "cover.jpg")
                if os.path.exists(cover_path):
                    logging.info(f"⏭️ Skipping cover download for {book_id}: cover.jpg already exists")
                else:
                    try:
                        storytel_api.download_cover(cover_url, cover_path)
                    except Exception as e:
                        logging.error(f"❌ Failed to download cover for {book_id}: {e}")

            # Generate Metadata
            metadata.generate_metadata_json(details, book_dir, formats_status)
            
        except Exception as e:
            logging.error(f"❌ Error processing book {book_id}: {e}")
            summary_failed += 1
            if args.debug:
                import traceback
                traceback.print_exc()
                
    logging.info(f"✨ Done. Processed: {summary_processed}, Failed: {summary_failed}")

if __name__ == "__main__":
    main()
