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
    Typically finds the first YYYY_MM_DD pattern.
    """
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def extract_title(content):
    try:
        # Try <title>
        match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
        # Try h2
        match = re.search(r'<h2>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL)
        if match:
            return match.group(1).strip()
    except Exception as e:
        pass
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
                title = extract_title(latest['content'])
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
        .navbar-nav > li > a { font-size: 14px; } /* Reduce Navbar font size */
        
        /* Removed custom flexbox list styling to match demo vertical style */
    </style>
    """


    # 5. Generate Content
    for base_name, data in processed_groups.items():
        versions = data['versions']
        has_multiple = len(versions) > 1
        
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

            title = extract_title(content)
            
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
