import json
import logging
import os
from typing import Any, Dict, List

def generate_metadata_json(
    book_details: Dict[str, Any],
    book_dir: str,
    formats_status: List[Dict[str, Any]]
) -> None:
    """
    Generates and saves a metadata.json file in the book directory.
    
    :param book_details: The JSON response from Storytel API (get_book_details)
    :param book_dir: The directory where the book is stored
    :param formats_status: List of dicts describing downloaded formats, e.g.:
           [
             {"type": "abook", "source": "...", "downloaded": True, "filename": "audio.mp3"},
             {"type": "ebook", "source": "...", "downloaded": False, "filename": "ebook.epub"}
           ]
    """
    
def extract_metadata_dict(book_details: Dict[str, Any], formats_status: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Common extraction logic for metadata.
    """
    # Extract fields with safe fallbacks
    title = book_details.get("title")
    
    # Helper to parse authors list
    authors = []
    if "authors" in book_details and isinstance(book_details["authors"], list):
        authors = [a.get("name") for a in book_details["authors"] if a.get("name")]
    elif "author" in book_details and isinstance(book_details["author"], dict):
         authors = [book_details["author"].get("name")]
    
    author_str = ", ".join(filter(None, authors)) if authors else "Unknown Author"

    # Narrators
    narrators = []
    if "narrators" in book_details and isinstance(book_details["narrators"], list):
        narrators = [n.get("name") for n in book_details["narrators"] if n.get("name")]
    narrator_str = ", ".join(filter(None, narrators)) if narrators else None

    # Series
    series_name = None
    if "series" in book_details and book_details["series"]:
        series_obj = book_details["series"]
        if isinstance(series_obj, dict):
            series_name = series_obj.get("name")
        elif isinstance(series_obj, list) and len(series_obj) > 0:
            series_name = series_obj[0].get("name")

    # Publishing info
    published_year = None
    release_date = book_details.get("releaseDate") or book_details.get("originalReleaseDate")
    if release_date and len(str(release_date)) >= 4:
        try:
            published_year = int(str(release_date)[:4])
        except ValueError:
            pass
            
    # Description
    description = book_details.get("description")

    # Genres (Category)
    genres = []
    if "category" in book_details and isinstance(book_details["category"], dict):
        cat_name = book_details["category"].get("name")
        if cat_name:
            genres.append(cat_name)
    elif "categories" in book_details and isinstance(book_details["categories"], list):
         genres = [c.get("name") for c in book_details["categories"] if c.get("name")]

    # Language
    language = book_details.get("language")

    # Provider ID
    provider_id = str(book_details.get("id", ""))
    
    return {
        "title": title,
        "author": author_str,
        "narrator": narrator_str,
        "series": series_name,
        "publishedYear": published_year,
        "description": description,
        "genres": genres,
        "language": language,
        "provider": "Storytel",
        "providerId": provider_id,
        "formats": formats_status
    }

def generate_metadata_json(
    book_details: Dict[str, Any],
    book_dir: str,
    formats_status: List[Dict[str, Any]]
) -> None:
    """
    Generates and saves a metadata.json file in the book directory.
    """
    metadata = extract_metadata_dict(book_details, formats_status)
    
    metadata_path = os.path.join(book_dir, "metadata.json")
    try:
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, indent=2, ensure_ascii=False)
        logging.info(f"📘 Metadata saved: {metadata_path}")
    except Exception as e:
        logging.error(f"❌ Failed to save metadata: {e}")
