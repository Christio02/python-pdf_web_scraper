# Author: Scott Grivner (original), adapted for dynamic column detection
# Abstract: Scrape NTNU exam pages for PDF files and download them.

import os
from urllib.parse import parse_qs, unquote, urljoin, urlparse

import requests
from bs4 import BeautifulSoup

urls = [
    "https://www.ntnu.no/fysikk/eksamen/landing/-/asset_publisher/uwSAlUJoweyy/content/tfy4125-fysikk"
]

folder_location = r"./downloads"
lf_folder = os.path.join(folder_location, "lf")
oppgave_folder = os.path.join(folder_location, "oppgave")

for folder in [folder_location, lf_folder, oppgave_folder]:
    os.makedirs(folder, exist_ok=True)


def get_unique_filepath(folder, filename):
    base, ext = os.path.splitext(filename)
    candidate = os.path.join(folder, filename)
    counter = 2
    while os.path.exists(candidate):
        candidate = os.path.join(folder, f"{base} ({counter}){ext}")
        counter += 1
    return candidate


def get_pdf_filename(pdf_url):
    parsed = urlparse(pdf_url)
    filename = None

    if "ntnu.no/documents" in pdf_url:
        filename = unquote(os.path.basename(parsed.path))

    elif "fetch.php" in parsed.path:
        params = parse_qs(parsed.query)
        if "media" in params:
            media_url = params["media"][0]
            filename = os.path.basename(urlparse(media_url).path)

    if not filename:
        filename = os.path.basename(parsed.path)

    if filename:
        filename = unquote(filename)

    if not filename or not filename.lower().endswith(".pdf"):
        filename = "Downloaded_PDF.pdf"

    return filename


def is_lf_filename(filename):
    name = filename.lower()
    return any(
        kw in name
        for kw in [
            "lf",
            "losning",
            "løsning",
            "losningsforslag",
            "fasit",
            "solution",
            "sol",
            "soln",
            "answer",
            "ans",
            "korrektur",
        ]
    )


def detect_column_roles(table):
    """
    Inspect the <thead> (or first <tr> with <th>) to map column indices
    to roles: 'oppgave', 'lf', or None.
    Returns a dict: {col_index: 'oppgave' | 'lf' | None}
    """

    OPPGAVE_KEYWORDS = {
        "bokmål",
        "bm",
        "oppgaver",
        "problems",
        "problem",
        "nb",
        "nn",
        "nynorsk",
        "english",
        "en",
        "eksamensoppgave",
    }
    LF_KEYWORDS = {
        "løsningsforslag",
        "løsning",
        "solution",
        "solutions",
        "lf",
        "fasit",
    }

    header_row = None
    thead = table.find("thead")
    if thead:
        header_row = thead.find("tr")
    if not header_row:
        # Fall back to first row if it contains <th>
        for row in table.find_all("tr"):
            if row.find("th"):
                header_row = row
                break

    if not header_row:
        return {}

    roles = {}
    col_index = 0
    for cell in header_row.find_all(["th", "td"]):
        text = cell.get_text(strip=True).lower()
        colspan = int(cell.get("colspan", 1))

        role = None
        if any(kw in text for kw in LF_KEYWORDS):
            role = "lf"
        elif any(kw in text for kw in OPPGAVE_KEYWORDS):
            role = "oppgave"

        for i in range(colspan):
            roles[col_index + i] = role
        col_index += colspan

    return roles


def resolve_rows_with_rowspan(table):
    """
    Expands a table's rows accounting for rowspan, returning a list of
    lists where each inner list contains (cell, role_hint) per logical column.
    Only returns actual <td> cells (skips <th> header cells in body rows).
    """
    # Build a grid: grid[row][col] = tag or None
    grid = []
    # pending[(row, col)] = tag — cells that span into future rows
    pending = {}

    rows = table.find_all("tr")
    for row_idx, row in enumerate(rows):
        # Skip pure header rows
        cells = row.find_all(["td", "th"])
        if all(c.name == "th" for c in cells):
            continue

        grid_row = {}
        # First, fill in pending (rowspan) cells
        for (r, c), tag in list(pending.items()):
            if r == row_idx:
                grid_row[c] = tag

        # Now place actual cells
        col_cursor = 0
        for cell in cells:
            # Skip to next free slot
            while col_cursor in grid_row:
                col_cursor += 1

            rowspan = int(cell.get("rowspan", 1))
            colspan = int(cell.get("colspan", 1))

            for dc in range(colspan):
                grid_row[col_cursor + dc] = cell
                for dr in range(1, rowspan):
                    pending[(row_idx + dr, col_cursor + dc)] = cell

            col_cursor += colspan

        # Clean up pending entries we just consumed
        for key in [k for k in pending if k[0] == row_idx]:
            del pending[key]

        if grid_row:
            grid.append(grid_row)

    return grid


def download_pdf(pdf_url, category, downloaded_urls):
    if pdf_url in downloaded_urls:
        return
    filename = get_pdf_filename(pdf_url)

    # Use category from column role if available, else infer from filename
    if category == "lf":
        folder = lf_folder
    elif category == "oppgave":
        folder = oppgave_folder
    else:
        folder = lf_folder if is_lf_filename(filename) else oppgave_folder

    filepath = get_unique_filepath(folder, filename)

    try:
        response = requests.get(pdf_url, timeout=30)
        response.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(response.content)
        downloaded_urls.add(pdf_url)
        print(f"✓ [{category or 'auto'}] {os.path.basename(filepath)}")
    except requests.RequestException as e:
        print(f"✗ Failed {pdf_url}: {e}")


def scrape_url(url):
    print(f"\n{'=' * 60}")
    print(f"Scraping: {url}")
    print("=" * 60)

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException as e:
        print(f"Failed to fetch page: {e}")
        return

    soup = BeautifulSoup(response.text, "html.parser")

    # Remove midtsemester section if present
    mid_heading = soup.find("h2", id="tidligere_midtsemesterprover_med_fasit")
    if mid_heading:
        section = mid_heading.find_next_sibling("div", class_="level2")
        if section:
            section.decompose()
            print("Excluded midtsemester section.")

    downloaded_urls = set()
    total = 0

    for table in soup.find_all("table"):
        roles = detect_column_roles(table)
        if not roles:
            continue

        grid = resolve_rows_with_rowspan(table)

        exam_count = 0
        for grid_row in grid:
            if exam_count >= 30:
                break
            row_has_oppgave = any(
                roles.get(col_idx) == "oppgave" and cell.find("a", href=True)
                for col_idx, cell in grid_row.items()
            )
            if row_has_oppgave:
                exam_count += 1
            for col_idx, cell in grid_row.items():
                role = roles.get(col_idx)
                if role not in ("oppgave", "lf"):
                    continue

                for link in cell.find_all("a", href=True):
                    href = link["href"]
                    if ".pdf" not in href.lower():
                        continue
                    pdf_url = urljoin(url, href)
                    if pdf_url not in downloaded_urls:
                        download_pdf(pdf_url, role, downloaded_urls)
                        total += 1

    print(f"\n✓ Downloaded {total} PDF(s) from this page.")


for url in urls:
    scrape_url(url)

print(f"\n{'=' * 60}")
print(f"All done. Files saved to: {os.path.abspath(folder_location)}")
print("=" * 60)
