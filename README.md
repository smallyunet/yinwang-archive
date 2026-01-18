# Yinwang Archive

A comprehensive toolset to archive, preserve, and generate a readable static site for Wang Yin's blog ([yinwang.org](http://yinwang.org)), retrieving historical data from the Internet Archive's Wayback Machine.

## Features

- **Deep Archiving**: Scans the entire history of the homepage to discover forgotten articles.
- **Version Control**: Preserves **all unique historical versions** of each article (e.g., if an article was modified, both versions are saved with timestamps).
- **Image Localization**: Automatically downloads remote images and converts them to local references for offline viewing.
- **Modern Static Site**: Generates a clean, "breathing" minimalist website (in `docs/`) perfect for reading or hosting on GitHub Pages.

## Usage

Follow these steps to build the archive from scratch:

### 1. Archive Content
Run the main archiver to fetch HTML content from the Wayback Machine.
```bash
python3 archive_yinwang.py
```
*   This will save HTML files to the `archives/` directory.
*   Files are named `slug_YYYYMMDD.html` to distinguish versions.

### 2. Localize Images
Download images referenced in the articles to ensure the archive is self-contained.
```bash
python3 localize_images.py
```
*   This scans `archives/*.html`, downloads images to `archives/images/`, and updates the HTML `src` tags.

### 3. Generate Site
Build the final static website.
```bash
python3 generate_site.py
```
*   This copies all content to the `docs/` folder.
*   Generates an `index.html` with a chronological list of articles.
*   Applies a custom "breathing" visual style.

## Directory Structure

*   `archive_yinwang.py`: Main scraper script.
*   `localize_images.py`: Image downloader and path fixer.
*   `generate_site.py`: Static site generator.
*   `archives/`: Raw storage for downloaded HTML and images.
*   `docs/`: The final deployable website (GitHub Pages ready).
