# Author: Scott Grivner
# Website: linktr.ee/scottgriv
# Abstract: Scrape a web page for PDF files and download them all locally.

# Import Modules
import os
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup

# Define your URL
url = "https://wiki.math.ntnu.no/tma4412/2025h/eksamen"

# If there is no such folder, the script will create one automatically
folder_location = r"./downloads"

lf_folder = rf"{folder_location}/lf"
oppgave_folder = rf"{folder_location}/oppgave"

if not os.path.exists(folder_location):
    os.mkdir(folder_location)

if not os.path.exists(lf_folder):
    os.mkdir(lf_folder)

if not os.path.exists(oppgave_folder):
    os.mkdir(oppgave_folder)

# Fetch page content
try:
    response = requests.get(url, timeout=10)
    response.raise_for_status()  # Raise an error for bad status codes
except requests.RequestException as e:
    print(f"Failed to fetch the page: {e}")
    exit(1)
soup = BeautifulSoup(response.text, "html.parser")

# List to store downloaded PDF filenames
downloaded_pdfs = []
pdf_count = 1  # Counter for unnamed PDFs

midtsemester_heading = soup.find("h2", id="tidligere_midtsemesterprover_med_fasit")
if midtsemester_heading:
    # Find the next div.level2 sibling which contains the content
    section_div = midtsemester_heading.find_next_sibling("div", class_="level2")
    if section_div:
        section_div.decompose()  # Remove this section from the tree
        print("Excluded midtsemester section from download.")


def get_unique_filename(folder, filename):
    """Ensures filename is unique by appending a number if the file already exists."""
    base, ext = os.path.splitext(filename)
    counter = 2  # Start numbering at (2) if a duplicate is found

    new_filename = filename
    while os.path.exists(os.path.join(folder, new_filename)):
        new_filename = f"{base} ({counter}){ext}"
        counter += 1

    return os.path.join(folder, new_filename)


def get_pdf_filename(pdf_url):
    """Extracts filename from URL or generates a default one if missing."""
    global pdf_count
    parsed_url = urlparse(pdf_url)

    # Check if this is a fetch.php URL with a media parameter
    if "fetch.php" in parsed_url.path:
        from urllib.parse import parse_qs

        query_params = parse_qs(parsed_url.query)

        # Extract the media parameter which contains the actual PDF URL
        if "media" in query_params:
            media_url = query_params["media"][0]
            # Get filename from the media URL
            filename = os.path.basename(urlparse(media_url).path)
            if filename and filename.endswith(".pdf"):
                if (
                    "lf" in filename
                    or "LF" in filename
                    or "losningsforslag" in filename
                    or "fasit" in filename
                    or "solution" in filename
                ):
                    return get_unique_filename(lf_folder, filename)
                return get_unique_filename(oppgave_folder, filename)

    # Standard extraction for direct PDF links
    filename = os.path.basename(parsed_url.path)

    # Assign a default name if the filename is missing or not a PDF
    if not filename or not filename.endswith(".pdf"):
        filename = f"Downloaded_PDF_{pdf_count}.pdf"
        pdf_count += 1

    if (
        "lf" in filename
        or "LF" in filename
        or "losningsforslag" in filename
        or "fasit" in filename
        or "solution" in filename
    ):
        return get_unique_filename(lf_folder, filename)
    return get_unique_filename(oppgave_folder, filename)


def download_pdf(pdf_url, source="link"):
    """Downloads a PDF from the given URL."""
    filename = get_pdf_filename(pdf_url)
    try:
        pdf_response = requests.get(pdf_url, timeout=30)
        pdf_response.raise_for_status()

        with open(filename, "wb") as f:
            f.write(pdf_response.content)
        downloaded_pdfs.append(filename)
        print(f"✓ Downloaded ({source}): {os.path.basename(filename)}")
        return True
    except requests.RequestException as e:
        print(f"✗ Failed to download {pdf_url}: {e}")
        return False


downloaded_urls = set()


# Find all <a> links ending in .pdf
for link in soup.find_all("a", href=True):
    href = link["href"]
    if ".pdf" not in href:
        continue
    pdf_url = urljoin(url, href)
    if pdf_url not in downloaded_urls:
        if download_pdf(pdf_url, source="embed"):
            downloaded_urls.add(pdf_url)

for main_tag in soup.find_all("main", class_="pdf-document"):
    pdf_url = main_tag.get("data-pdf")
    if pdf_url:
        pdf_url = urljoin(url, pdf_url)
        if pdf_url not in downloaded_urls:
            if download_pdf(pdf_url, source="embed"):
                downloaded_urls.add(pdf_url)


# Summary Output
print("\n" + "=" * 50)
if downloaded_pdfs:
    print(f"✓ Successfully downloaded {len(downloaded_pdfs)} PDF file(s) to:")
    print(f"  {os.path.abspath(folder_location)}")
else:
    print("⚠ No PDF files were downloaded.")
print("=" * 50)
