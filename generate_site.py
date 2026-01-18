import shutil
import os
import re

ARCHIVES_DIR = "archives"
OUTPUT_DIR = "docs"
INDEX_OUTPUT = os.path.join(OUTPUT_DIR, "index.html")
STYLE_OUTPUT = os.path.join(OUTPUT_DIR, "style.css")

DOMAIN = "yinwang.org"

def parse_date_from_filename(filename):
    # Try to find date pattern YYYY_MM_DD
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"
    return None

def extract_title(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
            content = f.read()
            # Try <title>
            match = re.search(r'<title>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
            # Try h2 (often used in his blog for title)
            match = re.search(r'<h2>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL)
            if match:
                return match.group(1).strip()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
    return os.path.basename(filepath)

def copy_archives():
    if not os.path.exists(OUTPUT_DIR):
        os.makedirs(OUTPUT_DIR)
        
    print(f"Copying files from {ARCHIVES_DIR} to {OUTPUT_DIR}...")
    
    # Copy images directory if it exists
    src_images = os.path.join(ARCHIVES_DIR, "images")
    dst_images = os.path.join(OUTPUT_DIR, "images")
    if os.path.exists(src_images):
        if os.path.exists(dst_images):
            shutil.rmtree(dst_images)
        shutil.copytree(src_images, dst_images)
        print(f"Copied images directory.")

    count = 0
    for f in os.listdir(ARCHIVES_DIR):
        if f.endswith(".html") and not f.startswith("index"):
             src = os.path.join(ARCHIVES_DIR, f)
             dst = os.path.join(OUTPUT_DIR, f)
             shutil.copy2(src, dst)
             count += 1
    print(f"Copied {count} HTML files.")

def generate_css():
    css = """
body {
    font-family: STFangSong, "Songti SC", SimSun, "Palatino Linotype", "Book Antiqua", Palatino, serif;
    line-height: 1.6;
    color: #333;
    max-width: 900px;
    margin: 0 auto;
    padding: 20px;
    background-color: #fff;
    -webkit-font-smoothing: antialiased;
}

/* Breathing Glow Effect */
.glow-overlay {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    box-shadow: inset 0 0 50px rgba(0, 102, 255, 0.15); 
    animation: breathe 5s ease-in-out infinite;
    z-index: 9999;
}

@keyframes breathe {
    0%, 100% { box-shadow: inset 0 0 50px rgba(0, 102, 255, 0.15); }
    50% { box-shadow: inset 0 0 100px rgba(0, 102, 255, 0.25); }
}

h1 {
    text-align: center;
    margin: 50px 0 60px;
    color: #666;
    font-weight: normal;
    font-size: 2.2em;
}

.article-list {
    list-style: none;
    padding: 0;
    margin: 0 auto;
    max-width: 800px;
}

.article-item {
    margin-bottom: 25px;
    padding: 5px 0;
    display: flex;
    align-items: baseline;
    border-bottom: 1px dashed #eee;
    padding-bottom: 15px;
}

.article-date {
    font-family: "Courier New", monospace;
    color: #999;
    margin-right: 20px;
    min-width: 100px;
    font-size: 0.9em;
    text-align: right;
}

.article-link {
    text-decoration: none;
    color: #444;
    font-size: 1.15em;
    transition: color 0.3s;
}

.article-link:hover {
    color: #2a6496;
    text-decoration: none;
}

footer {
    margin-top: 80px;
    text-align: center;
    font-size: 0.8em;
    color: #ccc;
    padding-bottom: 40px;
}

/* Mobile responsiveness */
@media (max-width: 600px) {
    body {
        padding: 15px;
    }
    .article-item {
        flex-direction: column;
    }
    .article-date {
        text-align: left;
        margin-bottom: 5px;
        font-size: 0.85em;
    }
}
    """
    with open(STYLE_OUTPUT, 'w', encoding='utf-8') as f:
        f.write(css)
    print(f"Generated {STYLE_OUTPUT}")

def generate_index():
    articles = []
    
    # Scan OUTPUT_DIR now (since we copied them)
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.html') and f != 'index.html']
    
    print(f"Scanning {len(files)} files...")
    
    for filename in files:
        filepath = os.path.join(OUTPUT_DIR, filename)
        
        # Skip junk
        if filename.startswith("_") or "index.json" in filename:
            continue
            
        date = parse_date_from_filename(filename)
        sort_date = date if date else "1970-01-01"
        display_date = date if date else "Unknown"
        
        title = extract_title(filepath)
        
        articles.append({
            'filename': filename,
            'title': title,
            'date': display_date,
            'sort_date': sort_date
        })
        
    # Sort by date descending
    articles.sort(key=lambda x: x['sort_date'], reverse=True)
    
    # Generate HTML
    html_lines = [
        "<!DOCTYPE html>",
        "<html lang='zh-CN'>",
        "<head>",
        "    <meta charset='UTF-8'>",
        "    <meta name='viewport' content='width=device-width, initial-scale=1.0'>",
        "    <title>Wang Yin's Blog Archive</title>",
        "    <link rel='stylesheet' href='style.css'>",
        "</head>",
        "<body>",
        "    <div class='glow-overlay'></div>",
        "    <h1>Wang Yin's Blog Archive</h1>",
        "    <ul class='article-list'>"
    ]
    
    for art in articles:
        html_lines.append(f"        <li class='article-item'>")
        html_lines.append(f"            <span class='article-date'>{art['date']}</span>")
        html_lines.append(f"            <a class='article-link' href='{art['filename']}'>{art['title']}</a>")
        html_lines.append(f"        </li>")
        
    html_lines.append("    </ul>")
    html_lines.append("    <footer>Archived from yinwang.org via Wayback Machine</footer>")
    html_lines.append("</body>")
    html_lines.append("</html>")
    
    with open(INDEX_OUTPUT, 'w', encoding='utf-8') as f:
        f.write("\n".join(html_lines))
        
    print(f"Generated {INDEX_OUTPUT} with {len(articles)} articles.")

def main():
    copy_archives()
    generate_css()
    generate_index()

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
