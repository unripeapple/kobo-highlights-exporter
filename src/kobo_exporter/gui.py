import sys
import os
import json
import sqlite3
import threading
import webbrowser
import ctypes
from pathlib import Path
import ctypes.wintypes

if sys.platform.startswith("win"):
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass
            
import customtkinter as ctk
from tkinter import filedialog, messagebox
from PIL import Image, ImageTk
import requests
import tkinter as tk
import tkinter.font as tkFont

APP_VERSION = "1.0.0"
GITHUB_API = "https://api.github.com/repos/unripeapple/kobo-highlights-exporter/releases/latest"

# SINGLE INSTANCE (Windows only)
mutex = None
if sys.platform.startswith("win"):
    mutex_name = "Global\\KoboHighlightsExtractorSingleton"
    mutex = ctypes.windll.kernel32.CreateMutexW(None, False, mutex_name)
    last_error = ctypes.windll.kernel32.GetLastError()

    if last_error == 183:
        sys.exit(0)

    ctypes.windll.kernel32.CloseHandle.argtypes = [ctypes.wintypes.HANDLE]
    ctypes.windll.kernel32.CloseHandle.restype = ctypes.wintypes.BOOL

_root = tk.Tk()
_available_fonts = tkFont.families()
_root.destroy()

# Cross-platform default font
if sys.platform.startswith("win"):
    DEFAULT_FONT = "Segoe UI" if "Segoe UI" in _available_fonts else "Arial"
elif sys.platform.startswith("darwin"):
    DEFAULT_FONT = "Helvetica" if "Helvetica" in _available_fonts else "Arial"
else:
    # Linux fallback list
    for f in ["DejaVu Sans", "Liberation Sans", "Arial", "Sans"]:
        if f in _available_fonts:
            DEFAULT_FONT = f
            break
    else:
        DEFAULT_FONT = "Sans"

# RESOURCE PATH FUNCTION
def resource_path(relative_path):

    if hasattr(sys, "_MEIPASS"):
        base_path = sys._MEIPASS
    else:
        base_path = os.path.dirname(os.path.abspath(__file__))

    return os.path.join(base_path, relative_path)

def safe_set_icon(window, ico_path="app_icon.ico", png_path="app_icon.png"):
    if sys.platform.startswith("win"):
        try:
            window.iconbitmap(resource_path(ico_path))
            return
        except Exception:
            pass

    # Fallback for macOS/Linux
    try:
        img = Image.open(resource_path(png_path))
        size = (64, 64)  # a reasonable universal size
        window._icon_images = [ImageTk.PhotoImage(img.resize(size))]
        window.wm_iconphoto(True, *window._icon_images)
    except Exception:
        pass

# import your existing functions
from kobo_exporter.core import (
    find_kobo_database,
    copy_database,
    get_books,
    get_highlights_universal,
    write_markdown,
)

import kobo_exporter.core as core

SETTINGS_FILE = "settings.json"

ctk.set_appearance_mode("dark")

class ToolTip:
    def __init__(self, widget, text):
        self.widget = widget
        self.text = text
        self.tip_window = None
        self.after_id = None


        widget.bind("<Enter>", self.schedule_show)
        widget.bind("<Leave>", self.hide_tip)
        widget.bind("<ButtonPress>", self.hide_tip)

    def schedule_show(self, event=None):
        self.after_id = self.widget.after(300, self.show_tip)  # small delay

    def show_tip(self):
        if self.tip_window:
            return

        x = self.widget.winfo_rootx() + self.widget.winfo_width() + 10
        y = self.widget.winfo_rooty()

        self.tip_window = tw = ctk.CTkToplevel(self.widget)
        tw.overrideredirect(True)
        tw.geometry(f"+{x}+{y}")
        tw.attributes("-topmost", True)

        frame = ctk.CTkFrame(
            tw,
            fg_color="#141432",
            corner_radius=8,
            border_width=1,
            border_color="#654c80"
        )
        frame.pack()

        label = ctk.CTkLabel(
            frame,
            text=self.text,
            text_color="#ffffff",
            justify="left",
            padx=12,
            pady=8,
            wraplength=220
        )
        label.pack()

    def hide_tip(self, event=None):
        if self.after_id:
            self.widget.after_cancel(self.after_id)
            self.after_id = None

        if self.tip_window:
            self.tip_window.destroy()
            self.tip_window = None
            

class KoboApp(ctk.CTk):
    
    def check_for_updates(self):
        try:
            r = requests.get(GITHUB_API, timeout=3)
            if r.status_code != 200:
                return

            data = r.json()
            latest_version = data["tag_name"].replace("v", "")
            release_url = data["html_url"]

            if latest_version != APP_VERSION:
                self.ask_update(latest_version, release_url)

        except Exception:
            pass
    

    def __init__(self):
        super().__init__()

        self.title("Kobo Highlights Exporter")
        self.geometry("900x650")
        self.minsize(800, 600)
        self.protocol("WM_DELETE_WINDOW", self.safe_close)
        
        safe_set_icon(
            self,
            ico_path="assets/app_icon.ico",
            png_path="assets/app_icon.png"
        )
        
        # Load info icon image
        self.info_icon = ctk.CTkImage(
            light_image=Image.open(resource_path("assets/info_icon.png")),
            dark_image=Image.open(resource_path("assets/info_icon.png")),
            size=(16, 16)
        )
        
        # Illustration
        self.kobo_illustration = ctk.CTkImage(
            light_image=Image.open(resource_path("assets/illustration.png")),
            dark_image=Image.open(resource_path("assets/illustration.png")),
            size=(140, 140)  # 👈 control displayed size here
        )
        
         
        #🎨 MAIN WINDOW BACKGROUND COLOR
        self.configure(fg_color="#1d1d42")
        
        # --- MAIN CONTAINER (for screens) ---
        self.main_container = ctk.CTkFrame(self, fg_color="#1d1d42")
        self.main_container.grid(row=0, column=0, sticky="nsew", padx=0, pady=0)

        self.grid_rowconfigure(0, weight=1)  # main container expands
        self.grid_columnconfigure(0, weight=1)
        
        # --- FOOTER FRAME ---
        self.footer_frame = ctk.CTkFrame(self, fg_color="#1d1d42")  # same as window background
        self.footer_frame.grid(row=1, column=0, sticky="ew")
        self.grid_rowconfigure(1, weight=0)  # footer row should not expand

        # Footer label
        self.footer_frame.grid_columnconfigure(0, weight=1)
        self.footer_frame.grid_columnconfigure(1, weight=0)

        # left text
        self.footer_label = ctk.CTkLabel(
            self.footer_frame,
            text=f"Kobo Highlights Exporter v{APP_VERSION} by Unripe apple",
            font=(DEFAULT_FONT, 12),
            text_color="#aaaaaa",
        )
        self.footer_label.grid(row=0, column=0, sticky="w", padx=10, pady=4)

        # donate link
        self.donate_label = ctk.CTkLabel(
            self.footer_frame,
            text="[donate]",
            font=(DEFAULT_FONT, 12, "underline"),
            text_color="#fdd886",
            cursor="hand2"
        )
        self.donate_label.grid(row=0, column=1, sticky="e", padx=10)

        self.donate_label.bind(
            "<Button-1>",
            lambda e: webbrowser.open("https://ko-fi.com/unripe_apple")
        )      
        
        #Slightly larger default font for better proportion
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)

        self.db_path = None
        self.conn = None
        self.books = []
        self.checkboxes = []

        self.output_dir = Path("output")
        self.saved_screen_type = "BW"   # default
        self.load_settings()

        #🎨 GLOBAL BUTTON STYLE
        self.BUTTON_BG = "#765996"
        self.BUTTON_HOVER = "#654c80"
        self.BUTTON_TEXT = "#ffffff"

        self.ACCENT_BG = "#fdd886"
        self.ACCENT_HOVER = "#e5c46a"
        self.ACCENT_TEXT = "#000000"

        # show the "No Kobo device" screen immediately
        self.show_start_screen()
        
        # then try detecting after UI loads
        self.after(300, lambda: self.try_find_kobo(show_popup=False))
        
        # check updates in background
        threading.Thread(target=self.check_for_updates, daemon=True).start()
        
    
    def safe_close(self):
        global mutex
        try:
            if mutex:
                ctypes.windll.kernel32.CloseHandle(mutex)
                mutex = None
        except Exception:
            pass
            
        try:
            if hasattr(self, "conn") and self.conn:
                self.conn.close()
        except:
            pass

        # Safely destroy all children first
        for widget in list(self.winfo_children()):
            try:
                widget.destroy()
            except Exception:
                pass

        try:
            self.destroy()
        except Exception:
            # fallback: force quit
            import sys
            sys.exit(0)
    
    # -------------------------
    # SETTINGS
    # -------------------------

    def load_settings(self):

        self.saved_screen_type = "BW"
        self.output_dir = Path("output")

        if Path(SETTINGS_FILE).exists():
            with open(SETTINGS_FILE) as f:
                data = json.load(f)

            self.output_dir = Path(data.get("output_dir", "output"))
            self.saved_screen_type = data.get("screen_type", "BW")

    def save_settings(self):
        with open(SETTINGS_FILE, "w") as f:
            json.dump({
                "output_dir": str(self.output_dir),
                "screen_type": self.screen_var.get()
            }, f)

    # ------------------------------------------------
    # START SCREEN (UI V2)
    # ------------------------------------------------

    def show_start_screen(self):

        self.clear()

        container = self.styled_frame(self.main_container)
        container.grid(row=0, column=0, sticky="nsew", padx=40, pady=20)
        
        self.main_container.grid_rowconfigure(0, weight=1)
        self.main_container.grid_columnconfigure(0, weight=1)
        
        # Central frame for vertical centering
        center_frame = ctk.CTkFrame(container, fg_color="transparent")
        center_frame.pack(expand=True)  # this will center it vertically

        title = ctk.CTkLabel(
            center_frame,
            text="No Kobo device found",
            font=(DEFAULT_FONT, 22)
        )
        title.pack(pady=(30, 20))
        
        illustration_label = ctk.CTkLabel(
            center_frame,
            text="",
            image=self.kobo_illustration
        )
        illustration_label.pack(pady=(10, 30))

        button_block = ctk.CTkFrame(center_frame, fg_color="#1d1d42")
        button_block.pack(pady=20)
     
        # ---- TRY AGAIN BUTTON ----
        try_btn = self.styled_button(
            button_block,
            "Search Again",
            command=self.try_find_kobo,
            width=300,
            accent=True
        )
        try_btn.pack(pady=(0, 15))

        # ---- UPLOAD BUTTON ----
        upload_btn = self.styled_button(
            button_block,
            "Select Kobo Database",
            command=self.upload_database,
            width=300
        )
        upload_btn.pack()

        # ---- INFO BUTTON (separate row, aligned right) ----
        info_row = ctk.CTkFrame(button_block, fg_color="#1d1d42")
        info_row.pack(fill="x")

        info_row.columnconfigure(0, weight=1)

        info_btn = ctk.CTkButton(
            info_row,
            text="",
            image=self.info_icon,
            width=18,
            height=18,
            fg_color="#1d1d42",
        )
        info_btn.grid(row=0, column=1, sticky="e", padx=(0, 5), pady=(6, 0))

        ToolTip(
            info_btn,
            """Select the file: KoboReader.sqlite

        Important:
        - Never open the file directly from your Kobo device.
        - Always select a copy saved on your computer."""
        )
        
    def try_find_kobo(self, show_popup=True):
        try:
            self.db_path = find_kobo_database()  # may raise Exception if not found
        except Exception as e:
            if show_popup:
                messagebox.showwarning(
                    "Kobo not found",
                    f"Kobo not found!\n\nCheck if your device is connected and try again.\n\nDetails: {e}",
                    parent=self
                )
            else:
                # silently update a label instead of popup
                if hasattr(self, "status_label"):
                    self.status_label.config(text="Kobo device not found")
            return

        print("Kobo DB path:", self.db_path)

        try:
            self.prepare_database()
        except Exception as e:
            messagebox.showerror("Error preparing database", str(e), parent=self)

    def upload_database(self):
        path = filedialog.askopenfilename(
            filetypes=[("SQLite file", "*.sqlite")]
        )

        if path:
            self.db_path = Path(path)
            self.prepare_database()

    # -------------------------
    # PREPARE DATABASE
    # -------------------------

    def prepare_database(self):

        db_copy = copy_database(self.db_path)
        self.db_copy_path = db_copy

        self.conn = sqlite3.connect(db_copy)
        self.all_books = get_books(self.conn)
        self.books = list(self.all_books)
        self.filesize_col = core.get_filesize_column(self.conn)

        # Precompute highlight counts
        self.highlight_counts = {}
        for volume_id, title, author, last_highlight in self.all_books:
            highlights = get_highlights_universal(
                self.conn,
                volume_id,
                book_title=title,
                screen_type=self.saved_screen_type,
                filesize_col=self.filesize_col
            )
            self.highlight_counts[volume_id] = len(highlights)

        self.show_main_screen()

    # ------------------------------------------------
    # MAIN SCREEN (UI V2)
    # ------------------------------------------------

    def show_main_screen(self):

        self.clear()
        
        self.main_container.grid_columnconfigure(0, weight=1)
        self.main_container.grid_rowconfigure(0, weight=1)

        main_frame = ctk.CTkFrame(self.main_container, fg_color="#1d1d42")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        # Configure row weights so only the books frame expands
        main_frame.grid_rowconfigure(0, weight=0)  # header
        main_frame.grid_rowconfigure(1, weight=0)  # sort frame
        main_frame.grid_rowconfigure(2, weight=0)  # search
        main_frame.grid_rowconfigure(3, weight=0)  # select all
        main_frame.grid_rowconfigure(4, weight=1)  # books scrollable frame -> expands
        main_frame.grid_rowconfigure(5, weight=0)  # screen type
        main_frame.grid_rowconfigure(6, weight=0)  # folder
        main_frame.grid_rowconfigure(7, weight=0)  # progress
        main_frame.grid_rowconfigure(8, weight=0)  # buttons
        main_frame.grid_columnconfigure(0, weight=1)  # make the column expand horizontally
        

        # 👇 Header section
        header = ctk.CTkLabel(
            main_frame,
            text=f"{len(self.books)} books found",
            font=(DEFAULT_FONT, 18)
        )
        header.grid(row=0, column=0, pady=(20,5))
        
        # ---- SORT DROPDOWN ----

        sort_frame = ctk.CTkFrame(main_frame, fg_color="#1d1d42")
        sort_frame.grid(row=1, column=0, sticky="ew", padx=40, pady=(0,5))

        # Push everything to right
        sort_frame.columnconfigure(0, weight=1)

        right_group = ctk.CTkFrame(sort_frame, fg_color="#1d1d42")
        right_group.grid(row=0, column=1, sticky="e")

        sort_label = ctk.CTkLabel(
            right_group,
            text="Sort by",
            font=(DEFAULT_FONT, 13)
        )
        sort_label.pack(side="left", padx=(0, 8))

        self.sort_var = ctk.StringVar(value="Name (A-Z)")

        sort_menu = ctk.CTkOptionMenu(
            right_group,
            values=[
                "Name (A-Z)",
                "Name (Z-A)",
                "Last annotated",
            ],
            variable=self.sort_var,
            command=self.sort_books,
            fg_color="#3a3659",
            button_color="#765996",
            button_hover_color="#654c80"
        )
        sort_menu.pack(side="left")

        # 👇 Select All (always visible)
        self.select_all_var = ctk.BooleanVar()

        select_all = ctk.CTkCheckBox(
            main_frame,
            text="Select All",
            variable=self.select_all_var,
            command=self.toggle_all,
            font=(DEFAULT_FONT, 14),
            corner_radius=4,
            border_color="#654c80",
            fg_color="#fdd886",
            hover_color="#e5c46a",
            checkmark_color="#2b2b2b",
            border_width=1
        )

        select_all.grid(row=3, column=0, sticky="w", padx=40, pady=(0,0))

        # SEARCH BAR

        search_frame = ctk.CTkFrame(main_frame, fg_color="#1d1d42")
        search_frame.grid(row=2, column=0, sticky="ew", padx=40, pady=(10,10))

        search_label = ctk.CTkLabel(
            search_frame,
            text="Search book",
            font=(DEFAULT_FONT, 13)
        )
        search_label.pack(side="left", padx=(0,10))

        self.search_var = ctk.StringVar()

        search_entry = ctk.CTkEntry(
            search_frame,
            textvariable=self.search_var,
            placeholder_text="Type to filter books...",
            fg_color="#3a3659",        # background color of the entry
            text_color="#ffffff",       # text color
            placeholder_text_color="#aaaaaa",  # placeholder color
            border_color="#1d1d42",     # border color if you want
            corner_radius=6
        )

        search_entry.pack(side="left", fill="x", expand=True)

        self.search_var.trace_add("write", self.filter_books)

        books_frame = ctk.CTkScrollableFrame(
            main_frame,
            fg_color="#141432",
            corner_radius=6
        )

        books_frame.grid(row=4, column=0, sticky="nsew", padx=20, pady=6)
        books_frame.grid_columnconfigure(0, weight=1)

        # smoother scrolling
        books_frame._parent_canvas.configure(yscrollincrement=30)

        self.scroll = books_frame

        # Refresh books
        self.refresh_book_list()


        # SCREEN TYPE SELECTION + OPEN ANOTHER DATABASE
        screen_frame = ctk.CTkFrame(main_frame, fg_color="#1d1d42")
        screen_frame.grid(row=5, column=0, sticky="ew", padx=40, pady=(5,5))

        screen_frame.columnconfigure(0, weight=0)  # label
        screen_frame.columnconfigure(1, weight=0)  # dropdown
        screen_frame.columnconfigure(2, weight=1)  # spacer
        screen_frame.columnconfigure(3, weight=0)  # button

        screen_label = ctk.CTkLabel(
            screen_frame,
            text="Screen Type",
            font=(DEFAULT_FONT, 14)
        )
        screen_label.grid(row=0, column=0, sticky="w", padx=(10,5), pady=(0,2))

        self.screen_var = ctk.StringVar(value=self.saved_screen_type)

        screen_menu = ctk.CTkOptionMenu(
            screen_frame,
            values=["BW", "Color"],
            variable=self.screen_var,
            command=lambda _: self.save_settings(),
            fg_color="#3a3659",
            button_color="#765996",
            button_hover_color="#654c80"
        )
        screen_menu.grid(row=0, column=1, sticky="w", pady=(0,2))

        open_db_btn = self.styled_button(
            screen_frame,
            "Open Another Database",
            command=self.upload_database,
            width=180,
            fg_color="#3a3659",
            hover_color="#343142"
        )
        
        open_db_btn.grid(row=0, column=3, sticky="e", padx=(5,0))

        info_btn_db = ctk.CTkButton(
            screen_frame,
            text="",
            image=self.info_icon,
            width=18,
            height=18,
            fg_color="#1d1d42",
            hover_color="#343142"
        )
        info_btn_db.grid(row=0, column=4, sticky="w", padx=(5,10), pady=(2,0))

        ToolTip(
            info_btn_db,
            """Select another KoboReader.sqlite file if you want to switch databases.

        Important:
        - Always select a copy saved on your computer.
        - Do not open the file directly from your Kobo device."""
        )

        # ------------------------------------------------
        # OUTPUT FOLDER SECTION
        # ------------------------------------------------

        folder_section = ctk.CTkFrame(main_frame, fg_color="#1d1d42")
        folder_section.grid(row=6, column=0, sticky="ew", padx=40, pady=10)

        folder_label = ctk.CTkLabel(
            folder_section,
            text="Save to",
            font=(DEFAULT_FONT, 14)
        )
        folder_label.pack(anchor="w", padx=10, pady=(0, 5))

        # 👇 this is the styled path container
        path_frame = ctk.CTkFrame(
            folder_section,
            fg_color="#141432",
            corner_radius=6
        )
        path_frame.pack(fill="x", padx=10, pady=(5, 10))

        self.folder_label = ctk.CTkLabel(
            path_frame,
            text=str(self.output_dir),
            anchor="w"
        )
        self.folder_label.pack(side="left", padx=10, pady=8, expand=True)

        browse_btn = self.styled_button(
            path_frame,
            "Browse",
            command=self.select_folder,
            width=90
        )
        browse_btn.pack(side="right", padx=10, pady=6)

        # ------------------------------------------------
        # PROGRESS BAR
        # ------------------------------------------------

        self.progress = ctk.CTkProgressBar(
            main_frame,
            height=12,
            corner_radius=4,
            progress_color="#765996",   # filled part
            fg_color="#3a3659"          # background bar
        )
        self.progress.grid(row=7, column=0, sticky="ew", padx=40, pady=(10,5))
        self.progress.set(0)

        # ------------------------------------------------
        # ACTION BUTTONS
        # ------------------------------------------------

        button_row = ctk.CTkFrame(main_frame, fg_color="#1d1d42")
        button_row.grid(row=8, column=0, pady=20)

        extract_btn = self.styled_button(
            button_row,
            "Export Highlights",
            command=self.start_extract,
            accent=True  # 👈 accent button
        )
        extract_btn.pack(side="left", padx=10)

        cancel_btn = self.styled_button(
            button_row,
            "Exit",
            command=self.destroy,
            width=120
        )
        cancel_btn.pack(side="left", padx=10)

    # -------------------------
    # ACTIONS
    # -------------------------

    def refresh_book_list(self):

        # Clear existing book checkboxes
        for widget in self.scroll.winfo_children():
            widget.destroy()

        self.checkboxes = []

        for volume_id, title, author, last_highlight in self.books:

            var = ctk.BooleanVar()

            # Lookup highlight count
            count = self.highlight_counts.get(volume_id, 0)

            cb = ctk.CTkCheckBox(
                self.scroll,
                text=f"{title} ({count} highlight{'s' if count != 1 else ''})",
                variable=var,
                font=(DEFAULT_FONT, 14),
                width=14,
                height=14,
                corner_radius=4,

                # 🎨 checkbox styling
                border_color="#654c80",
                fg_color="#fdd886",          # checked box color
                hover_color="#e5c46a",
                checkmark_color="#2b2b2b",
                border_width=1
            )
            
            cb.pack(anchor="w", padx=10, pady=5)

            self.checkboxes.append((var, volume_id, title, author))

    def toggle_all(self):

        value = self.select_all_var.get()

        for var, *_ in self.checkboxes:
            var.set(value)

    def sort_books(self, *_):

        if self.sort_var.get() == "Name (A-Z)":
            self.books.sort(key=lambda x: x[1].lower())

        elif self.sort_var.get() == "Name (Z-A)":
            self.books.sort(key=lambda x: x[1].lower(), reverse=True)

        elif self.sort_var.get() == "Last annotated":
            # newest highlight first
            self.books.sort(
                key=lambda x: x[3] or "",
                reverse=True
            )

        self.refresh_book_list()

    def filter_books(self, *_):

        query = self.search_var.get().lower()

        if not query:
            self.books = list(self.all_books)
            self.sort_books()   # respects current sort selection
        else:
            self.books = [
                book for book in self.all_books
                if query in book[1].lower() or query in (book[2] or "").lower()
            ]

        self.refresh_book_list()

    def select_folder(self):

        folder = filedialog.askdirectory()

        if folder:
            self.output_dir = Path(folder)
            self.folder_label.configure(text=folder)
            self.save_settings()  # 👈 always save automatically

    def start_extract(self):

        threading.Thread(target=self.extract, daemon=True).start()

    def extract(self):

        try:

            # create connection INSIDE thread
            conn = sqlite3.connect(self.db_copy_path)

            selected = [
                (volume_id, title, author)
                for var, volume_id, title, author in self.checkboxes
                if var.get()
            ]

            total = len(selected)

            if total == 0:
                messagebox.showwarning("No selection", "Select at least one book.")
                return

            self.output_dir.mkdir(exist_ok=True)

            core.OUTPUT_DIR = self.output_dir

            for i, (volume_id, title, author) in enumerate(selected):

                screen_type = self.screen_var.get()  # BW or Color

                highlights = get_highlights_universal(
                    conn,
                    volume_id,
                    book_title=title,
                    screen_type=screen_type,
                    filesize_col=self.filesize_col
                )

                write_markdown(
                    title,
                    author,
                    highlights,
                    screen_type=screen_type
                )

                progress = (i + 1) / total
                self.after(0, self.progress.set, progress)

            conn.close()

            messagebox.showinfo("Done", "Highlights exported successfully!")

        except Exception as e:
            messagebox.showerror("Error", str(e))

    # -------------------------

    def clear(self):
        for widget in self.main_container.winfo_children():
            widget.destroy()
            
    # ------------------------------------------------
    # 🎨 GLOBAL STYLE SYSTEM (UI V2)
    # ------------------------------------------------

    def styled_button(
        self,
        parent,
        text,
        command=None,
        width=None,
        accent=False,
        fg_color=None,
        hover_color=None,
    ):

        kwargs = {}

        if width is not None:
            kwargs["width"] = width

        return ctk.CTkButton(
            parent,
            text=text,
            command=command,
            fg_color=fg_color if fg_color else (self.ACCENT_BG if accent else self.BUTTON_BG),
            hover_color=hover_color if hover_color else (self.ACCENT_HOVER if accent else self.BUTTON_HOVER),
            text_color=self.ACCENT_TEXT if accent else self.BUTTON_TEXT,
            corner_radius=4,
            **kwargs
        )


    def styled_frame(self, parent):
        return ctk.CTkFrame(
            parent,
            fg_color="#1d1d42",    # checked "box background" color
            corner_radius=0
        )


if __name__ == "__main__":
    app = KoboApp()
    app.mainloop()