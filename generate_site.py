import shutil
import os
import re
import hashlib
from datetime import datetime

ARCHIVES_DIR = "archives"
OUTPUT_DIR = "docs"
INDEX_OUTPUT = os.path.join(OUTPUT_DIR, "index.html")
STYLE_OUTPUT = os.path.join(OUTPUT_DIR, "style.css")

DOMAIN = "yinwang.org"

def parse_article_date(filename):
    """
    Parses the article date (publication date) from the filename.
    Typically finds the first YYYY_MM_DD or YYYYMMDD pattern.
    """
    # Try YYYY_MM_DD
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    
    # Try YYYYMMDD (often at end of filename or after underscore)
    match = re.search(r'_(\d{4})(\d{2})(\d{2})', filename)
    if match:
         return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
         
    return None

def strip_tags(text):
    """Removes HTML tags from a string."""
    clean = re.compile('<.*?>')
    return re.sub(clean, '', text)

def extract_title(content, filename):
    # Try to find h1
    match = re.search(r'<h1[^>]*>(.*?)</h1>', content, re.IGNORECASE | re.DOTALL)
    if match:
        return strip_tags(match.group(1)).strip()
    
    # Try title tag
    match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    if match:
        title = strip_tags(match.group(1)).strip()
        if title and title.lower() != 'untitled':
            return title

    # Fallback to filename
    base = os.path.basename(filename)
    # Remove extension and potential date suffix
    base = re.sub(r'(_\d{8})?\.html$', '', base)
    # Improve readability for resource files (e.g. replacing separators)
    clean_name = base.replace('resources_', '').replace('_', ' ').replace('-', ' ')
    if clean_name.strip():
        return clean_name.title()
    
    return "Untitled"

def get_base_name_and_version(filename):
    """
    Returns (base_name, version_date_str)
    e.g. blog-cn_..._20140722.html -> (blog-cn_..., 20140722)
    """
    match = re.search(r'^(.*)_(\d{8})\.html$', filename)
    if match:
        return match.group(1), match.group(2)
    return filename, "00000000"

def extract_metadata(content, filename):
    """
    Extract date and title from content.
    Returns a dict with 'date' (YYYY-MM-DD or None) and 'title'.
    """
    title = extract_title(content, filename)
    
    # Try to find date in content (common yinwang patterns)
    # Pattern 1: <h2>Date</h2> or <div class="date">
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', content)
    date = None
    if date_match:
        date = date_match.group(1).replace('/', '-')
    else:
        # Fallback: Extract date from filename (e.g., _20130504.html)
        filename_date_match = re.search(r'_(\d{8})\.html$', filename)
        if filename_date_match:
            d_str = filename_date_match.group(1)
            date = f"{d_str[:4]}-{d_str[4:6]}-{d_str[6:]}"

    return {
        'date': date,
        'title': title
    }

def format_version_date(date_str):
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str



def try_fix_mojibake(text):
    """
    Attempts to fix Mojibake (UTF-8 bytes decoded as Latin-1).
    Heuristic: 
    1. If the text can be encoded to latin-1 (meaning it only contains 0-255 chars),
    2. AND those bytes can be validly decoded as utf-8,
    3. AND the length changes (usually gets shorter as multibyte chars combine),
    Then assume it was Mojibake and return the fixed text.
    """
    try:
        # If text contains real Chinese characters, this will fail (which is good)
        bytes_content = text.encode('latin-1')
        fixed = bytes_content.decode('utf-8')
        # If we got here, it's valid UTF-8. 
        # Double check: usually fixing mojibake reduces length (3 chars -> 1 char)
        if len(fixed) < len(text):
            return fixed
    except Exception:
        pass
    return text


def get_body_content(text):
    """Extracts content inside <body> tags."""
    match = re.search(r'<body[^>]*>(.*?)</body>', text, re.DOTALL | re.IGNORECASE)
    if match:
        return match.group(1).strip()
    return text

def normalize_html(text):
    """Removes whitespace for robust comparison."""
    return re.sub(r'\s+', '', text)

def clean_html_attributes(content):
    # Remove <style> blocks
    content = re.sub(r'<style.*?>.*?</style>', '', content, flags=re.DOTALL | re.IGNORECASE)
    
    # Remove style="..." attributes
    content = re.sub(r'\s+style\s*=\s*(["\']).*?\1', '', content, flags=re.IGNORECASE)
    
    # Remove width and border from table attributes
    def clean_tag(match):
        tag_text = match.group(0)
        tag_text = re.sub(r'\s+width\s*=\s*(["\']).*?\1', '', tag_text, flags=re.IGNORECASE)
        tag_text = re.sub(r'\s+border\s*=\s*(["\']).*?\1', '', tag_text, flags=re.IGNORECASE)
        return tag_text

    content = re.sub(r'<(table|td|th|tr|tbody|thead|tfoot)\b[^>]*>', clean_tag, content, flags=re.IGNORECASE)
    
    return content

def unwrap_layout(content):
    """
    If checks for the pattern <table>...<td>...<div><h2>...
    If found, extracts that inner div, effectively discarding the table wrapper and sidebar.
    """
    # Look for the innermost div that contains an h2 (the title).
    # This is a heuristic: the real content usually starts with the title in an h2.
    
    # First, simple check: is there a table?
    if '<table' not in content.lower():
        return content
        
    # Regex to find the div wrapping the title.
    # We look for <div ...> ... <h2>Title</h2> ... </div>
    # But regex for balanced tags is hard. 
    # Alternative strategy: 
    # The structure is usually: <body> <div> <table> <tr> <td> <div ...> <h2>...</h2> ... </div> ...
    # We can try to match the specific legacy structure.
    
    # Find the block containing the H2 title
    match = re.search(r'(<div[^>]*>\s*<h2.*?>.*?</div>)', content, re.IGNORECASE | re.DOTALL)
    if match:
        # Check if this div is inside a table (heuristic)
        # Actually, if we found a div with h2, and the total length is significantly smaller than content,
        # it might be the extraction we want.
        extracted = match.group(1)
        
        # Verify it's not just the title but the whole article.
        # In the files observed, the whole article body is in that one div.
        # Let's verify length ratio to be safe, or just trust the H2 presence in legacy files.
        if len(extracted) > len(content) * 0.1: # It should be a substantial part of the page
             return f"<body>{extracted}</body>"
             
    return content


def process_archives():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"Processing archives from {ARCHIVES_DIR}...")
    
    # 1. Copy Assets
    src_images = os.path.join(ARCHIVES_DIR, "images")
    dst_images = os.path.join(OUTPUT_DIR, "images")
    if os.path.exists(src_images):
        if os.path.exists(dst_images):
            shutil.rmtree(dst_images)
        shutil.copytree(src_images, dst_images)

    theme_source = os.path.join("demo", "yinwang", "source")
    for asset_type in ["css", "js"]:
        src = os.path.join(theme_source, asset_type)
        dst = os.path.join(OUTPUT_DIR, asset_type)
        if os.path.exists(src):
            if os.path.exists(dst):
                shutil.rmtree(dst)
            shutil.copytree(src, dst)

    # 2. Group files
    article_groups = {} 
    page_groups = {}    
    
    for f in os.listdir(ARCHIVES_DIR):
        if not f.endswith(".html") or f.startswith("index.json"): # Skip index.json but keep index_*.html
            continue
            
        base_name, version_date = get_base_name_and_version(f)
        
        if f.startswith("blog-cn"):
            if base_name not in article_groups:
                article_groups[base_name] = []
            article_groups[base_name].append(f)
        else:
            if base_name not in page_groups:
                page_groups[base_name] = []
            page_groups[base_name].append(f)

    # 3. Analyze & Deduplicate (Load into memory)
    # Structure: processed_groups = { base_name: { 'type': 'article'|'page', 'versions': [...], 'latest': {...} } }
    processed_groups = {}

    def analyze_group(groups, type_label):
        for base_name, files in groups.items():
            files.sort(key=lambda x: get_base_name_and_version(x)[1])
            
            unique_versions = [] 
            seen_hashes = set()
            
            for filename in files:
                filepath = os.path.join(ARCHIVES_DIR, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
                        content = f.read()
                    
                    content = try_fix_mojibake(content)
                    content = unwrap_layout(content)
                    content = clean_html_attributes(content)
                    body_content = get_body_content(content)
                    norm_body = normalize_html(body_content)
                    content_hash = hashlib.sha256(norm_body.encode('utf-8')).hexdigest()
                    
                    if content_hash not in seen_hashes:
                        _, ver_date = get_base_name_and_version(filename)
                        unique_versions.append({
                            'filename': filename,
                            'content': content,
                            'date': ver_date,
                            'formatted_date': format_version_date(ver_date)
                        })
                        seen_hashes.add(content_hash)
                except Exception as e:
                    print(f"Error reading {filename}: {e}")
            
            if unique_versions:
                latest = unique_versions[-1]
                # Pre-calculate title for layout
                title = extract_title(latest['content'], latest['filename'])
                processed_groups[base_name] = {
                    'type': type_label,
                    'versions': unique_versions,
                    'latest_meta': {
                        'filename': latest['filename'],
                        'title': title,
                        'date': parse_article_date(latest['filename']),
                        'sort_date': parse_article_date(latest['filename']) or "1970-01-01"
                    }
                }

    print("Analyzing articles...")
    analyze_group(article_groups, 'article')
    print("Analyzing pages...")
    analyze_group(page_groups, 'page')

    # 4. Build Navbar
    # We want valid links to the 'latest' version of each page.
    # Grouping logic:
    # - Tweets (tweet) -> "MicroBlog"
    # - History (homepage*, index*) -> "History" dropdown
    # - Posts (posts_*) -> "Posts" dropdown
    # - Resources (resources_*) -> "Resources" dropdown
    # - Tags (tags_*) -> "Tags" dropdown
    # - About (about*) -> "About"
    # - Misc -> "More" dropdown
    
    nav_structure = {
        'top': [],
        'History': [],
        'Posts': [],
        'Resources': [],
        'Tags': [],
        'Misc': []
    }
    
    page_keys = [k for k, v in processed_groups.items() if v['type'] == 'page']
    page_keys.sort()
    
    for base_name in page_keys:
        meta = processed_groups[base_name]['latest_meta']
        link = meta['filename']
        title = meta['title'] or base_name
        
        # Clean title if it looks like a filename
        if title == base_name or title.endswith('.html'):
             title = base_name.replace('_', ' ').title()

        if base_name.startswith('tweet'):
            nav_structure['top'].append({'url': link, 'label': 'Tweets'})
        elif base_name.startswith('about'):
             nav_structure['top'].append({'url': link, 'label': 'About'})
        elif base_name.startswith('homepage') or base_name.startswith('index'):
            nav_structure['History'].append({'url': link, 'label': f"{title} ({meta['date']})"})
        elif base_name.startswith('posts_'):
            nav_structure['Posts'].append({'url': link, 'label': title})
        elif base_name.startswith('resources_'):
             nav_structure['Resources'].append({'url': link, 'label': title})
        elif base_name.startswith('tags_'):
             nav_structure['Tags'].append({'url': link, 'label': title})
        else:
            nav_structure['Misc'].append({'url': link, 'label': title})


    def build_nav_html():
        html = "<ul class='nav navbar-nav navbar-right'>"
        html += "<li class='active'><a href='./'>首页 (Home)</a></li>"
        
        # Helper to dedup
        def add_unique_items(items):
            result = ""
            seen_labels = set()
            for item in items:
                label = item['label']
                if label in seen_labels:
                    # Append date to make unique? Or just skip?
                    # For now, let's skip exact duplicates, or append part of filename if needed.
                    # But simpler: just skip.
                    continue
                seen_labels.add(label)
                result += f"<li><a href='{item['url']}'>{item['label']}</a></li>"
            return result

        # Top level items
        html += add_unique_items(nav_structure['top'])

        # Dropdowns
        dropdowns = ['History', 'Posts', 'Resources', 'Tags', 'Misc']
        for cat in dropdowns:
            items = nav_structure[cat]
            if not items:
                continue
            
            if cat == 'History':
               items.sort(key=lambda x: x['label'], reverse=True)
            
            html += f"""
            <li class="dropdown">
                <a href="#" class="dropdown-toggle" data-toggle="dropdown" role="button" aria-haspopup="true" aria-expanded="false">{cat} <span class="caret"></span></a>
                <ul class="dropdown-menu">
            """
            html += add_unique_items(items)
            html += "</ul></li>"
            
        html += "</ul>"
        return html

    navbar_html = build_nav_html()

    # Shared CSS Overrides
    custom_css = """
    <style>
        body { padding-top: 70px; } /* Fix fixed-top navbar overlap */
        /* Removed .inner/.outer overrides to respect theme post.css */
        
        .version-switcher { padding: 10px 15px; margin: 20px 0; border: 1px solid #e9ecef; background: #f8f9fa; border-radius: 4px; font-family: monospace; }
        .version-switcher a { margin-right: 10px; color: #888; text-decoration: none; }
        .version-switcher a.current { font-weight: bold; color: #333; }
        
        .navbar-brand { font-size: 20px; font-weight: bold; }
        .navbar-nav > li > a { font-size: 16px; } /* Slightly larger per user request */
        
        /* Reduce gap between navbar and content */
        div.outer { margin-top: 30px; }
        
        /* Removed custom flexbox list styling to match demo vertical style */
    </style>
    """


    # 5. Generate Content
    for base_name, data in processed_groups.items():
        versions = data['versions']
        has_multiple = len(versions) > 1

        # Check if it is a resource page and skip templating
        if base_name.startswith('resources_'):
             for ver in versions:
                 # Ensure output directory exists
                 with open(os.path.join(OUTPUT_DIR, ver['filename']), 'w', encoding='utf-8') as f:
                     f.write(ver['content'])
             continue

        # Generate version switcher for history pages (homepage/index) or normal pages
        switcher_html = ""
        if has_multiple:
            links = []
            for other_ver in versions:
                is_current = (other_ver['filename'] == versions[-1]['filename']) # Default to latest? No, need current iter context, but here we don't have 'ver' in loop yet.
                # Actually we need to generate switcher inside the loop or per version.
                # But to avoid re-generating for every version if it's identical list, we can gen list first.
                pass 
                
        # Special handling for history pages: Inject switcher into raw content
        if base_name.startswith('homepage') or base_name.startswith('index'):
            for ver in versions:
                 content = ver['content']
                 
                 # Generate switcher specifically for this version to mark 'current' correctly
                 local_switcher_html = ""
                 if has_multiple:
                     links = []
                     for other_ver in versions:
                         is_current = (other_ver['filename'] == ver['filename'])
                         cls = 'class="current"' if is_current else ''
                         links.append(f'<a href="{other_ver["filename"]}" {cls}>{other_ver["formatted_date"]}</a>')
                     local_switcher_html = f'<div class="version-switcher"><span>Versions:</span>{" ".join(links)}</div>'
                 
                 if local_switcher_html:
                    style_block = """
                    <style>
                    .version-switcher { padding: 10px; background: #f0f0f0; border-bottom: 1px solid #ccc; font-family: sans-serif; margin: 20px 0; }
                    .version-switcher span { font-weight: bold; margin-right: 10px; color: #555; }
                    .version-switcher a { margin-right: 10px; text-decoration: none; color: #007bff; border-bottom: 1px dotted #ccc; }
                    .version-switcher a:hover { text-decoration: underline; }
                    .version-switcher a.current { font-weight: bold; color: #000; pointer-events: none; border-bottom: 2px solid #000; }
                    </style>
                    """
                    if '<body' in content.lower():
                         content = re.sub(r'(<body[^>]*>)', r'\1' + style_block + local_switcher_html, content, count=1, flags=re.IGNORECASE)
                    else:
                         content = style_block + local_switcher_html + content

                 with open(os.path.join(OUTPUT_DIR, ver['filename']), 'w', encoding='utf-8') as f:
                     f.write(content)
            continue

        for ver in versions:
            content = ver['content']
            
            # Clean old CSS
            content = re.sub(r'<link[^>]*href=["\'].*?main\.css["\'][^>]*>', '', content, flags=re.IGNORECASE)
            content = re.sub(r'<link[^>]*href=["\'].*?style\.css["\'][^>]*>', '', content, flags=re.IGNORECASE)
            
            # Fix nesting: neutralize internal .inner to avoid double styling from theme
            content = re.sub(r'<div\s+[^>]*class=["\']inner["\'][^>]*>', '<div>', content, count=1, flags=re.IGNORECASE)
            
            raw_body = get_body_content(content)
            
            # Special handling for Tweets: Transform to .micro-blog structure
            if base_name.startswith('tweet'):
                # Extract content inside <div class="tweet">
                tweet_match = re.search(r'<div class="tweet">(.*?)</div>', content, re.DOTALL | re.IGNORECASE)
                if tweet_match:
                    tweet_content = tweet_match.group(1)
                    
                    # Transform <p><i>Date</i>Content... to structured items
                    # Pattern: <p><i>(.*?)</i>(.*?)</p> (or just up to next <p>)
                    # Note: Original HTML is messy, sometimes <p> isn't closed or uses <br>.
                    # Heuristic: Split by <p><i>, then reconstruct.
                    
                    matches = re.finditer(r'<p><i>(.*?)</i>(.*?)(?=<p><i>|$)', tweet_content, re.DOTALL | re.IGNORECASE)
                    new_tweets = []
                    for m in matches:
                        date = m.group(1).strip()
                        text = m.group(2).strip()
                        # Clean up any leading/trailing <br> or whitespace
                        text = re.sub(r'^<br\s*/?>', '', text).strip()
                        
                        item_html = f"""
                        <div class="list-group-item">
                            <div class="date">{date}</div>
                            <div class="content">{text}</div>
                        </div>
                        """
                        new_tweets.append(item_html)
                    
                    if new_tweets:
                        raw_body = f'<div class="micro-blog">{"".join(new_tweets)}</div>'
                else:
                    # Fallback if no .tweet div found, just wrap raw body
                     raw_body = f'<div class="micro-blog">{raw_body}</div>'

            title = extract_title(content, ver['filename'])
            
            switcher_html = ""
            if has_multiple:
                links = []
                for other_ver in versions:
                    is_current = (other_ver['filename'] == ver['filename'])
                    cls = 'class="current"' if is_current else ''
                    links.append(f'<a href="{other_ver["filename"]}" {cls}>{other_ver["formatted_date"]}</a>')
                switcher_html = f'<div class="version-switcher"><span>Versions:</span>{" ".join(links)}</div>'

            # Template
            new_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=0.5">
    <title>{title}</title>
    <link rel="stylesheet" href="css/highlight/xcode.min.css">
    <link rel="stylesheet" href="css/bootstrap/bootstrap-tooltips.css">
    <link rel="stylesheet" href="css/bootstrap/bootstrap.min.css">
    <link rel="stylesheet" href="css/bootstrap/bootstrap-theme.min.css">
    <link rel="stylesheet" href="css/home.css">
    <link rel="stylesheet" href="css/post.css">
    <script src="js/jquery.min.js"></script>
    {custom_css}
</head>
<body>
    <nav class="navbar navbar-default navbar-fixed-top" style="opacity:.9" role="navigation">
        <div class="container-fluid">
            <div class="navbar-header">
                <button class="navbar-toggle collapsed" type="button" data-toggle="collapse" data-target="#navbar-bs">
                    <span class="icon-bar"></span><span class="icon-bar"></span><span class="icon-bar"></span>
                </button>
                <a class="navbar-brand" href="./" title="" data-toggle="tooltip" data-placement="right">Wang Yin's Blog</a>
            </div>
            <div class="navbar-collapse collapse" id="navbar-bs" style="height:1px">
                {navbar_html}
            </div>
        </div>
    </nav>

    <div class="inner">
        {switcher_html}
        {raw_body}
    </div>
    
    <script src="js/highlight.min.js"></script>
    <script src="js/main.js"></script>
    <script src="js/bootstrap/bootstrap.min.js"></script>
    <script>
        if (/mobile/i.test(navigator.userAgent) || /android/i.test(navigator.userAgent)) {{
            document.body.classList.add('mobile');
            var navbar = document.querySelector('nav.navbar');
            if (navbar) {{ navbar.classList.remove('navbar-fixed-top'); }}
        }}
    </script>
</body>
</html>"""
            
            with open(os.path.join(OUTPUT_DIR, ver['filename']), 'w', encoding='utf-8') as f:
                f.write(new_html)

    # 6. Generate Index
    articles_meta = [v['latest_meta'] for k, v in processed_groups.items() if v['type'] == 'article']
    articles_meta.sort(key=lambda x: x['sort_date'], reverse=True)
    
    html_lines = [
        "<!DOCTYPE html>",
        "<html>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=0.5'>",
        "    <title>Wang Yin's Blog Archive</title>",
        "    <link rel='stylesheet' href='css/highlight/xcode.min.css'>",
        "    <link rel='stylesheet' href='css/bootstrap/bootstrap-tooltips.css'>",
        "    <link rel='stylesheet' href='css/bootstrap/bootstrap.min.css'>",
        "    <link rel='stylesheet' href='css/bootstrap/bootstrap-theme.min.css'>",
        "    <link rel='stylesheet' href='css/home.css'>",
        "    <script src='js/jquery.min.js'></script>",
        f"    {custom_css}",
        "</head>",
        "<body>",
        "    <nav class='navbar navbar-default navbar-fixed-top' style='opacity:.9' role='navigation'>",
        "        <div class='container-fluid'>",
        "            <div class='navbar-header'>",
        "                <button class='navbar-toggle collapsed' type='button' data-toggle='collapse' data-target='#navbar-bs'>",
        "                    <span class='icon-bar'></span><span class='icon-bar'></span><span class='icon-bar'></span>",
        "                </button>",
        "                <a class='navbar-brand' href='./' title='' data-toggle='tooltip' data-placement='right'>Wang Yin's Blog</a>",
        "            </div>",
        "            <div class='navbar-collapse collapse' id='navbar-bs' style='height:1px'>",
        f"               {navbar_html}",
        "            </div>",
        "        </div>",
        "    </nav>",
        "    <div class='outer'>",
        "        <ul class='list-group'>"
    ]
    
    for art in articles_meta:
        html_lines.append(f"            <li class='list-group-item title'>")
        if art['date']:
             html_lines.append(f"                <div class='date'>{art['date']}</div>")
        html_lines.append(f"                <a href='{art['filename']}' target='_blank'>{art['title']}</a>")
        html_lines.append(f"            </li>")
        
    html_lines.append("        </ul>")
    html_lines.append("    </div>") 
    
    html_lines.append("    <div class='footer'><p class='text-center'>Archived from yinwang.org</p></div>")
    html_lines.append("    <script src='js/highlight.min.js'></script>")
    html_lines.append("    <script src='js/main.js'></script>")
    html_lines.append("    <script src='js/bootstrap/bootstrap.min.js'></script>")
    html_lines.append("""
    <script>
      if (/mobile/i.test(navigator.userAgent) || /android/i.test(navigator.userAgent)) {
        document.body.classList.add('mobile')
        var navbar = document.querySelector('nav.navbar');
        if (navbar) { navbar.classList.remove('navbar-fixed-top'); }
      }
    </script>
    """)
    html_lines.append("</body></html>")
    
    with open(INDEX_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("\n".join(html_lines))
        
    print(f"Generated {INDEX_OUTPUT} with {len(articles_meta)} articles.")




def main():
    process_archives()


if __name__ == "__main__":
    main()
