import logging
import requests
import uuid
from typing import Any, Dict, List, Optional
from tqdm import tqdm
import os

USER_AGENT = "Storytel/24.22 (Android 14; Google Pixel 8 Pro) Release/2288629"

def get_common_headers(jwt: Optional[str] = None) -> Dict[str, str]:
    headers = {
        "User-Agent": USER_AGENT,
    }
    if jwt:
        headers["Authorization"] = f"Bearer {jwt}"
    return headers

def login(username: str, encrypted_password: str) -> str:
    """
    Logs in to Storytel and returns the JWT token.
    """
    device_id = str(uuid.uuid4())
    login_url = (
        "https://www.storytel.com/api/login.action?"
        "m=1&token=guestsv&userid=-1&version=24.22&terminal=android&locale=sv"
        f"&deviceId={device_id}&kidsMode=false"
    )
    
    headers = {
        "User-Agent": USER_AGENT,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    data = {
        "uid": username,
        "pwd": encrypted_password
    }
    
    logging.debug(f"🔐 Logging in as {username} (Device ID: {device_id})")
    
    try:
        response = requests.post(login_url, headers=headers, data=data)
        logging.debug(f"RAW LOGIN RESPONSE: {response.text}")
        response.raise_for_status()
        
        user_data = response.json()
        jwt = user_data.get("accountInfo", {}).get("jwt")
        if not jwt:
            raise ValueError("JWT not found in login response")
            
        logging.info("✅ Successfully signed in!")
        return jwt
    except requests.exceptions.RequestException as e:
        status = e.response.status_code if e.response else "Unknown"
        logging.error(f"❌ Login failed (Status: {status}): {e}")
        if e.response:
            logging.debug(f"Response body: {e.response.text}")
        raise

def get_book_details(book_id: str, jwt: str) -> Dict[str, Any]:
    """
    Fetches book details by ID.
    """
    url = f"https://api.storytel.net/book-details/consumables/{book_id}?kidsMode=false&configVariant=default"
    headers = get_common_headers(jwt)
    
    logging.debug(f"📘 Fetching details for ID: {book_id}")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            logging.warning(f"⚠️ Book not found: {book_id}")
            return None
        
        logging.debug(f"RAW BOOK DETAILS RESPONSE: {response.text}")
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        logging.error(f"❌ Failed to get book details for {book_id}: {e}")
        raise

def _download_stream(url: str, target_path: str, headers: Dict[str, str], desc: str = "Downloading"):
    """
    Internal helper to stream download content to a file with a progress bar.
    """
    temp_path = target_path + ".part"
    try:
        with requests.get(url, headers=headers, stream=True) as r:
            r.raise_for_status()
            total_size = int(r.headers.get('content-length', 0))
            
            with open(temp_path, 'wb') as f, tqdm(
                desc=desc,
                total=total_size,
                unit='iB',
                unit_scale=True,
                unit_divisor=1024,
                leave=False # Don't leave nested bars
            ) as bar:
                for chunk in r.iter_content(chunk_size=8192):
                    if chunk:
                        size = f.write(chunk)
                        bar.update(size)
                        
        os.rename(temp_path, target_path)
    except Exception as e:
        logging.error(f"❌ Download failed for {desc}: {e}")
        if os.path.exists(temp_path):
            os.remove(temp_path)
        raise

def download_audiobook(book_id: str, jwt: str, target_path: str):
    """
    Downloads audiobook. Expects strict 302 redirect.
    """
    url_endpoint = f"https://api.storytel.net/assets/v2/consumables/{book_id}/abook"
    headers = get_common_headers(jwt)
    
    logging.debug(f"🎧 Requesting audio URL: {url_endpoint}")
    
    try:
        # TS code: method='GET', redirect='manual'. 
        # Requests follows redirects by default, need allow_redirects=False
        response = requests.get(url_endpoint, headers=headers, allow_redirects=False)
        
        if response.status_code != 302:
            raise ValueError(f"Expected 302 redirect for audio, got {response.status_code}")
            
        location = response.headers.get('Location')
        if not location:
            raise ValueError("Redirect Location header not found")
            
        logging.debug(f"🎧 Redirecting to: {location}")
        _download_stream(location, target_path, headers, desc="🎧 Audio")
        logging.info(f"🎧 Audiobook downloaded: {os.path.basename(target_path)}")
        
    except Exception as e:
        logging.error(f"❌ Failed to download audiobook for {book_id}: {e}")
        raise

def get_audiobook_markers(book_id: str, jwt: str) -> List[Dict[str, Any]]:
    """
    Fetches chapter markers for the audiobook using the playback-metadata endpoint.
    """
    url = f"https://api.storytel.net/playback-metadata/consumable/{book_id}"
    headers = get_common_headers(jwt)
    
    logging.debug(f"📑 Fetching markers for ID: {book_id}")
    
    try:
        response = requests.get(url, headers=headers)
        if response.status_code == 404:
            logging.warning(f"⚠️ Markers not found for book: {book_id}")
            return []
            
        logging.debug(f"RAW MARKERS RESPONSE: {response.text}")
        response.raise_for_status()
        data = response.json()
        
        # Find abook format
        formats = data.get("formats", [])
        abook_format = next((f for f in formats if f.get("type") == "abook"), None)
        
        if not abook_format:
            logging.warning(f"⚠️ No 'abook' format found in playback metadata for: {book_id}")
            return []
            
        chapters = abook_format.get("chapters", [])
        markers = []
        current_time_ms = 0
        
        for i, chapter in enumerate(chapters):
            title = chapter.get("title")
            if not title:
                number = chapter.get("number")
                title = f"Chapter {number}" if number is not None else f"Chapter {i+1}"
                
            markers.append({
                "title": title,
                "startTime": current_time_ms
            })
            # Add duration of current chapter to find next chapter's start time
            # The sample response shows durationInMilliseconds
            duration = chapter.get("durationInMilliseconds", 0)
            current_time_ms += duration
            
        return markers
    except Exception as e:
        logging.error(f"❌ Failed to get markers for {book_id}: {e}")
        return []

def download_ebook(book_id: str, jwt: str, target_path: str):
    """
    Downloads ebook. Handles 302 redirect OR direct 200 content.
    """
    url_endpoint = f"https://api.storytel.net/assets/v2/consumables/{book_id}/ebook"
    headers = get_common_headers(jwt)
    
    logging.debug(f"📚 Requesting ebook URL: {url_endpoint}")
    
    try:
        response = requests.get(url_endpoint, headers=headers, allow_redirects=False)
        
        download_url = None
        
        if response.status_code == 302:
            location = response.headers.get('Location')
            if not location:
                raise ValueError("Redirect Location header not found for ebook")
            download_url = location
            logging.debug(f"📚 Redirecting to: {location}")
        elif response.status_code == 200:
             # Direct content? TS says: "If it's not a redirect but still OK, it might be the direct content"
             # But the TS implementation calls `response.arrayBuffer()` immediately.
             # My _download_stream helper makes a *new* GET request. 
             # If `response` already HAS the content (streaming or not), I shouldn't make a new request to the same URL if it's not a restartable stream or if I already consumed it (I haven't consumed it yet if I didn't access .content).
             # However, `response` here was made with stream=False (default).
             # If I want to stream it, I should have made the initial request with stream=True?
             # But I needed to check status code first to decide logic.
             # If 200, the content is in `response`. If I did `stream=True`, I could read `response.raw`.
             # Let's refactor to support this case cleanly.
             pass
        else:
             raise ValueError(f"Unexpected status for ebook: {response.status_code}")

        if download_url:
             _download_stream(download_url, target_path, headers, desc="📚 Ebook")
        else:
             # It was a 200 direct response.
             # If the initial request wasn't streamed, we might have the whole body in memory if we access .content, 
             # but we strictly avoided that.
             # Given the likely size of ebooks (small), it's probably fine to just save it.
             # But for consistency, let's treat it properly.
             # Re-requesting might be safer if we want to show progress bar, OR we just write what we have.
             # "ebook endpoint... return direct content"
             # Let's restart the request with stream=True if we want a progress bar, 
             # OR since we already made the request (without stream=True), requests downloaded it?
             # Default requests.get is not streaming, so it downloads body immediately.
             # So we already have it.
             with open(target_path, 'wb') as f:
                 f.write(response.content)
             logging.info(f"📚 Ebook downloaded (direct): {os.path.basename(target_path)}")

    except Exception as e:
        logging.error(f"❌ Failed to download ebook for {book_id}: {e}")
        raise

def download_cover(url: str, target_path: str):
    """
    Downloads the cover image from a given URL.
    """
    headers = {
        "User-Agent": USER_AGENT
    }
    logging.debug(f"🖼️ Downloading cover from: {url}")
    try:
        response = requests.get(url, headers=headers)
        response.raise_for_status()
        with open(target_path, 'wb') as f:
            f.write(response.content)
        logging.info(f"🖼️ Cover image saved: {os.path.basename(target_path)}")
    except Exception as e:
        logging.error(f"❌ Failed to download cover image: {e}")
        raise
