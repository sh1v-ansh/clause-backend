import requests
from bs4 import BeautifulSoup
import json
import time

BASE_URL = "https://malegislature.gov/Laws/GeneralLaws"

# Define chapters with their full paths and output filenames
CHAPTERS = [
    {
        "number": "186",
        "path": "PartII/TitleI/Chapter186",
        "output_file": "chapter_186.json"
    },
    {
        "number": "93A",
        "path": "PartI/TitleXV/Chapter93A",
        "output_file": "chapter_93A.json"
    }
]

def scrape_section(section_url, chapter_num):
    """Scrape an individual section page"""
    res = requests.get(section_url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    main = soup.find('main')
    if not main:
        return None
    
    # Get section number from H1
    h1 = main.find('h1')
    section_num = h1.get_text(strip=True) if h1 else "Unknown"
    
    # Get law text from paragraphs
    paragraphs = main.find_all('p')
    law_text = []
    seen_text = set()  # Track duplicates
    
    for p in paragraphs:
        text = p.get_text(strip=True)
        # Filter out navigation, social media, and duplicate paragraphs
        if (len(text) > 30 and 
            'MyLegislature' not in text and 
            'facebook' not in text.lower() and
            text not in seen_text):
            law_text.append(text)
            seen_text.add(text)
    
    if not law_text:
        return None
    
    # The first paragraph usually contains "Section X. Title text..."
    full_text = " ".join(law_text)
    
    # Try to extract title from first paragraph
    first_para = law_text[0]
    section_title = section_num
    if '. ' in first_para:
        # Extract title portion (between "Section X." and the rest)
        parts = first_para.split('. ', 1)
        if len(parts) > 1:
            section_title = parts[0]
    
    return {
        "chapter": chapter_num,
        "section": section_num,
        "section_title": section_title,
        "text": full_text
    }

def scrape_chapter(chapter_num, chapter_path, output_file):
    """Get all section links from chapter page and scrape each section"""
    url = f"{BASE_URL}/{chapter_path}"
    print(f"\nScraping chapter {chapter_num} from {url}")
    
    res = requests.get(url)
    res.raise_for_status()
    soup = BeautifulSoup(res.text, "html.parser")
    
    # Find all links to sections
    section_links = []
    for link in soup.find_all('a', href=True):
        href = link.get('href')
        if href and f'/Chapter{chapter_num}/Section' in href:
            full_url = f"https://malegislature.gov{href}"
            section_links.append(full_url)
    
    print(f"Found {len(section_links)} sections in chapter {chapter_num}")
    
    data = []
    for i, section_url in enumerate(section_links, 1):
        print(f"  Scraping section {i}/{len(section_links)}...", end='\r')
        section_data = scrape_section(section_url, chapter_num)
        if section_data:
            data.append(section_data)
        time.sleep(0.5)  # Be respectful to the server
    
    print(f"  Completed {len(data)} sections from chapter {chapter_num}     ")
    
    # Save to individual output file
    with open(output_file, "w") as f:
        json.dump(data, f, indent=2)
    print(f"  Saved to {output_file}")
    
    return data

# Scrape each chapter and save to separate files
total_sections = 0
for chapter in CHAPTERS:
    chapter_data = scrape_chapter(
        chapter["number"], 
        chapter["path"], 
        chapter["output_file"]
    )
    total_sections += len(chapter_data)

print(f"\n{'='*50}")
print(f"Total: Scraped {total_sections} sections across {len(CHAPTERS)} chapters")
print(f"{'='*50}")