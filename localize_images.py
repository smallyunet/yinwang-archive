import os
import re
import requests
import time
from urllib.parse import urlparse, urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
ARCHIVES_DIR = "archives"
IMAGES_DIR = os.path.join(ARCHIVES_DIR, "images")
WAYBACK_URL_TEMPLATE = "https://web.archive.org/web/{timestamp}im_/{original}"

def get_session():
    """Create a requests session with retry logic."""
    session = requests.Session()
    retries = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504],
        allowed_methods=["GET"]
    )
    adapter = HTTPAdapter(max_retries=retries)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def parse_timestamp_from_filename(filename):
    """
    Extract timestamp from filename or metadata.
    Filename format: blog-cn_YYYY_MM_DD_slug.html
    We need a full 14-digit timestamp for Wayback.
    We can approximate it as YYYYMMDD000000 or use a known close date.
    Ideally, we should rely on the index.json, but reading files is easier for now.
    """
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}{match.group(2)}{match.group(3)}000000"
    # Fallback default
    return "20150101000000" 

def download_image(session, img_url, timestamp, save_path):
    if os.path.exists(save_path):
        return True
        
    # Construct Wayback URL
    # Handle protocol-relative URLs
    if img_url.startswith("//"):
        img_url = "http:" + img_url
        
    wayback_url = WAYBACK_URL_TEMPLATE.format(timestamp=timestamp, original=img_url)
    print(f"Downloading image: {img_url} from {wayback_url}")
    
    try:
        response = session.get(wayback_url, timeout=30)
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            time.sleep(0.5)
            return True
        elif response.status_code == 404:
             # Try a different timestamp? Or without timestamp redirects?
             print(f"Image not found at {timestamp}, trying current...")
             # Just try raw URL, maybe it's still there? Unlikely for 404s on WB.
             pass
    except Exception as e:
        print(f"Error downloading image {img_url}: {e}")
    return False

def process_file(session, filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()
    except Exception as e:
        print(f"Skipping {filepath}: {e}")
        return
        
    # Find all images
    # Regex for <img src="...">
    # Captures src value
    img_tags = re.findall(r'<img[^>]+src=["\'](.*?)["\']', content, re.IGNORECASE)
    
    if not img_tags:
        return
        
    timestamp = parse_timestamp_from_filename(os.path.basename(filepath))
    modified_content = content
    has_changes = False
    
    for img_src in img_tags:
        # Determine strictness: only download if it looks like a yinwang.org image?
        # Yes, ignore external tracking pixels etc.
        if "yinwang.org" in img_src or img_src.startswith("/images/"):
             # It's an internal image
             
             # Clean URL
             full_url = img_src
             if img_src.startswith("/"):
                 full_url = "http://www.yinwang.org" + img_src
             
             # Filename for local storage
             img_name = os.path.basename(urlparse(full_url).path)
             if not img_name: continue
             
             # Handle query params if any
             img_name = img_name.split("?")[0]
             
             local_path = os.path.join(IMAGES_DIR, img_name)
             
             success = download_image(session, full_url, timestamp, local_path)
             
             if success:
                 # Update HTML
                 new_src = f"images/{img_name}"
                 # Replace carefully
                 modified_content = modified_content.replace(img_src, new_src)
                 has_changes = True
    
    if has_changes:
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(modified_content)
        print(f"Updated {filepath}")

def main():
    if not os.path.exists(IMAGES_DIR):
        os.makedirs(IMAGES_DIR)
        
    session = get_session()
    
    files = [f for f in os.listdir(ARCHIVES_DIR) if f.endswith(".html")]
    print(f"Scanning {len(files)} files for images...")
    
    for filename in files:
        filepath = os.path.join(ARCHIVES_DIR, filename)
        process_file(session, filepath)
        
    print("Image localization complete.")

if __name__ == "__main__":
    main()
