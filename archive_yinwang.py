import requests
import json
import os
import time
import re
from urllib.parse import urlparse, unquote, urljoin
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Configuration
DOMAIN = "yinwang.org"
CDX_API_URL = "http://web.archive.org/cdx/search/cdx"
WAYBACK_URL_TEMPLATE = "https://web.archive.org/web/{timestamp}id_/{original}"
OUTPUT_DIR = "archives"
INDEX_FILE = os.path.join(OUTPUT_DIR, "index.json")
MIN_YEAR = "2010"
JUNK_YEAR_START = "2025"

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

def fetch_cdx_records(session, url_pattern, filters=None):
    """Fetch all CDX records for a specific URL pattern."""
    if filters is None:
        filters = ["mimetype:text/html", "statuscode:200"]
        
    params = {
        "url": url_pattern,
        "output": "json",
        "fl": "original,timestamp,mimetype,statuscode,length,digest",
        "filter": filters
    }
    
    print(f"Fetching CDX records for {url_pattern}...")
    try:
        response = session.get(CDX_API_URL, params=params, timeout=30) 
        response.raise_for_status()
        data = response.json()
        if not data:
            return []
        header = data[0]
        rows = data[1:]
        
        records = []
        for row in rows:
            record = dict(zip(header, row))
            try:
                record["length"] = int(record.get("length", 0))
            except:
                record["length"] = 0
            records.append(record)
        return records
    except Exception as e:
        print(f"Error fetching CDX records: {e}")
        time.sleep(2) # Backoff more on error
        return []

def normalize_url(url):
    """Normalize URL to identify unique pages."""
    if "://" in url:
        url = url.split("://", 1)[1]
    if ":" in url:
        parts = url.split("/")
        if ":" in parts[0]:
            parts[0] = parts[0].split(":")[0]
        url = "/".join(parts)
    url = url.rstrip("/")
    try:
        url = unquote(url)
    except:
        pass
    return url

def get_safe_filename(original_url, timestamp):
    parsed = urlparse(original_url)
    path = parsed.path.strip("/")
    if not path:
        path = "index"
    
    # special case for homepage
    p = original_url.lower()
    if p.endswith("yinwang.org") or p.endswith("yinwang.org/"):
        base_name = "homepage"
    else:
        base_name = "".join([c if c.isalnum() or c in "._-" else "_" for c in path])
    
    if base_name.endswith(".html"):
        base_name = base_name[:-5]
        
    date_str = timestamp[:8] if timestamp else "00000000"
    return f"{base_name}_{date_str}.html"

def download_page_content(session, url):
    """Download content from a specific Wayback URL."""
    try:
        response = session.get(url, timeout=30)
        if response.status_code == 200:
            return response.text
    except Exception as e:
        print(f"Error downloading {url}: {e}")
    return None

def extract_links_from_html(html, base_url):
    """Extract all relevant blog links from HTML content."""
    # Regex to find hrefs. Simple but effective for our filtered needs.
    # Looking for /blog-cn/ or potentially other article paths.
    
    # Match href="..." or href='...'
    links = set()
    matches = re.findall(r'href=["\'](.*?)["\']', html, re.IGNORECASE)
    for link in matches:
        full_url = urljoin(base_url, link)
        if "yinwang.org" in full_url:
            # Check if it looks like an article
            # Most articles are in /blog-cn/...
            if "/blog-cn/" in full_url:
                links.add(full_url)
            # Heuristic for other potential articles?
            # Early articles might be elsewhere, but /blog-cn/ is dominat.
            # Let's trust /blog-cn/ for now based on previous file list.
            
    return links

def crawl_homepage_history(session):
    """
    Crawl historical versions of the homepage to discover links.
    """
    print("Starting Homepage Timeline Crawl...")
    
    print("Starting Homepage Timeline Crawl...")
    
    unique_digests = {}
    
    # 1. Load cached snapshots if valid
    if os.path.exists("homepage_snapshots.json"):
        try:
            with open("homepage_snapshots.json", "r") as f:
                saved_snapshots = json.load(f)
                for rec in saved_snapshots:
                    unique_digests[rec['digest']] = rec
            print(f"Loaded {len(unique_digests)} snapshots from cache.")
        except Exception as e:
            print(f"Error loading cache: {e}")

    # 2. Always fetch fresh CDX to find new updates
    print("Fetching fresh CDX records...")
    try:
        records_root = fetch_cdx_records(session, "yinwang.org")
        records_www = fetch_cdx_records(session, "www.yinwang.org")
        all_records = records_root + records_www
        
        new_count = 0
        for rec in all_records:
            if rec.get("length", 0) < 500: continue
            ts = rec.get("timestamp", "")
            if ts < MIN_YEAR or ts >= JUNK_YEAR_START: continue
                
            digest = rec.get("digest")
            if digest not in unique_digests:
                unique_digests[digest] = rec
                new_count += 1
        
        print(f"Merged {new_count} new snapshots from API.")
            
        # 3. Update cache
        with open("homepage_snapshots.json", "w") as f:
            json.dump(list(unique_digests.values()), f)
            
    except Exception as e:
        print(f"Error fetching/merging CDX: {e}")
            
    print(f"Total {len(unique_digests)} unique homepage versions to crawl.")
    
    # 2. Load existing discovered URLs
    discovered_urls = set()
    if os.path.exists("discovered_urls.json"):
        print("Loading discovered URLs from cache...")
        with open("discovered_urls.json", "r") as f:
            discovered_urls = set(json.load(f))
    
    sorted_snapshots = sorted(unique_digests.values(), key=lambda x: x['timestamp'])
    
    for i, snapshot in enumerate(sorted_snapshots):
        ts = snapshot['timestamp']
        orig = snapshot['original']
        wayback_url = WAYBACK_URL_TEMPLATE.format(timestamp=ts, original=orig)
        
        print(f"ts: {ts}")
        print(f"orig: {orig}")
        print(f"wayback_url: {wayback_url}")

        print(f"[{i+1}/{len(sorted_snapshots)}] Scanning homepage snapshot from {ts[:8]}... (looking for links)")
        html = download_page_content(session, wayback_url)
        if html:
            links = extract_links_from_html(html, orig)
            if links:
                print(f"  -> Found {len(links)} links.")
                discovered_urls.update(links)
        if (i + 1) % 10 == 0:
            print(f"  (Saving progress... found {len(discovered_urls)} links)")
            with open("discovered_urls.json", "w") as f:
                json.dump(list(discovered_urls), f)
        time.sleep(0.1)
        
    print(f"Timeline Crawl complete. Discovered {len(discovered_urls)} unique article URLs.")
    return discovered_urls

def process_discovered_urls(discovered_urls):
    """
    Convert discovered URLs into pseudo-CDX records so they can be processed by existing logic.
    Since we don't have CDX records for these yet, we might need to fetch them?
    Actually, we should add these URLs to the "to be fetched" list.
    BUT, we want to download the *best snapshot* for these URLs.
    So for every discovered URL, we should query CDX to get its available snapshots.
    This might be too many requests if we found 500 links -> 500 CDX queries.
    
    Alternative: We already did a wildcard query `yinwang.org/*`.
    We should check if these discovered URLs are already in our wildcard list.
    If yes, we are good.
    If no, THEN we query CDX for that specific URL.
    """
    return list(discovered_urls)

def main():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)

    session = get_session()

    # 1. Wildcard Search (Existing)
    wildcard_records = fetch_cdx_records(session, DOMAIN + "/*")
    print(f"Wildcard search found {len(wildcard_records)} records.")

    # 2. Homepage Timeline Crawl (New)
    discovered_urls = crawl_homepage_history(session)
    
    # 3. Merge & Check for missing
    # Normalize wildcard records to a set of URLs
    known_urls_map = {} # normalized -> list of records
    for rec in wildcard_records:
        norm = normalize_url(rec['original'])
        if norm not in known_urls_map:
            known_urls_map[norm] = []
        known_urls_map[norm].append(rec)
        
    # Check discovered against known
    new_urls_to_fetch = []
    for url in discovered_urls:
        norm = normalize_url(url)
        if norm not in known_urls_map:
            print(f"New URL discovered: {url}")
            new_urls_to_fetch.append(url)
            
    # 4. Fetch CDX for new URLs
    if new_urls_to_fetch:
        print(f"Fetching CDX for {len(new_urls_to_fetch)} new URLs...")
        for url in new_urls_to_fetch:
            new_recs = fetch_cdx_records(session, url)
            if new_recs:
                norm = normalize_url(url)
                if norm not in known_urls_map:
                     known_urls_map[norm] = []
                known_urls_map[norm].extend(new_recs)
            time.sleep(1)

    # 5. Filter & Select Best Snapshots (Unified)
    # Flatten the map back to a list of records (conceptually)
    # Actually, let's just pick the best for each normalized URL from the map directly
    
    final_snapshots = []
    for norm_url, candidates in known_urls_map.items():
        # Dedup logic from before
        candidates.sort(key=lambda x: x['timestamp']) # Sort by time ascending
        
        seen_digests = set()
        for cand in candidates:
            # Filter junk during selection
            if cand['timestamp'] < MIN_YEAR or cand['timestamp'] >= JUNK_YEAR_START:
                continue

            if "blog-cn" not in norm_url and len(norm_url) > 30 and not norm_url.endswith(".html"):
                 pass

            # Validity check: must be reasonable size
            if cand['length'] > 1500:
                digest = cand.get('digest')
                if digest not in seen_digests:
                    seen_digests.add(digest)
                    final_snapshots.append(cand)
        
        # If nothing valid found, maybe keep the largest one as fallback?
        if not seen_digests and candidates:
             candidates.sort(key=lambda x: x['length'], reverse=True)
             final_snapshots.append(candidates[0])

    print(f"Total unique pages to download: {len(final_snapshots)}")
    final_snapshots.sort(key=lambda x: x['original'])
    
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(final_snapshots, f, indent=2)
        
    # 6. Download
    # 6. Download with Multi-threading
    # 6. Download with Multi-threading
    print(f"Starting download with 10 threads...")
    
    import concurrent.futures
    import threading
    
    success_count = [0]
    fail_count = [0]
    lock = threading.Lock()
    total_files = len(final_snapshots)
    
    # Timeout configuration (5.5 hours = 19800 seconds to be safe within 6h limit)
    TIMELIMIT = 19800 
    start_time = time.time()
    stop_event = threading.Event()
    
    def download_wrapper(snapshot):
        if stop_event.is_set():
            return

        # Check timeout
        if time.time() - start_time > TIMELIMIT:
            if not stop_event.is_set():
                stop_event.set()
                print("\n!!! TIME LIMIT REACHED. Stopping new downloads to save progress. !!!\n")
            return

        original_url = snapshot.get("original")
        timestamp = snapshot.get("timestamp")
        target_url = WAYBACK_URL_TEMPLATE.format(timestamp=timestamp, original=original_url)
        
        filename = os.path.join(OUTPUT_DIR, get_safe_filename(original_url, timestamp))
        
        should_download = True
        if os.path.exists(filename):
            try:
                if os.path.getsize(filename) > 1000:
                    should_download = False
            except:
                pass
        
        if should_download:
             try:
                res = session.get(target_url, timeout=30)
                if res.status_code == 200:
                    with open(filename, "w", encoding="utf-8") as f:
                        f.write(res.text)
                    with lock:
                        success_count[0] += 1
                        print(f"[{success_count[0] + fail_count[0]}/{total_files}] Downloaded {original_url} ({timestamp})")
                    time.sleep(0.1) # Be nice
                else:
                    with lock:
                        fail_count[0] += 1
                        print(f"[{success_count[0] + fail_count[0]}/{total_files}] Failed: {res.status_code} for {original_url}")
             except Exception as e:
                 with lock:
                     fail_count[0] += 1
                     print(f"Error downloading {original_url}: {e}")
        else:
            with lock:
                success_count[0] += 1

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        executor.map(download_wrapper, final_snapshots)

    print(f"Process complete. Total: {total_files}, Success: {success_count[0]}, Failed: {fail_count[0]}")

def cleanup_old_archives():
    """Remove files in archives/ that are older than MIN_YEAR."""
    print(f"Cleaning up archives older than {MIN_YEAR}...")
    if not os.path.exists(OUTPUT_DIR):
        print("Archives directory not found, skipping cleanup.")
        return

    count = 0
    for filename in os.listdir(OUTPUT_DIR):
        filepath = os.path.join(OUTPUT_DIR, filename)
        if not os.path.isfile(filepath):
            continue
            
        # Extract date from filename: name_20060213.html
        match = re.search(r'_(\d{8})\.html$', filename)
        if match:
            date_str = match.group(1)
            year = date_str[:4]
            
            if year < MIN_YEAR:
                try:
                    os.remove(filepath)
                    # print(f"Deleted old file: {filename}")
                    count += 1
                except Exception as e:
                    print(f"Error deleting {filename}: {e}")
    
    if count > 0:
        print(f"Cleanup complete. Deleted {count} files older than {MIN_YEAR}.")
    else:
        print("Cleanup complete. No old files found.")

if __name__ == "__main__":
    # Run cleanup before main process or after? 
    # Better run it first to clear out junk.
    cleanup_old_archives()
    main()
