import shutil
import os
import re
import hashlib
import html as html_lib
import difflib
import urllib.parse
from datetime import datetime
import json
from collections import Counter

ARCHIVES_DIR = "archives"
OUTPUT_DIR = "docs"
INDEX_OUTPUT = os.path.join(OUTPUT_DIR, "index.html")
STYLE_OUTPUT = os.path.join(OUTPUT_DIR, "style.css")

DOMAIN = "yinwang.org"
MIN_YEAR = "2000"

LEGACY_REDIRECTS = {
    "blog-cn_20090101_谈P=NP_20090101.html": "blog-cn_2013_03_谈P=NP_20171025.html",
    "blog-cn_20090101_程序语言理论的学习对于程序员教育的作用_20090101.html": "blog-cn_20120613_程序语言理论的学习对于程序员教育的作用_20120613.html",
    "blog-cn_20090101_完全用Linux工作_20090101.html": "blog-cn_20030113_完全用Linux工作_20030113.html",
    "blog-cn_20090101_为什么需要正则表达式_20090101.html": "blog-cn_20120517_为什么需要正则表达式_20120517.html",
    "blog-cn_20090101_让科学和理性回到计算机科学_20090101.html": "blog-cn_20120517_让科学和理性回到计算机科学_20120517.html",
    "blog-cn_20090101_谁是真正的程序语言专家_20090101.html": "blog-cn_20120614_谁是真正的程序语言专家_20120614.html",
    "blog-cn_20090101_我看PhD_20090101.html": "blog-cn_20120722_我看PhD_20120722.html",
    "blog-cn_20090101_从工具的奴隶到工具的主人_20090101.html": "blog-cn_20120814_从工具的奴隶到工具的主人_20120814.html",
    "blog-cn_20090101_给Texmacs的推荐信_20090101.html": "blog-cn_20120918_给Texmacs的推荐信_20120918.html",
    "blog-cn_20090101_上海_20090101.html": "blog-cn_20180627_上海_20180627.html",
    "blog-cn_20090101_警惕“编译器人”和“函数式程序员”_20090101.html": "blog-cn_20191224_警惕“编译器人”和“函数式程序员”_20191224.html",
    "blog-cn_20120712_我和谷歌的故事_20120712.html": "blog-cn_2012_07_12_google-story_20180329.html",
}

DISCLAIMER_AUTHOR = "王垠"
DISCLAIMER_BLOG_URL = "https://www.yinwang.org/"


def build_disclaimer_footer_html(variant: str) -> str:
    """Returns an HTML footer disclaimer.

    variant:
      - "templated": uses classes expected to exist on generated pages (bootstrap).
      - "raw": inline styles for pages that keep original HTML/CSS.
    """
    if variant == "raw":
        return (
            "\n"
            "<div style=\"margin:40px auto 30px; padding:0 20px; max-width:1000px; font-size:14px; line-height:1.6; text-align:center;\">"
            "<p style=\"margin:0;\">"
            "声明：本项目仅出于个人兴趣对网络历史内容进行备份与学习，无任何商业用途。"
            f"原文作者：{DISCLAIMER_AUTHOR}；原博客："
            f"<a href=\"{DISCLAIMER_BLOG_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">{DISCLAIMER_BLOG_URL}</a>"
            "</p>"
            "</div>\n"
        )

    # templated
    return (
        "\n"
        "<div class=\"site-footer\">"
        "  <p class=\"text-center text-muted\">"
        "声明：本项目仅出于个人兴趣对网络历史内容进行备份与学习，无任何商业用途。"
        f"原文作者：{DISCLAIMER_AUTHOR}；原博客："
        f"<a href=\"{DISCLAIMER_BLOG_URL}\" target=\"_blank\" rel=\"noopener noreferrer\">{DISCLAIMER_BLOG_URL}</a>"
        "  </p>"
        "</div>\n"
    )


def inject_footer_before_body_close(html: str, footer_html: str) -> str:
    """Injects footer_html before </body> if present, else before </html>, else appends."""
    if not html or not footer_html:
        return html

    if re.search(r"</body\\s*>", html, flags=re.IGNORECASE):
        return re.sub(r"</body\\s*>", footer_html + "</body>", html, count=1, flags=re.IGNORECASE)
    if re.search(r"</html\\s*>", html, flags=re.IGNORECASE):
        return re.sub(r"</html\\s*>", footer_html + "</html>", html, count=1, flags=re.IGNORECASE)
    return html + footer_html


def normalize_generated_html(html: str) -> str:
    """Trim template/prose whitespace without changing preformatted source text."""
    lines = []
    in_pre = False
    for line in html.splitlines():
        lowered = line.lower()
        starts_pre = '<pre' in lowered
        preserve = in_pre or starts_pre
        lines.append(line if preserve else line.rstrip())
        if starts_pre and '</pre>' not in lowered:
            in_pre = True
        if in_pre and '</pre>' in lowered:
            in_pre = False
    return "\n".join(lines) + "\n"

def parse_article_date(filename):
    """
    Parses the article date (publication date) from the filename.
    Typically finds the first YYYY_MM_DD, YYYY_MM, or YYYYMMDD pattern.
    Month-only dates are used when the surviving evidence does not establish
    an exact publication day.
    """
    # Try YYYY_MM_DD
    match = re.search(r'(\d{4})_(\d{2})_(\d{2})', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"

    # Try YYYY_MM, but do not treat the prefix of YYYY_MM_DD as month-only.
    match = re.search(r'(\d{4})_(\d{2})(?!_\d{2})', filename)
    if match:
        return f"{match.group(1)}-{match.group(2)}"
    
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
    
    # Try title tag (only works if head wasn't stripped)
    match = re.search(r'<title[^>]*>(.*?)</title>', content, re.IGNORECASE | re.DOTALL)
    if match:
        title = strip_tags(match.group(1)).strip()
        if title and title.lower() != 'untitled':
            return title

    # Try h2 (common in yinwang's older posts)
    match = re.search(r'<h2[^>]*>(.*?)</h2>', content, re.IGNORECASE | re.DOTALL)
    if match:
        return strip_tags(match.group(1)).strip()

    # Fallback to filename
    base = os.path.basename(filename)
    # Remove extension and potential date suffix
    base = re.sub(r'(_\d{8})?\.html$', '', base)
    # Improve readability for resource files (e.g. replacing separators)
    clean_name = base.replace('resources_', '').replace('_', ' ').replace('-', ' ')
    if clean_name.strip():
        return clean_name.title()
    
    return "Untitled"


def extract_article_title(content, filename):
    """Prefer the visible article heading over generic document metadata."""
    match = re.search(
        r'<h(?P<level>[12])\b[^>]*>(?P<inner>.*?)</h(?P=level)>',
        content,
        re.IGNORECASE | re.DOTALL,
    )
    if match:
        title = html_lib.unescape(strip_tags(match.group('inner'))).strip()
        if title:
            return title
    return extract_title(content, filename)


def normalize_title_key(text):
    text = html_lib.unescape(strip_tags(text or ""))
    return re.sub(r'[\s（）()·:：—–-]+', '', text).lower()


def clean_archived_page_chrome(raw_body):
    """Remove duplicated analytics/mobile/ad chrome while preserving article scripts."""
    removable_markers = (
        'GoogleAnalyticsObject',
        'google-analytics.com',
        'adsbygoogle',
        'navigator.userAgent',
        'document.body.classList.add',
    )

    def clean_script(match):
        script = match.group(0)
        return '' if any(marker in script for marker in removable_markers) else script

    raw_body = re.sub(
        r'<script\b[^>]*>.*?</script>',
        clean_script,
        raw_body,
        flags=re.IGNORECASE | re.DOTALL,
    )

    def clean_comment(match):
        comment = match.group(0)
        lowered = comment.lower()
        if 'ad-banner' in lowered or 'adsbygoogle' in lowered:
            return ''
        return comment

    raw_body = re.sub(r'<!--.*?-->', clean_comment, raw_body, flags=re.DOTALL)
    raw_body = re.sub(
        r'<div\b[^>]*class=["\'][^"\']*\bad-banner\b[^"\']*["\'][^>]*>\s*</div>',
        '',
        raw_body,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return raw_body.strip()


def normalize_article_title(raw_body, title):
    """Give confirmed article-title headings one consistent semantic style."""
    heading = re.search(
        r'<h(?P<level>[12])\b[^>]*>(?P<inner>.*?)</h(?P=level)>',
        raw_body,
        re.IGNORECASE | re.DOTALL,
    )
    escaped_title = html_lib.escape(title)
    if not heading:
        return f'<h1 class="article-title">{escaped_title}</h1>\n{raw_body}'

    visible_heading = html_lib.unescape(strip_tags(heading.group('inner'))).strip()
    if normalize_title_key(visible_heading) != normalize_title_key(title):
        return f'<h1 class="article-title">{escaped_title}</h1>\n{raw_body}'

    normalized_heading = f'<h1 class="article-title">{heading.group("inner").strip()}</h1>'
    return raw_body[:heading.start()] + normalized_heading + raw_body[heading.end():]

def get_base_name_and_version(filename):
    """
    Returns (base_name, version_date_str)
    e.g. blog-cn_..._20140722.html -> (blog-cn_..., 20140722)
    """
    match = re.search(r'^(.*)_(\d{8})\.html$', filename)
    if match:
        return match.group(1), match.group(2)
    return filename, "00000000"


def is_archive_year_allowed(version_date):
    if not version_date or len(version_date) < 4:
        return True
    return version_date[:4] >= MIN_YEAR

def extract_metadata(content, filename):
    """
    Extract date and title from content.
    Returns a dict with 'date' (YYYY-MM-DD, YYYY-MM, or None) and 'title'.
    """
    title = extract_title(content, filename)
    
    # Try to find date in content (common yinwang patterns)
    # Pattern 1: <h2>Date</h2> or <div class="date">
    date_match = re.search(r'(\d{4}[-/]\d{1,2}[-/]\d{1,2})', content)
    date = None
    if date_match:
        date = date_match.group(1).replace('/', '-')
    else:
        # Preserve explicitly month-precision dates without inventing a day.
        month_date_match = re.search(
            r'<div[^>]*class=["\'][^"\']*\bdate\b[^"\']*["\'][^>]*>\s*(\d{4}[-/]\d{1,2})\s*</div>',
            content,
            re.IGNORECASE,
        )
        if month_date_match:
            date = month_date_match.group(1).replace('/', '-')
        else:
            date = parse_article_date(filename)

    return {
        'date': date,
        'title': title
    }

def format_version_date(date_str):
    if len(date_str) == 8:
        return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:]}"
    return date_str


DIFF_BLOCK_RE = re.compile(
    r'<(?P<tag>h[1-6]|p|li|pre|blockquote)\b[^>]*>.*?</(?P=tag)>',
    re.IGNORECASE | re.DOTALL,
)


def prepare_diff_body(content, title):
    body = get_body_content(content)
    body = re.sub(r'<!--.*?-->', '', body, flags=re.DOTALL)
    body = re.sub(r'<(?:script|style)\b.*?</(?:script|style)>', '', body, flags=re.IGNORECASE | re.DOTALL)

    heading = re.search(
        r'<h(?P<level>[12])\b[^>]*>(?P<inner>.*?)</h(?P=level)>',
        body,
        re.IGNORECASE | re.DOTALL,
    )
    if heading:
        visible_heading = html_lib.unescape(strip_tags(heading.group('inner'))).strip()
        if normalize_title_key(visible_heading) == normalize_title_key(title):
            body = body[:heading.start()] + body[heading.end():]

    # Publication metadata is not an editorial content change.
    body = re.sub(
        r'<(?P<tag>div|p)\b[^>]*class=["\'][^"\']*\b(?:date|time)\b[^"\']*["\'][^>]*>.*?</(?P=tag)>',
        '',
        body,
        count=1,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return body


def extract_diff_blocks(content, title):
    body = prepare_diff_body(content, title)
    blocks = []
    for match in DIFF_BLOCK_RE.finditer(body):
        raw_html = match.group(0).strip()
        text = html_lib.unescape(strip_tags(raw_html))
        text = re.sub(r'\s+', ' ', text).strip()
        key = text or normalize_html(raw_html)
        blocks.append({
            'tag': match.group('tag').lower(),
            'html': raw_html,
            'text': text,
            'key': key,
        })
    return blocks


def tokenize_diff_text(text):
    return re.findall(r'[\u3400-\u9fff]|[A-Za-z0-9_]+|\s+|.', text or '', re.DOTALL)


def render_inline_diff(before, after):
    before_tokens = tokenize_diff_text(before)
    after_tokens = tokenize_diff_text(after)
    matcher = difflib.SequenceMatcher(None, before_tokens, after_tokens, autojunk=False)
    rendered = []
    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        old = html_lib.escape(''.join(before_tokens[i1:i2]))
        new = html_lib.escape(''.join(after_tokens[j1:j2]))
        if op == 'equal':
            rendered.append(new)
        elif op == 'delete':
            rendered.append(f'<del>{old}</del>')
        elif op == 'insert':
            rendered.append(f'<ins>{new}</ins>')
        else:
            rendered.append(f'<del>{old}</del><ins>{new}</ins>')
    return ''.join(rendered)


def nearest_diff_heading(blocks, index):
    for block in reversed(blocks[:index]):
        if block['tag'].startswith('h') and block['text']:
            return block['text']
    return ''


def build_semantic_diff(before_content, after_content, before_title, after_title):
    before_blocks = extract_diff_blocks(before_content, before_title)
    after_blocks = extract_diff_blocks(after_content, after_title)
    matcher = difflib.SequenceMatcher(
        None,
        [block['key'] for block in before_blocks],
        [block['key'] for block in after_blocks],
        autojunk=False,
    )

    counts = {'added': 0, 'removed': 0, 'changed': 0}
    changes = []
    preview = ''
    last_context = None

    def add_context(label):
        nonlocal last_context
        if label and label != last_context:
            changes.append(
                f'<div class="diff-context">{html_lib.escape(label)}</div>'
            )
            last_context = label

    def add_removed(block):
        nonlocal preview
        counts['removed'] += 1
        if not preview:
            preview = block['text']
        changes.append(
            '<div class="diff-block diff-removed">'
            '<span class="diff-marker" aria-hidden="true">−</span>'
            f'{block["html"]}</div>'
        )

    def add_added(block):
        nonlocal preview
        counts['added'] += 1
        if not preview:
            preview = block['text']
        changes.append(
            '<div class="diff-block diff-added">'
            '<span class="diff-marker" aria-hidden="true">+</span>'
            f'{block["html"]}</div>'
        )

    def add_changed(old_block, new_block):
        nonlocal preview
        counts['changed'] += 1
        if not preview:
            preview = new_block['text'] or old_block['text']
        rendered = render_inline_diff(old_block['text'], new_block['text'])
        pre_class = ' diff-preformatted' if new_block['tag'] == 'pre' else ''
        changes.append(
            f'<div class="diff-block diff-changed{pre_class}">'
            '<span class="diff-marker" aria-hidden="true">±</span>'
            f'<div class="diff-inline">{rendered}</div></div>'
        )

    for op, i1, i2, j1, j2 in matcher.get_opcodes():
        if op == 'equal':
            continue

        context = nearest_diff_heading(after_blocks, j1) or nearest_diff_heading(before_blocks, i1)
        add_context(context)

        if op == 'delete':
            for block in before_blocks[i1:i2]:
                add_removed(block)
        elif op == 'insert':
            for block in after_blocks[j1:j2]:
                add_added(block)
        else:
            old_slice = before_blocks[i1:i2]
            new_slice = after_blocks[j1:j2]
            paired = min(len(old_slice), len(new_slice))
            for offset in range(paired):
                add_changed(old_slice[offset], new_slice[offset])
            for block in old_slice[paired:]:
                add_removed(block)
            for block in new_slice[paired:]:
                add_added(block)

    preview = re.sub(r'\s+', ' ', preview).strip()
    if len(preview) > 120:
        preview = preview[:117].rstrip() + '…'
    return {
        'counts': counts,
        'preview': preview,
        'html': '\n'.join(changes) or '<p class="diff-empty">两个版本的正文没有可见差异。</p>',
    }



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

def is_valid_content(content):
    """
    Checks if content is valid article content or a junk placeholder.
    """
    if not content:
        return False
        
    s = content.lower()
    
    # Reject the known empty app shell itself, rather than matching its title
    # anywhere in the document. Valid articles can mention "Surely I Am
    # Joking" in their body (for example, 《我和权威的故事》).
    if '<div id="app"></div>' in s and len(s) < 2000:
        return False
        
    # Check for empty/too short content (keep conservative; allow short posts)
    if len(s) < 200 and "redirect" not in s and "moved" not in s:
        return False
        
    return True


def invalid_content_reason(content):
    if not content:
        return "empty"

    s = content.lower()

    if '<div id="app"></div>' in s and len(s) < 2000:
        return "empty-app-shell"

    if len(s) < 200 and "redirect" not in s and "moved" not in s:
        return "too-short"

    return "other"

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

    diff_output_dir = os.path.join(OUTPUT_DIR, "diffs")
    if os.path.exists(diff_output_dir):
        shutil.rmtree(diff_output_dir)
    os.makedirs(diff_output_dir)

    # 2. Group files
    article_groups = {} 
    page_groups = {}    

    skipped_invalid_files = []
    skipped_invalid_reason_counts = Counter()
    dropped_groups = []
    
    for f in os.listdir(ARCHIVES_DIR):
        if not f.endswith(".html") or f.startswith("index.json"): # Skip index.json but keep index_*.html
            continue

        _, version_date = get_base_name_and_version(f)
        if not is_archive_year_allowed(version_date):
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
                    
                    if not is_valid_content(content):
                        reason = invalid_content_reason(content)
                        skipped_invalid_reason_counts[reason] += 1
                        if len(skipped_invalid_files) < 200:
                            skipped_invalid_files.append({
                                'filename': filename,
                                'reason': reason,
                                'type': type_label,
                                'base_name': base_name
                            })
                        continue

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
                title_extractor = extract_article_title if type_label == 'article' else extract_title
                title = title_extractor(latest['content'], latest['filename'])
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
            else:
                # If a group has no usable versions, it will disappear from the site/index.
                # Record it so the user can audit what was dropped.
                dropped_groups.append({
                    'base_name': base_name,
                    'type': type_label,
                    'file_count': len(files),
                    'files': files[:50],
                })

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
    site_overrides_style = """
    <style>
        body { padding-top: 70px; } /* Fix fixed-top navbar overlap */
        /* Removed .inner/.outer overrides to respect theme post.css */
        
        .version-switcher { padding: 10px 15px; margin: 20px 0; border: 1px solid #e9ecef; background: #f8f9fa; border-radius: 4px; font-family: monospace; }
        .version-switcher a { margin-right: 10px; color: #888; text-decoration: none; }
        .version-switcher a.current { font-weight: bold; color: #333; }

        h1.article-title {
            width: auto;
            margin: 0 0 1.15em;
            padding: 0;
            border: 0;
            color: #555;
            font-size: clamp(1.55em, 4vw, 2em);
            line-height: 1.35;
            overflow-wrap: anywhere;
            text-wrap: balance;
        }
        h1.article-title + .date,
        h1.article-title + .time {
            margin-top: -1.2em;
            margin-bottom: 2em;
            color: #777;
            text-align: center;
            font-size: .85em;
        }

        .version-nav { margin-right: 8px; }
        .skip-link {
            position: fixed;
            top: 8px;
            left: 8px;
            z-index: 1100;
            padding: 9px 12px;
            border-radius: 4px;
            background: #fff;
            color: #222;
            transform: translateY(-150%);
        }
        .skip-link:focus { transform: translateY(0); }
        .version-menu-trigger {
            min-height: 44px;
            margin: 3px 0;
            padding: 8px 14px;
            border: 1px solid #cfcfcf;
            border-radius: 6px;
            background: #fff;
            color: #444;
            font-size: 16px;
            line-height: 24px;
            cursor: pointer;
            touch-action: manipulation;
        }
        .version-menu-trigger:hover { background: #f3f3f3; }
        .version-menu-trigger:active { background: #e8e8e8; }
        .version-menu-trigger:focus-visible,
        .version-panel a:focus-visible,
        .version-panel button:focus-visible {
            outline: 2px solid #555;
            outline-offset: 2px;
        }
        .version-count {
            display: inline-block;
            min-width: 22px;
            margin-left: 5px;
            padding: 0 6px;
            border-radius: 999px;
            background: #ececec;
            text-align: center;
            font-size: 13px;
        }
        .version-panel-backdrop {
            position: fixed;
            inset: 0;
            z-index: 1040;
            background: transparent;
        }
        .version-panel {
            position: fixed;
            top: 62px;
            right: 16px;
            z-index: 1050;
            width: min(360px, calc(100vw - 32px));
            max-height: calc(100vh - 80px);
            overflow: hidden;
            border: 1px solid #d8d8d8;
            border-radius: 10px;
            background: #fff;
            box-shadow: 0 14px 38px rgba(0, 0, 0, .18);
            color: #333;
            font-size: 15px;
        }
        .version-panel[hidden],
        .version-panel-backdrop[hidden] { display: none !important; }
        body.version-panel-open { overflow: hidden; }
        .version-panel-header {
            display: flex;
            align-items: center;
            justify-content: space-between;
            padding: 14px 16px;
            border-bottom: 1px solid #e5e5e5;
        }
        .version-panel-title {
            width: auto;
            margin: 0;
            padding: 0;
            border: 0;
            color: #333;
            text-align: left;
            font-family: inherit;
            font-size: 17px;
            font-weight: 600;
            line-height: 1.35;
        }
        .version-panel-close {
            width: 44px;
            height: 44px;
            padding: 0;
            border: 0;
            border-radius: 50%;
            background: transparent;
            color: #555;
            font-size: 24px;
            line-height: 44px;
            cursor: pointer;
            touch-action: manipulation;
        }
        .version-panel-close:hover { background: #eee; }
        .version-list {
            max-height: calc(100vh - 145px);
            margin: 0;
            padding: 8px;
            overflow-y: auto;
            list-style: none;
        }
        .version-item {
            margin: 0;
            padding: 10px 11px;
            border-left: 3px solid transparent;
            border-radius: 6px;
            transition: background-color .16s ease, border-color .16s ease;
        }
        .version-item:hover,
        .version-item:focus-within { background: #f5f5f5; }
        .version-item.current { border-left-color: #555; background: #f1f1f1; }
        .version-item-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .version-date-link,
        .version-current-label { color: #333; font-weight: 600; text-decoration: none; }
        .version-date-link { display: inline-flex; min-height: 44px; align-items: center; }
        .version-panel a { cursor: pointer; }
        .version-date-link:hover { background: transparent; text-decoration: underline; }
        .version-current-badge {
            padding: 2px 7px;
            border-radius: 999px;
            background: #dedede;
            color: #555;
            font-size: 12px;
            font-weight: 400;
        }
        .version-diff-summary { margin: 5px 0 0; color: #666; font-size: 13px; line-height: 1.5; }
        .version-preview {
            max-height: 0;
            margin: 0;
            overflow: hidden;
            color: #666;
            opacity: 0;
            font-size: 13px;
            line-height: 1.55;
            transition: max-height .18s ease, margin .18s ease, opacity .18s ease;
        }
        .version-item:hover .version-preview,
        .version-item:focus-within .version-preview {
            max-height: 7em;
            margin-top: 6px;
            opacity: 1;
        }
        .version-diff-link { display: inline-flex; min-height: 44px; margin-top: 3px; align-items: center; color: #555; text-decoration: underline; touch-action: manipulation; }
        .version-diff-link:hover { background: transparent; color: #111; }

        .diff-header { margin-bottom: 28px; text-align: center; }
        .diff-header h1 { margin-bottom: 12px; }
        .diff-range { color: #666; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; }
        .diff-summary { margin: 10px 0; color: #555; }
        .diff-actions { margin: 18px 0 0; }
        .diff-actions a { display: inline-block; padding: 8px 12px; border: 1px solid #ccc; border-radius: 6px; color: #444; }
        .diff-actions a:hover { background: #f2f2f2; }
        .diff-legend { display: flex; justify-content: center; gap: 16px; margin: 20px 0 30px; color: #555; font-size: 14px; }
        .diff-legend span::before { display: inline-block; width: 10px; height: 10px; margin-right: 6px; border-radius: 2px; content: ""; }
        .diff-legend .added::before { background: #b9dfc6; }
        .diff-legend .removed::before { background: #efc0bd; }
        .diff-legend .changed::before { background: #ead89c; }
        .diff-context { margin: 34px 0 12px; color: #666; font-weight: 600; }
        .diff-block { position: relative; margin: 10px 0; padding: 12px 14px 12px 34px; border-left: 4px solid; border-radius: 4px; }
        .diff-block > :first-child:not(.diff-marker) { margin-top: 0; }
        .diff-block > :last-child { margin-bottom: 0; }
        .diff-added { border-color: #4e9565; background: #eef8f1; }
        .diff-removed { border-color: #bb615b; background: #fff1f0; }
        .diff-changed { border-color: #aa8b2c; background: #fff9e6; }
        .diff-marker { position: absolute; top: 12px; left: 11px; color: #555; font-family: monospace; font-weight: 700; }
        .diff-inline { line-height: 1.8; white-space: pre-wrap; }
        .diff-inline del { background: #f1b8b5; color: #632c28; text-decoration-thickness: 1px; }
        .diff-inline ins { background: #bce3c8; color: #245d35; text-decoration: none; }
        .diff-preformatted .diff-inline { font-family: Inconsolata, Consolas, monospace; font-size: 90%; }
        .diff-empty, .diff-loading, .diff-error { padding: 24px; border: 1px solid #ddd; border-radius: 6px; text-align: center; }
        .diff-error { border-color: #d7aaa7; background: #fff4f3; color: #7d302b; }
        
        .navbar-brand { font-size: 20px; font-weight: bold; }
        .navbar-nav > li > a { font-size: 20px; }
        body.mobile .navbar-nav > li > a { font-size: 17px; line-height: 24px; }
        
        /* Reduce gap between navbar and content */
        div.outer { margin-top: 30px; }

        .site-footer { margin: 50px 0 30px; padding: 0 15px; font-size: 14px; line-height: 1.6; }
        .site-footer a { color: inherit; text-decoration: underline; }

        @media (max-width: 767px) {
            .version-nav { margin: 0; }
            .version-menu-trigger { display: block; width: 100%; margin: 4px 0; text-align: left; }
            .version-panel-backdrop { background: rgba(0, 0, 0, .28); }
            .version-panel {
                top: auto;
                right: 0;
                bottom: 0;
                width: 100%;
                max-height: min(76vh, 680px);
                border-right: 0;
                border-bottom: 0;
                border-left: 0;
                border-radius: 14px 14px 0 0;
            }
            .version-list { max-height: calc(min(76vh, 680px) - 65px); padding-bottom: max(12px, env(safe-area-inset-bottom)); }
            .version-preview { display: none; }
            .diff-legend { flex-wrap: wrap; gap: 8px 16px; }
            .diff-block { padding-right: 10px; padding-left: 30px; }
        }

        @media (prefers-reduced-motion: reduce) {
            .version-item, .version-preview { transition: none; }
        }
        
        /* Removed custom flexbox list styling to match demo vertical style */
    </style>
    """

    site_overrides_css = re.sub(
        r'^\s*<style>\s*|\s*</style>\s*$',
        '',
        site_overrides_style,
        flags=re.DOTALL,
    )
    with open(os.path.join(OUTPUT_DIR, 'css', 'site-overrides.css'), 'w', encoding='utf-8') as css_file:
        css_file.write(site_overrides_css.strip() + '\n')
    custom_css = '<link rel="stylesheet" href="css/site-overrides.css">'

    def prepare_group_diffs(base_name, versions, canonical_title):
        diff_id = hashlib.sha256(base_name.encode('utf-8')).hexdigest()[:16]
        relative_path = f"diffs/{diff_id}.json"
        comparisons = {}
        by_current = {}

        for index in range(1, len(versions)):
            before = versions[index - 1]
            after = versions[index]
            before_title = extract_article_title(before['content'], before['filename'])
            after_title = extract_article_title(after['content'], after['filename'])
            result = build_semantic_diff(
                before['content'],
                after['content'],
                before_title,
                after_title,
            )
            comparison = {
                'from': before['filename'],
                'to': after['filename'],
                'from_date': before['formatted_date'],
                'to_date': after['formatted_date'],
                'counts': result['counts'],
                'preview': result['preview'],
                'html': result['html'],
            }
            comparisons[after['filename']] = comparison
            query = urllib.parse.urlencode({
                'data': relative_path,
                'to': after['filename'],
            })
            by_current[after['filename']] = {
                **comparison,
                'url': f'diff.html?{query}',
            }

        payload = {
            'title': canonical_title,
            'comparisons': comparisons,
        }
        with open(os.path.join(OUTPUT_DIR, relative_path), 'w', encoding='utf-8') as diff_file:
            json.dump(payload, diff_file, ensure_ascii=False, separators=(',', ':'))
        return by_current

    def build_version_ui(versions, current, diff_by_current):
        count = len(versions)
        trigger = f"""
        <ul class="nav navbar-nav navbar-right version-nav">
            <li>
                <button class="version-menu-trigger" type="button" aria-expanded="false" aria-controls="version-panel">
                    版本 <span class="version-count">{count}</span>
                </button>
            </li>
        </ul>
        """

        items = []
        for version in reversed(versions):
            is_current = version['filename'] == current['filename']
            safe_filename = html_lib.escape(version['filename'], quote=True)
            safe_date = html_lib.escape(version['formatted_date'])
            if is_current:
                date_control = f'<span class="version-current-label" aria-current="page">{safe_date}</span>'
                badge = '<span class="version-current-badge">当前</span>'
            else:
                date_control = f'<a class="version-date-link" href="{safe_filename}">{safe_date}</a>'
                badge = ''

            diff_info = diff_by_current.get(version['filename'])
            if diff_info:
                counts = diff_info['counts']
                summary = (
                    f'较前版：+{counts["added"]} −{counts["removed"]} '
                    f'修改 {counts["changed"]}'
                )
                preview = ''
                if diff_info['preview']:
                    preview = f'<p class="version-preview">{html_lib.escape(diff_info["preview"])}</p>'
                diff_url = html_lib.escape(diff_info['url'], quote=True)
                diff_link = f'<a class="version-diff-link" href="{diff_url}">查看差异</a>'
            else:
                summary = '最早保留版本'
                preview = ''
                diff_link = ''

            current_class = ' current' if is_current else ''
            items.append(
                f'<li class="version-item{current_class}">'
                f'<div class="version-item-row">{date_control}{badge}</div>'
                f'<p class="version-diff-summary">{summary}</p>'
                f'{preview}{diff_link}</li>'
            )

        panel = f"""
        <div class="version-panel-backdrop" hidden></div>
        <section class="version-panel" id="version-panel" role="dialog" aria-modal="true" aria-labelledby="version-panel-title" hidden>
            <div class="version-panel-header">
                <h2 class="version-panel-title" id="version-panel-title">文章版本</h2>
                <button class="version-panel-close" type="button" aria-label="关闭版本列表">×</button>
            </div>
            <ol class="version-list">{''.join(items)}</ol>
        </section>
        """
        return trigger, panel

    diff_shell = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=0.5">
    <title>版本差异</title>
    <link rel="stylesheet" href="css/bootstrap/bootstrap.min.css">
    <link rel="stylesheet" href="css/bootstrap/bootstrap-theme.min.css">
    <link rel="stylesheet" href="css/home.css">
    <link rel="stylesheet" href="css/post.css">
    {custom_css}
</head>
<body>
    <a class="skip-link" href="#main-content">跳到正文</a>
    <nav class="navbar navbar-default navbar-fixed-top" style="opacity:.9" role="navigation">
        <div class="container-fluid">
            <div class="navbar-header">
                <button class="navbar-toggle collapsed" type="button" data-toggle="collapse" data-target="#navbar-bs">
                    <span class="icon-bar"></span><span class="icon-bar"></span><span class="icon-bar"></span>
                </button>
                <a class="navbar-brand" href="./">Wang Yin's Blog</a>
            </div>
            <div class="navbar-collapse collapse" id="navbar-bs" style="height:1px">{navbar_html}</div>
        </div>
    </nav>
    <main class="inner diff-page" id="main-content">
        <header class="diff-header">
            <h1 class="article-title" id="diff-title">版本差异</h1>
            <div class="diff-range" id="diff-range"></div>
            <p class="diff-summary" id="diff-summary"></p>
            <p class="diff-actions"><a id="diff-back-link" href="./">返回文章</a></p>
        </header>
        <div class="diff-legend" aria-label="差异图例">
            <span class="added">新增</span><span class="removed">删除</span><span class="changed">修改</span>
        </div>
        <p class="diff-loading" id="diff-loading" role="status">正在载入差异…</p>
        <p class="diff-error" id="diff-error" role="alert" hidden></p>
        <div id="diff-content"></div>
    </main>
    {build_disclaimer_footer_html("templated")}
    <script src="js/jquery.min.js"></script>
    <script src="js/bootstrap/bootstrap.min.js"></script>
    <script src="js/diff-view.js"></script>
</body>
</html>"""
    with open(os.path.join(OUTPUT_DIR, 'diff.html'), 'w', encoding='utf-8') as diff_shell_file:
        diff_shell_file.write(normalize_generated_html(diff_shell))


    # 5. Generate Content
    for base_name, data in processed_groups.items():
        versions = data['versions']
        has_multiple = len(versions) > 1
        is_article = data['type'] == 'article'
        diff_by_current = {}
        if is_article and has_multiple:
            diff_by_current = prepare_group_diffs(
                base_name,
                versions,
                data['latest_meta']['title'],
            )

        # Check if it is a resource page and skip templating
        if base_name.startswith('resources_'):
             for ver in versions:
                 # Ensure output directory exists
                 with open(os.path.join(OUTPUT_DIR, ver['filename']), 'w', encoding='utf-8') as f:
                     f.write(inject_footer_before_body_close(ver['content'], build_disclaimer_footer_html("raw")))
             continue

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

                 # Add disclaimer footer at the very bottom
                 content = inject_footer_before_body_close(content, build_disclaimer_footer_html("raw"))

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

            title = extract_article_title(content, ver['filename']) if is_article else extract_title(content, ver['filename'])
            if is_article:
                raw_body = clean_archived_page_chrome(raw_body)
                raw_body = normalize_article_title(raw_body, title)
            
            switcher_html = ""
            if has_multiple and not is_article:
                links = []
                for other_ver in versions:
                    is_current = (other_ver['filename'] == ver['filename'])
                    cls = 'class="current"' if is_current else ''
                    links.append(f'<a href="{other_ver["filename"]}" {cls}>{other_ver["formatted_date"]}</a>')
                switcher_html = f'<div class="version-switcher"><span>Versions:</span>{" ".join(links)}</div>'

            version_nav_html = ""
            version_panel_html = ""
            if is_article and has_multiple:
                version_nav_html, version_panel_html = build_version_ui(
                    versions,
                    ver,
                    diff_by_current,
                )

            # Template
            disclaimer_footer_html = build_disclaimer_footer_html("templated")
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
    <a class="skip-link" href="#main-content">跳到正文</a>
    <nav class="navbar navbar-default navbar-fixed-top" style="opacity:.9" role="navigation">
        <div class="container-fluid">
            <div class="navbar-header">
                <button class="navbar-toggle collapsed" type="button" data-toggle="collapse" data-target="#navbar-bs">
                    <span class="icon-bar"></span><span class="icon-bar"></span><span class="icon-bar"></span>
                </button>
                <a class="navbar-brand" href="./" title="" data-toggle="tooltip" data-placement="right">Wang Yin's Blog</a>
            </div>
            <div class="navbar-collapse collapse" id="navbar-bs" style="height:1px">
                {version_nav_html}
                {navbar_html}
            </div>
        </div>
    </nav>

    {version_panel_html}

    <main class="inner" id="main-content">
        {switcher_html}
        {raw_body}
    </main>

    {disclaimer_footer_html}
    
    <script src="js/highlight.min.js"></script>
    <script src="js/main.js"></script>
    <script src="js/bootstrap/bootstrap.min.js"></script>
    <script src="js/version-menu.js"></script>
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
                f.write(normalize_generated_html(new_html))

    # Preserve published archive URLs when correcting imported metadata.
    for old_filename, new_filename in LEGACY_REDIRECTS.items():
        redirect_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <meta http-equiv="refresh" content="0; url={new_filename}">
    <link rel="canonical" href="{new_filename}">
    <title>Redirecting…</title>
</head>
<body>
    <p><a href="{new_filename}">文章已移动，点击这里继续阅读。</a></p>
</body>
</html>"""
        with open(os.path.join(OUTPUT_DIR, old_filename), 'w', encoding='utf-8') as f:
            f.write(redirect_html)

    # 6. Generate Index
    articles_meta = [v['latest_meta'] for k, v in processed_groups.items() if v['type'] == 'article']
    

    # Deduplicate by title: Prefer version with "real" date over 2009-01-01
    # 1. Group by normalized title (remove whitespace) to catch "Title A" vs "TitleA"
    by_title = {}
    for art in articles_meta:
        # Normalize: remove whitespace
        t_norm = art['title'].replace(' ', '').lower()
        if t_norm not in by_title:
             by_title[t_norm] = []
        by_title[t_norm].append(art)
        
    final_articles = []
    dropped_duplicates = []
    
    for t_norm, arts in by_title.items():
        if len(arts) == 1:
            final_articles.append(arts[0])
        else:
            # If duplicates exist, filter out 2009-01-01 if a better date exists
            has_real_date = any(a['date'] != '2009-01-01' for a in arts)
            if has_real_date:
                # Keep only those that are NOT 2009-01-01
                kept = [a for a in arts if a['date'] != '2009-01-01']
                dropped = [a for a in arts if a['date'] == '2009-01-01']
                final_articles.extend(kept)
                dropped_duplicates.extend(dropped)
            else:
                # All are 2009-01-01.
                # If titles differ only by whitespace, we might want to keep just one.
                # Heuristic: Keep the one with the longest title (maybe more spaces = better formatted?)
                # OR just keep the first one.
                # Let's keep the one that matches the key? No key is stripped.
                # Let's Sort by title length descending (arbitrary stable choice) and pick first?
                # Actually if all are 20090101, it's likely duplicates from import.
                # Let's keep the first one found.
                # BUT if we have multiple 20090101s with same normalized title but different actual titles...
                # e.g. "Foo" and "Foo "
                # We probably only want one showing up.
                # Let's deduplicate these strict fuzzy dupes to 1 if all are undated.
                
                # Sort by title length (prefer "Foo Bar" over "FooBar"?)
                # It's hard to say which is better using length.
                # Let's just pick duplicates[0] to avoid 2 entries.
                final_articles.append(arts[0])
                if len(arts) > 1:
                    dropped_duplicates.extend(arts[1:])
                
    articles_meta = final_articles
    articles_meta.sort(key=lambda x: x['sort_date'], reverse=True)

    # Write a build report for auditing missing/skipped content
    report = {
        'generated_at': datetime.now().isoformat(timespec='seconds'),
        'archives_dir': ARCHIVES_DIR,
        'output_dir': OUTPUT_DIR,
        'articles_in_index': len(articles_meta),
        'dropped_duplicates_count': len(dropped_duplicates),
        'dropped_duplicates': [d['title'] for d in dropped_duplicates],
        'processed_groups_total': len(processed_groups),
        'style_and_diff': {
            'normalized_article_versions': sum(
                len(group['versions'])
                for group in processed_groups.values()
                if group['type'] == 'article'
            ),
            'multi_version_article_groups': sum(
                1
                for group in processed_groups.values()
                if group['type'] == 'article' and len(group['versions']) > 1
            ),
            'adjacent_diff_comparisons': sum(
                len(group['versions']) - 1
                for group in processed_groups.values()
                if group['type'] == 'article' and len(group['versions']) > 1
            ),
        },
        'skipped_invalid_reason_counts': dict(skipped_invalid_reason_counts),
        'skipped_invalid_examples': skipped_invalid_files,
        'dropped_groups_count': len(dropped_groups),
        'dropped_groups': dropped_groups,
    }
    try:
        with open(os.path.join(OUTPUT_DIR, '_build_report.json'), 'w', encoding='utf-8') as f:
            json.dump(report, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Warning: failed to write build report: {e}")
    
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
            # User request: don't show date for older/default date articles (2009-01-01)
            is_default_date = (art['date'] == '2009-01-01')
            if not is_default_date:
                 html_lines.append(f"                <div class='date'>{art['date']}</div>")
            else:
                 # Optional: Visual indicator or just empty?
                 # User said "do not mark the date"
                 pass
        html_lines.append(f"                <a href='{art['filename']}' target='_blank'>{art['title']}</a>")
        html_lines.append(f"            </li>")
        
    html_lines.append("        </ul>")
    html_lines.append("    </div>") 

    html_lines.append(build_disclaimer_footer_html("templated"))
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
