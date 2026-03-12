from datetime import datetime
import sqlite3
import shutil
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path
import re

from platformdirs import user_documents_dir

# CHECK IF HIGHLIGHTTYPE COLUMN EXISTS
def has_color_column(conn):
    columns = [col[1] for col in conn.execute("PRAGMA table_info(Bookmark)").fetchall()]
    return "Color" in columns


HIGHLIGHT_COLORS = {
    0: "#F6E27A",  # Yellow
    1: "#F8BBD0",  # Pink
    2: "#A8DCFF",  # Blue
    3: "#A2DEAA",  # Green
}

HIGHLIGHT_NAMES = {
    0: "Yellow",
    1: "Pink",
    2: "Blue",
    3: "Green",
}

OUTPUT_DIR = Path(user_documents_dir()) / "Kobo Highlights"

EPUB_CHAPTER_CACHE = {}
DEBUG_CHAPTERS = True

# ------------------------------------------------
# FIND KOBO DATABASE
# ------------------------------------------------

import psutil
from pathlib import Path

def find_kobo_database():

    for p in psutil.disk_partitions():

        mount = Path(p.mountpoint)

        db = mount / ".Kobo" / "KoboReader.sqlite"

        if db.exists():
            return db

    raise Exception("KoboReader.sqlite not found. Is the Kobo connected?")

def find_kobo_root():

    for p in psutil.disk_partitions():
        mount = Path(p.mountpoint)

        if (mount / ".Kobo").exists():
            return mount

    return None
# ------------------------------------------------
# COPY DATABASE SAFELY
# ------------------------------------------------

from platformdirs import user_cache_dir
from pathlib import Path
import sqlite3
import shutil

def copy_database(src):

    work_dir = Path(user_cache_dir("kobo-highlights"))
    work_dir.mkdir(parents=True, exist_ok=True)

    dest = work_dir / "KoboReader_WORKING_COPY.sqlite"

    shutil.copy2(src, dest)

    return dest

# ------------------------------------------------
# ___FileSize or FileSize dynamic detection
# ------------------------------------------------

def get_filesize_column(conn):
    columns = [col[1] for col in conn.execute("PRAGMA table_info(content)").fetchall()]
    if "___FileSize" in columns:
        return "___FileSize"
    elif "FileSize" in columns:
        return "FileSize"
    else:
        return None  


# ------------------------------------------------
# GET BOOK LIST
# ------------------------------------------------

def get_books(conn):

    return conn.execute("""

        SELECT
            c.ContentID,
            c.Title,
            c.Attribution,
            MAX(bm.DateCreated) as LastHighlight

        FROM content c

        JOIN Bookmark bm
            ON bm.VolumeID = c.ContentID

        WHERE c.ContentType = 6
        AND c.BookID IS NULL

        GROUP BY c.ContentID

        ORDER BY c.Title

    """).fetchall()

# ------------------------------------------------
# CLEAN CONTENT ID
# ------------------------------------------------

def clean_content_id(content_id):

    if not content_id:
        return ""

    if "#kobo." in content_id:
        content_id = content_id.split("#kobo.")[0]

    return content_id.replace("\\", "/")
    
def clean_kobo_text(text):
    if not text:
        return ""

    # Normalize Windows line breaks
    text = text.replace("\r\n", "\n").replace("\r", "\n")

    # Replace tabs but preserve line structure
    text = text.replace("\t", " ")

    # Remove trailing spaces per line but keep line breaks
    lines = [line.strip() for line in text.split("\n")]

    return "\n".join(lines).strip()


# ------------------------------------------------
# RESOLVE CHAPTER TITLE
# ------------------------------------------------

def resolve_chapter(conn, volume_id, content_id):

    clean = clean_content_id(content_id)

    rows = conn.execute("""
        SELECT Title, ContentID
        FROM content
        WHERE BookID = ?
        AND (
            ContentID = ?
            OR ContentID LIKE ?
        )
        ORDER BY LENGTH(ContentID) DESC
    """, (volume_id, clean, clean + "%")).fetchall()

    for title, cid in rows:

        if not title:
            continue

        return title

    return None
    

# PARENT CHAPTER FALLBACK (Kobo / OverDrive books)
def resolve_parent_chapter(conn, volume_id, content_id):

    clean = clean_content_id(content_id)

    # convert part04_sub03.xhtml -> part04.xhtml
    parent = re.sub(
        r'(_sub\d+|_split_\d+)\.(xhtml|html)$',
        r'.\2',
        clean,
        flags=re.IGNORECASE
    )

    if not parent or parent == clean:
        return None

    rows = conn.execute("""
        SELECT Title
        FROM content
        WHERE BookID = ?
        AND ContentID LIKE ?
        ORDER BY LENGTH(ContentID) DESC
    """, (volume_id, "%" + parent + "%")).fetchall()

    for (title,) in rows:

        if not title:
            continue

        # Skip titles that look like file paths
        if re.search(r'\.xhtml$|\.html$|/|\\', title):
            continue

        return title

    return None

# ------------------------------------------------
# DETECT EPUB VS KEPUB
# ------------------------------------------------

def detect_type(conn, volume_id):

    row = conn.execute("""

        SELECT ContentID
        FROM content
        WHERE BookID = ?
        LIMIT 1

    """, (volume_id,)).fetchone()

    if not row:
        return "unknown"

    cid = row[0].lower()

    if "kepub" in cid or "ubiquitous" in cid:
        return "kepub"

    return "epub"

def is_sideloaded_epub(conn, volume_id):

    row = conn.execute("""
        SELECT ContentID
        FROM Bookmark
        WHERE VolumeID = ?
        LIMIT 1
    """, (volume_id,)).fetchone()

    if not row:
        return False

    content_id = row[0].lower()

    return (
        "file:///mnt/onboard" in content_id
        or "/mnt/onboard/" in content_id
        or ".kepub.epub!!" in content_id
    )

# GET EPUB PATH (Fallback Resolver Helper) 
def get_epub_path(conn, volume_id):
    """
    Locate the EPUB/Kepub file for a given volume on a connected Kobo device.
    Works for both Windows and macOS/Linux sideloaded EPUBs.
    Returns a Path object or None if not found.
    """
    row = conn.execute("""
        SELECT ContentID
        FROM content
        WHERE ContentID = ?
    """, (volume_id,)).fetchone()  # Use ContentID like old script

    if not row:
        return None

    cid = row[0]

    if not cid.startswith("file:///"):
        return None

    # Remove file:// URL prefix
    relative = cid.replace("file:///", "")

    # Default fallback: check common Kobo mount points
    possible_roots = []

    # On Windows, often E:/, F:/, G:/
    for drive in "EFG":
        possible_roots.append(Path(f"{drive}:/"))

    # On Linux/macOS, dynamically detect via psutil if available
    try:
        import psutil
        for p in psutil.disk_partitions():
            mount = Path(p.mountpoint)
            if (mount / ".Kobo").exists():
                possible_roots.append(mount)
    except ImportError:
        pass

    # Iterate possible roots to find EPUB
    for root in possible_roots:
        epub_path = root / relative.replace("mnt/onboard/", "")
        if epub_path.exists():
            return epub_path

    print(f"[EPUB FALLBACK] EPUB file not found for volume {volume_id}")
    return None

# ------------------------------------------------
# DETECT SPINE COLUMN (SpineIndex or VolumeIndex)
# ------------------------------------------------

def get_spine_column(conn):

    columns = conn.execute("""
        PRAGMA table_info(content)
    """).fetchall()

    column_names = {col[1] for col in columns}

    if "SpineIndex" in column_names:
        return "SpineIndex"

    return "VolumeIndex"


# ------------------------------------------------
# UNIVERSAL HIGHLIGHTS (EPUB + KEPUB)
# ------------------------------------------------

# EPUB STRUCTURAL RESOLVER (Fallback Only)
def build_epub_chapter_map(epub_path):

    chapter_map = {}

    with zipfile.ZipFile(epub_path, 'r') as z:

        # ------------------------------------------------
        # 1. Locate OPF
        # ------------------------------------------------
        container = ET.fromstring(z.read("META-INF/container.xml"))
        rootfile = container.find(".//{*}rootfile")
        opf_path = rootfile.attrib["full-path"]
        opf_dir = Path(opf_path).parent

        opf = ET.fromstring(z.read(opf_path))
        ns = {"n": opf.tag.split("}")[0].strip("{")}

        # ------------------------------------------------
        # 2. Manifest map (id -> href)
        # ------------------------------------------------
        manifest = {}
        for item in opf.findall(".//n:manifest/n:item", ns):
            manifest[item.attrib["id"]] = item.attrib["href"]

        # ------------------------------------------------
        # 3. Spine list (ordered HTML files)
        # ------------------------------------------------
        spine_files = []
        for itemref in opf.findall(".//n:spine/n:itemref", ns):
            idref = itemref.attrib["idref"]
            href = manifest.get(idref)
            if href:
                spine_files.append(Path(href).name)

        # ------------------------------------------------
        # 4. Try EPUB2 TOC (toc.ncx)
        # ------------------------------------------------
        toc_href = None

        # Look for ncx in manifest
        for item in opf.findall(".//n:manifest/n:item", ns):
            media = item.attrib.get("media-type", "")
            if media == "application/x-dtbncx+xml":
                toc_href = item.attrib.get("href")
                break

        toc_map = {}

        if toc_href:
            try:
                toc_path = str(opf_dir / toc_href).replace("\\", "/")
                toc_xml = ET.fromstring(z.read(toc_path))

                for navpoint in toc_xml.findall(".//{*}navPoint"):
                    label = navpoint.find(".//{*}text")
                    content = navpoint.find(".//{*}content")

                    if label is not None and content is not None:
                        title = "".join(label.itertext()).strip()
                        src = content.attrib.get("src", "")

                        file_name = src.split("#")[0]
                        file_name = Path(file_name).name

                        if title and file_name:
                            toc_map[file_name] = title

            except Exception:
                pass

        # ------------------------------------------------
        # 5. If no toc.ncx found, try EPUB3 nav.xhtml
        # ------------------------------------------------
        if not toc_map:

            nav_href = None

            for item in opf.findall(".//n:manifest/n:item", ns):
                props = item.attrib.get("properties", "")
                if "nav" in props:
                    nav_href = item.attrib.get("href")
                    break

            if nav_href:
                try:
                    nav_path = str(opf_dir / nav_href).replace("\\", "/")
                    nav_xml = ET.fromstring(z.read(nav_path))

                    for link in nav_xml.findall(".//{*}a"):
                        href = link.attrib.get("href", "")
                        text = "".join(link.itertext()).strip()

                        file_name = href.split("#")[0]
                        file_name = Path(file_name).name

                        if text and file_name:
                            toc_map[file_name] = text

                except Exception:
                    pass

        # ------------------------------------------------
        # 6. If TOC found → map by range logic
        # ------------------------------------------------
        if toc_map:

            current_title = None

            for index, file in enumerate(spine_files):

                if file in toc_map:
                    current_title = toc_map[file]

                if current_title:
                    chapter_map[index] = current_title
                else:
                    chapter_map[index] = file

            return chapter_map

        # ------------------------------------------------
        # 7. Faster fallback: partial chapter scanning
        # ------------------------------------------------

        for index, file in enumerate(spine_files):

            try:
                full_path = str(opf_dir / file).replace("\\", "/")

                # read only first part of chapter (usually contains title)
                raw = z.read(full_path)[:4096]

                text = raw.decode("utf-8", errors="ignore").lower()

                chapter_title = None

                # fast regex detection

                match = re.search(r"<h[1-3][^>]*>(.*?)</h[1-3]>", text)
                if match:
                    chapter_title = re.sub("<.*?>", "", match.group(1)).strip()

                if not chapter_title:
                    match = re.search(r"<title[^>]*>(.*?)</title>", text)
                    if match:
                        chapter_title = re.sub("<.*?>", "", match.group(1)).strip()

                if chapter_title:
                    chapter_map[index] = chapter_title
                else:
                    chapter_map[index] = file

            except Exception:
                chapter_map[index] = file

    return chapter_map


def get_highlights_universal(conn, volume_id, book_title=None, screen_type="BW", filesize_col=None):
    """
    Returns a list of highlights for a given volume, supporting KEPUB and sideloaded EPUBs.
    Correctly calculates Book and Chapter locations:
        - For EPUBs, Chapter Location = "-", Book Location = actual percentage.
        - For KEPUBs, both percentages are calculated normally.
    """
    epub_map = None
    spine_col = get_spine_column(conn)
    sideloaded = is_sideloaded_epub(conn, volume_id)
    
    if filesize_col is None:
        filesize_col = get_filesize_column(conn)

    # Determine if Color exists
    highlight_column_exists = has_color_column(conn)

    if screen_type == "Color" and highlight_column_exists:
        cursor = conn.execute("""
            SELECT Text, Annotation, ContentID, ChapterProgress, DateCreated, Color
            FROM Bookmark
            WHERE VolumeID = ?
            ORDER BY DateCreated
        """, (volume_id,))
    else:
        cursor = conn.execute("""
            SELECT Text, Annotation, ContentID, ChapterProgress, DateCreated
            FROM Bookmark
            WHERE VolumeID = ?
            ORDER BY DateCreated
        """, (volume_id,))

    highlights = []
    seen = set()

    # total spine size
    total_size = conn.execute(f"""
        SELECT SUM({filesize_col})
        FROM content
        WHERE BookID = ?
        AND ContentType IN (9, 899)
        AND {filesize_col} > 0
    """, (volume_id,)).fetchone()[0] or 1

    for row in cursor:
        # Unpack dynamically based on screen type
        if screen_type == "Color" and highlight_column_exists:
            text, note, content_id, chapter_progress, date_created, color = row
        else:
            text, note, content_id, chapter_progress, date_created = row
            color = None  # default for BW mode

        if not text and not note:
            continue

        clean_id = clean_content_id(content_id)
        key = (
            (text or "").strip(),
            (note or "").strip(),
            clean_id
        )
        if key in seen:
            continue
        seen.add(key)

        chapter_progress = chapter_progress if chapter_progress is not None else 0.0
        chapter_percent = chapter_progress * 100        

        chapter = resolve_chapter(conn, volume_id, content_id)

        if DEBUG_CHAPTERS:
            print("\n--- CHAPTER DEBUG ---")
            print("ContentID:", content_id)
            print("DB chapter:", chapter)

        looks_like_file = (
            not chapter
            or "/" in chapter
            or re.search(r'\.(xhtml|html)(#.*)?$', chapter, re.IGNORECASE)
        )

        if DEBUG_CHAPTERS:
            print("Looks like file:", bool(looks_like_file))
            print("Sideloaded:", sideloaded)

        if looks_like_file:

            if sideloaded:

                if DEBUG_CHAPTERS:
                    print("Using EPUB fallback")

                if volume_id not in EPUB_CHAPTER_CACHE:

                    print(f"[EPUB FALLBACK] {book_title} → Parsing EPUB")

                    epub_path = get_epub_path(conn, volume_id)

                    if epub_path and epub_path.exists():
                        EPUB_CHAPTER_CACHE[volume_id] = build_epub_chapter_map(epub_path)
                    else:
                        EPUB_CHAPTER_CACHE[volume_id] = {}

                epub_map = EPUB_CHAPTER_CACHE[volume_id]

            else:

                if DEBUG_CHAPTERS:
                    print("Using parent fallback")

                chapter = resolve_parent_chapter(conn, volume_id, content_id)

                if DEBUG_CHAPTERS:
                    print("Parent resolved:", chapter)

        # get spine index       
        chapter_info = conn.execute(f"""
            SELECT {spine_col}
            FROM content
            WHERE BookID = ?
            AND ContentType IN (9, 899)
            AND (
                ? LIKE ContentID || '%'
                OR ContentID LIKE ? || '%'
            )
            ORDER BY LENGTH(ContentID) DESC
            LIMIT 1
        """, (volume_id, clean_id, clean_id)).fetchone()

        spine_index = chapter_info[0] if chapter_info else 0

        # Apply EPUB fallback only if necessary
        if sideloaded and looks_like_file:
            if epub_map is not None and spine_index in epub_map:
                chapter_candidate = epub_map[spine_index]

                # Apply filename filter
                if (
                    not chapter_candidate
                    or "/" in chapter_candidate
                    or re.search(r'\.(xhtml|html)$', chapter_candidate, re.IGNORECASE)
                ):
                    chapter = None
                else:
                    chapter = chapter_candidate
            else:
                # EPUB fallback missing → set to None if original looks like file
                chapter = None

        if DEBUG_CHAPTERS:
            print("Final chapter:", chapter)

        # Convert timestamp to readable date
        try:
            date_str = datetime.fromisoformat(date_created.replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M")
        except:
            date_str = str(date_created)

        # size before for book percent
        size_before = conn.execute(f"""
            SELECT SUM({filesize_col})
            FROM content
            WHERE BookID = ?
            AND ContentType IN (9, 899)
            AND {filesize_col} > 0
            AND {spine_col} < ?
        """, (volume_id, spine_index)).fetchone()[0] or 0

        # current chapter size
        current_size = 0

        result = conn.execute(f"""
            SELECT {filesize_col}
            FROM content
            WHERE BookID = ?
            AND ContentType IN (9, 899)
            AND {spine_col} = ?
            AND {filesize_col} > 0
            LIMIT 1
        """, (volume_id, spine_index)).fetchone()

        if result and result[0] is not None:
            current_size = result[0]

        # Kobo-accurate calculation
        if total_size > 0:
            if sideloaded:
                # EPUB fallback: use ___FileSize, with 1 as fallback if missing
                current_size = current_size or 1
                book_percent = (size_before + chapter_progress * current_size) / total_size * 100
            else:
                # KEPUB
                book_percent = (size_before + chapter_progress * current_size) / total_size * 100
        else:
            book_percent = 0

        # EPUB exception
        # hide chapter percent only for sideloaded pure EPUBs
        if sideloaded and ".kepub.epub" not in content_id.lower():
            chapter_percent_display = "-"
        else:
            chapter_percent_display = round(chapter_percent, 2)

        highlight_dict = {
            "chapter": chapter,
            "spine_index": spine_index,
            "chapter_progress": chapter_progress,
            "text": clean_kobo_text(text),
            "annotation": clean_kobo_text(note),
            "chapter_percent": chapter_percent_display,
            "book_percent": round(book_percent, 2),
            "date": date_str,
        }

        # only add Color if relevant
        if color is not None:
            highlight_dict["Color"] = color

        highlights.append(highlight_dict)

    return highlights


# ------------------------------------------------
# WRITE MARKDOWN
# ------------------------------------------------

def sanitize_filename(name):
    return re.sub(r'[<>:"/\\|?*]', '', name).strip()


def write_markdown(title, author, highlights, screen_type="BW"):

    if not highlights:
        print("Skipping empty:", title)
        return
    
    highlights.sort(
        key=lambda h: ((h["spine_index"] or 0), h["chapter_progress"])
    )

    safe_title = sanitize_filename(title)
    path = OUTPUT_DIR / f"{safe_title}.md"

    with open(path, "w", encoding="utf-8") as f:
        f.write(f"# {title}\n")
        if author:
            f.write(f"Author: {author}\n")
        f.write(f"Highlights: {len(highlights)}\n")
        f.write("\n---\n\n")

        last_chapter = None

        for highlight in highlights:

            chapter = highlight["chapter"] or "Unknown chapter"

            # Print chapter header when it changes
            if chapter != last_chapter:
                f.write(f"## {chapter}\n\n")

            if highlight["text"]:
                quote_lines = highlight["text"].split("\n")

                if screen_type == "Color" and "Color" in highlight:
                    color = HIGHLIGHT_COLORS.get(highlight["Color"], "#F6E27A")
                    name = HIGHLIGHT_NAMES.get(highlight["Color"], "Yellow")
                    f.write(f"> [!quote] <span style=\"color:{color};\">⬤</span> *{name}*\n")
                else:
                    f.write("> [!quote]\n")

                for line in quote_lines:
                    if line.strip():
                        f.write(f"> {line}\n")
                    else:
                        f.write(">\n")
                f.write("\n")

            if highlight.get("annotation"):
                f.write("Note:\n")
                for line in highlight["annotation"].split("\n"):
                    f.write(f"    {line}\n")
                f.write("\n")
                
            # --- Compact metadata line ---
            meta = []

            # Only add Book location if available
            if highlight["book_percent"] is not None:
                meta.append(f"Book location: {highlight['book_percent']}%")
                
            # Only add Chapter location if it's not "-"
            if highlight["chapter_percent"] != "-":
                meta.append(f"Chapter location: {highlight['chapter_percent']}%")

            # Only add Date if available
            if highlight["date"]:
                meta.append(f"Date: {highlight['date']}")

            # Write as a single line in Markdown
            f.write(" | ".join(meta) + "\n")
            f.write("\n---\n\n")

            # Special rule so "Unknown chapter" never merges
            if chapter == "Unknown chapter":
                last_chapter = None
            else:
                last_chapter = chapter

    print("Created:", path)


# ------------------------------------------------
# MAIN
# ------------------------------------------------

def main():

    OUTPUT_DIR.mkdir(exist_ok=True)

    db = find_kobo_database()

    print("Kobo database found:", db)

    db_copy = copy_database(db)

    print("Database copied to:", db_copy)

    conn = sqlite3.connect(db_copy)
    filesize_col = get_filesize_column(conn)

    books = get_books(conn)

    print(len(books), "books found\n")

    for volume_id, title, author, _ in books:

        print("Processing:", title)

        book_type = detect_type(conn, volume_id)

        print("Type:", book_type)

        highlights = get_highlights_universal(conn, volume_id, title, filesize_col=filesize_col)

        write_markdown(title, author, highlights)

        print()


if __name__ == "__main__":
    main()