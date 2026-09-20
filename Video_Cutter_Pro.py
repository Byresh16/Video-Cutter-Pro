import os
import re
import shutil
import subprocess
import sys
import threading
import tkinter as tk

from tkinter import filedialog, messagebox, ttk


# ============================================================
# CONFIGURATION
# ============================================================

# ------------------------------------------------------------
# Application folder / portable paths
# ------------------------------------------------------------
# When running the .py file, use the folder containing this file.
# When running the packaged .exe, use the folder containing the .exe.
# This allows Video Cutter Pro to work without Python installed.
if getattr(sys, "frozen", False):
    APP_DIR = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_DIR = os.path.dirname(os.path.abspath(__file__))


# ------------------------------------------------------------
# FFmpeg / 7-Zip paths
# ------------------------------------------------------------
FFMPEG = os.path.join(APP_DIR, "ffmpeg.exe")
SEVEN_ZIP = os.path.join(APP_DIR, "7z.exe")


# ------------------------------------------------------------
# Performance settings
# ------------------------------------------------------------
# 0 = let FFmpeg automatically use available CPU threads.
# This is normally faster than limiting the encoder to 2 threads.
FFMPEG_THREADS = "0"

# Fast Cut uses stream copy first. This can be dramatically faster
# because the video is not re-encoded. If the source/container/codecs
# cannot be copied safely to MP4, the app automatically falls back to
# accurate H.264/AAC re-encoding.
FAST_CUT_DEFAULT = True

# Used only by the accurate re-encode fallback.
FFMPEG_PRESET = "superfast"
FFMPEG_CRF = "23"


# ------------------------------------------------------------
# Archive CPU limit
# ------------------------------------------------------------
ARCHIVE_THREADS = "0"


# ============================================================
# WINDOWS DPI
# ============================================================

try:
    from ctypes import windll

    windll.shcore.SetProcessDpiAwareness(1)

except Exception:
    pass


# ============================================================
# APPLICATION
# ============================================================

class VideoCutterPro:

    def __init__(self, root):

        self.root = root

        self.root.title("Video Cutter Pro")

        self.root.geometry("1000x900")

        self.root.minsize(900, 760)

        self.root.resizable(True, True)

        # ----------------------------------------------------
        # State
        # ----------------------------------------------------

        self.video_path = ""

        self.output_dir = ""

        self.output_video_path = ""

        self.video_duration = 0.0

        self.ffmpeg_process = None

        self.archive_process = None

        self.export_running = False

        self.stop_requested = False
        self.fast_cut_enabled = tk.BooleanVar(value=FAST_CUT_DEFAULT)

        # ----------------------------------------------------
        # Build UI
        # ----------------------------------------------------

        self.create_widgets()

        # ----------------------------------------------------
        # Window close
        # ----------------------------------------------------

        self.root.protocol(
            "WM_DELETE_WINDOW",
            self.close_application
        )

        # ----------------------------------------------------
        # Initial checks
        # ----------------------------------------------------

        self.root.after(
            500,
            self.check_dependencies
        )


    # ========================================================
    # UI CREATION
    # ========================================================

    def create_widgets(self):

        # ----------------------------------------------------
        # Main container
        # ----------------------------------------------------

        main = ttk.Frame(
            self.root,
            padding=15
        )

        main.pack(
            fill="both",
            expand=True
        )


        # ====================================================
        # TITLE
        # ====================================================

        title = ttk.Label(
            main,
            text="Video Cutter Pro",
            font=("Arial", 22, "bold")
        )

        title.pack(
            anchor="w"
        )


        subtitle = ttk.Label(
            main,
            text="Simple video cutter with issue-based trimming and optional split archive."
        )

        subtitle.pack(
            anchor="w",
            pady=(2, 12)
        )


        # ====================================================
        # 1. INPUT VIDEO
        # ====================================================

        input_frame = ttk.LabelFrame(
            main,
            text="1. Input Video",
            padding=10
        )

        input_frame.pack(
            fill="x",
            pady=(0, 10)
        )


        input_row = ttk.Frame(
            input_frame
        )

        input_row.pack(
            fill="x"
        )


        self.video_entry = ttk.Entry(
            input_row
        )

        self.video_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10)
        )


        self.browse_video_btn = ttk.Button(
            input_row,
            text="Browse",
            command=self.browse_video
        )

        self.browse_video_btn.pack(
            side="right"
        )


        self.video_info_label = ttk.Label(
            input_frame,
            text="No video selected"
        )

        self.video_info_label.pack(
            anchor="w",
            pady=(8, 0)
        )


        # ====================================================
        # 2. CUTTING SETTINGS
        # ====================================================

        cutting_frame = ttk.LabelFrame(
            main,
            text="2. Cutting Settings",
            padding=10
        )

        cutting_frame.pack(
            fill="x",
            pady=(0, 10)
        )

        # ----------------------------------------------------
        # Fast export option
        # ----------------------------------------------------

        self.fast_cut_check = ttk.Checkbutton(
            cutting_frame,
            text="Fast Cut",
            variable=self.fast_cut_enabled
        )

        self.fast_cut_check.pack(
            anchor="w",
            pady=(0, 8)
        )

        # ----------------------------------------------------
        # Cutter mode
        # ----------------------------------------------------

        mode_row = ttk.Frame(
            cutting_frame
        )

        mode_row.pack(
            fill="x",
            pady=(0, 10)
        )


        self.cutter_mode = tk.StringVar(
            value="issue"
        )


        self.issue_radio = ttk.Radiobutton(
            mode_row,
            text="Issue Cutter",
            variable=self.cutter_mode,
            value="issue",
            command=self.update_cutter_mode
        )

        self.issue_radio.pack(
            side="left",
            padx=(0, 30)
        )


        self.normal_radio = ttk.Radiobutton(
            mode_row,
            text="Normal Cutter",
            variable=self.cutter_mode,
            value="normal",
            command=self.update_cutter_mode
        )

        self.normal_radio.pack(
            side="left"
        )


        # ----------------------------------------------------
        # Issue Cutter fields
        # ----------------------------------------------------

        self.issue_frame = ttk.Frame(
            cutting_frame
        )

        self.issue_frame.pack(
            fill="x"
        )


        ttk.Label(
            self.issue_frame,
            text="Issue timestamp:"
        ).grid(
            row=0,
            column=0,
            padx=(0, 8),
            pady=5,
            sticky="w"
        )


        self.issue_entry = ttk.Entry(
            self.issue_frame,
            width=15
        )

        self.issue_entry.insert(
            0,
            "00:05:00"
        )

        self.issue_entry.grid(
            row=0,
            column=1,
            padx=(0, 25),
            pady=5
        )


        ttk.Label(
            self.issue_frame,
            text="Cut duration:"
        ).grid(
            row=0,
            column=2,
            padx=(0, 8),
            pady=5,
            sticky="w"
        )


        self.cut_duration_entry = ttk.Entry(
            self.issue_frame,
            width=15
        )

        self.cut_duration_entry.insert(
            0,
            "00:05:00"
        )

        self.cut_duration_entry.grid(
            row=0,
            column=3,
            padx=(0, 15),
            pady=5
        )


        # ----------------------------------------------------
        # Normal Cutter fields
        # ----------------------------------------------------

        self.normal_frame = ttk.Frame(
            cutting_frame
        )


        ttk.Label(
            self.normal_frame,
            text="Start time:"
        ).grid(
            row=0,
            column=0,
            padx=(0, 8),
            pady=5
        )


        self.normal_start_entry = ttk.Entry(
            self.normal_frame,
            width=15
        )

        self.normal_start_entry.insert(
            0,
            "00:00:00"
        )

        self.normal_start_entry.grid(
            row=0,
            column=1,
            padx=(0, 25),
            pady=5
        )


        ttk.Label(
            self.normal_frame,
            text="End time:"
        ).grid(
            row=0,
            column=2,
            padx=(0, 8),
            pady=5
        )


        self.normal_end_entry = ttk.Entry(
            self.normal_frame,
            width=15
        )

        self.normal_end_entry.insert(
            0,
            "00:01:00"
        )

        self.normal_end_entry.grid(
            row=0,
            column=3,
            pady=5
        )


        # ----------------------------------------------------
        # Calculated values
        # ----------------------------------------------------

        calculation_row = ttk.Frame(
            cutting_frame
        )

        calculation_row.pack(
            fill="x",
            pady=(10, 0)
        )


        self.calculated_label = ttk.Label(
            calculation_row,
            text="Calculated cut: --"
        )

        self.calculated_label.pack(
            side="left"
        )


        self.calculate_btn = ttk.Button(
            calculation_row,
            text="Calculate Cut",
            command=self.calculate_cut
        )

        self.calculate_btn.pack(
            side="right"
        )


        # ====================================================
        # 3. ARCHIVE / SPLIT SETTINGS
        # ====================================================

        archive_frame = ttk.LabelFrame(
            main,
            text="3. Archive / Split Settings",
            padding=10
        )

        archive_frame.pack(
            fill="x",
            pady=(0, 10)
        )


        # ----------------------------------------------------
        # Archive checkbox
        # ----------------------------------------------------

        self.archive_enabled = tk.BooleanVar(
            value=True
        )


        self.archive_check = ttk.Checkbutton(
            archive_frame,
            text="Create archive after trimming",
            variable=self.archive_enabled,
            command=self.update_archive_controls
        )

        self.archive_check.pack(
            anchor="w",
            pady=(0, 8)
        )


        # ----------------------------------------------------
        # Archive settings row
        # ----------------------------------------------------

        archive_settings = ttk.Frame(
            archive_frame
        )

        archive_settings.pack(
            fill="x"
        )


        # Format

        ttk.Label(
            archive_settings,
            text="Format:"
        ).grid(
            row=0,
            column=0,
            padx=(0, 5),
            sticky="w"
        )


        self.archive_format = ttk.Combobox(
            archive_settings,
            values=[
                "7z",
                "zip"
            ],
            width=12,
            state="readonly"
        )

        self.archive_format.set(
            "7z"
        )

        self.archive_format.grid(
            row=0,
            column=1,
            padx=(0, 30)
        )


        # Split size

        ttk.Label(
            archive_settings,
            text="Split size:"
        ).grid(
            row=0,
            column=2,
            padx=(0, 5),
            sticky="w"
        )


        self.split_size = ttk.Combobox(
            archive_settings,
            values=[
                "10 MB",
                "14 MB",
                "50 MB",
                "100 MB",
                "500 MB",
                "1 GB",
                "2 GB",
                "Custom"
            ],
            width=12,
            state="readonly"
        )

        self.split_size.set(
            "14 MB"
        )

        self.split_size.grid(
            row=0,
            column=3,
            padx=(0, 30)
        )


        self.split_size.bind(
            "<<ComboboxSelected>>",
            self.update_custom_size
        )


        # Custom MB

        ttk.Label(
            archive_settings,
            text="Custom MB:"
        ).grid(
            row=0,
            column=4,
            padx=(0, 5)
        )


        self.custom_mb_entry = ttk.Entry(
            archive_settings,
            width=10
        )

        self.custom_mb_entry.insert(
            0,
            "14"
        )

        self.custom_mb_entry.grid(
            row=0,
            column=5
        )


        # Description

        self.archive_description = ttk.Label(
            archive_frame,
            text="Each archive part is approximately the selected size."
        )

        self.archive_description.pack(
            anchor="w",
            pady=(8, 0)
        )


        # ====================================================
        # 4. OUTPUT
        # ====================================================

        output_frame = ttk.LabelFrame(
            main,
            text="4. Output",
            padding=10
        )

        output_frame.pack(
            fill="x",
            pady=(0, 10)
        )


        # ----------------------------------------------------
        # Output folder
        # ----------------------------------------------------

        folder_row = ttk.Frame(
            output_frame
        )

        folder_row.pack(
            fill="x",
            pady=(0, 5)
        )


        ttk.Label(
            folder_row,
            text="Output folder:"
        ).pack(
            side="left",
            padx=(0, 10)
        )


        self.output_entry = ttk.Entry(
            folder_row
        )

        self.output_entry.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(0, 10)
        )


        self.browse_output_btn = ttk.Button(
            folder_row,
            text="Browse",
            command=self.browse_output
        )

        self.browse_output_btn.pack(
            side="right"
        )


        # ----------------------------------------------------
        # Output filename
        # ----------------------------------------------------

        name_row = ttk.Frame(
            output_frame
        )

        name_row.pack(
            fill="x"
        )


        ttk.Label(
            name_row,
            text="Output video name:"
        ).pack(
            side="left",
            padx=(0, 10)
        )


        self.output_name_entry = ttk.Entry(
            name_row
        )

        self.output_name_entry.pack(
            side="left",
            fill="x",
            expand=True
        )


        self.example_label = ttk.Label(
            output_frame,
            text="Example: Issue_Video_02m_30s"
        )

        self.example_label.pack(
            anchor="w",
            padx=(115, 0),
            pady=(5, 0)
        )


        # ====================================================
        # EXPORT CONTROLS
        # ====================================================

        control_frame = ttk.Frame(
            main
        )

        control_frame.pack(
            fill="x",
            pady=(0, 10)
        )


        self.start_export_btn = ttk.Button(
            control_frame,
            text="START EXPORT",
            command=self.start_export
        )

        self.start_export_btn.pack(
            side="right",
            padx=(5, 0)
        )


        self.stop_btn = ttk.Button(
            control_frame,
            text="STOP",
            command=self.stop_export,
            state=tk.DISABLED
        )

        self.stop_btn.pack(
            side="right"
        )


        # ====================================================
        # 5. PROGRESS
        # ====================================================

        progress_frame = ttk.LabelFrame(
            main,
            text="5. Progress",
            padding=10
        )

        progress_frame.pack(
            fill="both",
            expand=True
        )


        self.status_label = ttk.Label(
            progress_frame,
            text="Ready."
        )

        self.status_label.pack(
            anchor="w",
            pady=(0, 8)
        )


        # ----------------------------------------------------
        # Progress bar
        # ----------------------------------------------------

        self.progress = ttk.Progressbar(
            progress_frame,
            orient="horizontal",
            mode="determinate"
        )

        self.progress.pack(
            fill="x",
            pady=(0, 8)
        )


        # ----------------------------------------------------
        # Percentage
        # ----------------------------------------------------

        self.progress_percent = ttk.Label(
            progress_frame,
            text="0%"
        )

        self.progress_percent.pack(
            anchor="w"
        )


        # ----------------------------------------------------
        # Log
        # ----------------------------------------------------

        self.log_text = tk.Text(
            progress_frame,
            height=6,
            state=tk.DISABLED
        )

        self.log_text.pack(
            fill="both",
            expand=True,
            pady=(8, 0)
        )


        # ----------------------------------------------------
        # Initial mode
        # ----------------------------------------------------

        self.update_cutter_mode()

        self.update_archive_controls()


    # ========================================================
    # DEPENDENCY CHECK
    # ========================================================

    def check_dependencies(self):

        if not os.path.isfile(FFMPEG):

            self.log(
                "WARNING: FFmpeg was not found."
            )

            self.log(
                f"Expected FFmpeg:\n{FFMPEG}"
            )

        else:

            self.log(
                "FFmpeg detected."
            )


        if os.path.isfile(SEVEN_ZIP):

            self.log(
                "7-Zip detected."
            )

        else:

            seven_zip_path = shutil.which(
                "7z"
            )


            if seven_zip_path:

                self.log(
                    f"7-Zip detected in PATH: {seven_zip_path}"
                )

            else:

                self.log(
                    "7-Zip not detected. Archive creation "
                    "will require 7-Zip."
                )


    # ========================================================
    # LOG
    # ========================================================

    def log(self, message):

        def add_log():

            self.log_text.config(
                state=tk.NORMAL
            )


            self.log_text.insert(
                tk.END,
                str(message) + "\n"
            )


            self.log_text.see(
                tk.END
            )


            self.log_text.config(
                state=tk.DISABLED
            )


        self.root.after(
            0,
            add_log
        )


    # ========================================================
    # BROWSE VIDEO
    # ========================================================

    def browse_video(self):

        if self.export_running:
            return


        file_types = [
            (
                "Video Files",
                "*.mp4 *.mkv *.avi *.mov *.wmv *.flv *.webm"
            ),
            (
                "All Files",
                "*.*"
            )
        ]


        selected = filedialog.askopenfilename(
            title="Select Video",
            filetypes=file_types
        )


        if not selected:
            return


        self.video_path = selected


        self.video_entry.delete(
            0,
            tk.END
        )


        self.video_entry.insert(
            0,
            selected
        )


        filename = os.path.basename(
            selected
        )


        self.video_info_label.config(
            text=f"Selected: {filename}"
        )


        # ----------------------------------------------------
        # Default output directory
        # ----------------------------------------------------

        if not self.output_dir:

            default_output = os.path.dirname(
                selected
            )

            self.output_dir = default_output


            self.output_entry.delete(
                0,
                tk.END
            )


            self.output_entry.insert(
                0,
                default_output
            )


        # ----------------------------------------------------
        # Default output filename
        # ----------------------------------------------------

        base_name = os.path.splitext(
            filename
        )[0]


        self.output_name_entry.delete(
            0,
            tk.END
        )


        self.output_name_entry.insert(
            0,
             "Issue_Video_02m_30s_"
        )


        # ----------------------------------------------------
        # Get duration
        # ----------------------------------------------------

        self.video_info_label.config(
            text=f"Selected: {filename} | Reading duration..."
        )


        threading.Thread(
            target=self.get_video_duration,
            daemon=True
        ).start()


    # ========================================================
    # GET VIDEO DURATION
    # ========================================================

    def get_video_duration(self):

        try:

            command = [
                FFMPEG,
                "-hide_banner",
                "-i",
                self.video_path
            ]


            creationflags = 0


            if os.name == "nt":

                creationflags = (
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.BELOW_NORMAL_PRIORITY_CLASS
                )


            result = subprocess.run(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                creationflags=creationflags
            )


            output = result.stderr


            match = re.search(
                r"Duration:\s*"
                r"(\d+):(\d+):(\d+)"
                r"\.?(\d*)",
                output
            )


            if not match:

                self.root.after(
                    0,
                    lambda: self.video_info_label.config(
                        text="Unable to read video duration."
                    )
                )

                return


            hours = int(
                match.group(1)
            )

            minutes = int(
                match.group(2)
            )

            seconds = int(
                match.group(3)
            )


            fraction = match.group(4)


            fractional_seconds = 0.0


            if fraction:

                fractional_seconds = float(
                    "0." + fraction
                )


            self.video_duration = (
                hours * 3600
                + minutes * 60
                + seconds
                + fractional_seconds
            )


            duration_text = self.seconds_to_hms(
                self.video_duration
            )


            self.root.after(
                0,
                lambda: self.video_info_label.config(
                    text=(
                        f"Selected: "
                        f"{os.path.basename(self.video_path)}"
                        f" | Duration: {duration_text}"
                    )
                )
            )


        except Exception as error:

            self.log(
                f"Duration error: {error}"
            )


    # ========================================================
    # BROWSE OUTPUT
    # ========================================================

    def browse_output(self):

        if self.export_running:
            return


        selected = filedialog.askdirectory(
            title="Select Output Folder"
        )


        if not selected:
            return


        self.output_dir = selected


        self.output_entry.delete(
            0,
            tk.END
        )


        self.output_entry.insert(
            0,
            selected
        )


    # ========================================================
    # CUTTER MODE
    # ========================================================

    def update_cutter_mode(self):

        if self.cutter_mode.get() == "issue":

            self.normal_frame.pack_forget()

            self.issue_frame.pack(
                fill="x"
            )

        else:

            self.issue_frame.pack_forget()

            self.normal_frame.pack(
                fill="x"
            )


    # ========================================================
    # ARCHIVE CONTROLS
    # ========================================================

    def update_archive_controls(self):

        enabled = self.archive_enabled.get()


        state = (
            "readonly"
            if enabled
            else "disabled"
        )


        self.archive_format.config(
            state=state
        )


        self.split_size.config(
            state=state
        )


        self.custom_mb_entry.config(
            state=(
                "normal"
                if enabled
                else "disabled"
            )
        )


    # ========================================================
    # CUSTOM SIZE
    # ========================================================

    def update_custom_size(self, event=None):

        if self.split_size.get() == "Custom":

            self.custom_mb_entry.focus()


    # ========================================================
    # TIME PARSER
    # ========================================================

    def parse_time(self, value):

        value = value.strip()


        if not value:

            raise ValueError(
                "Time cannot be empty."
            )


        # ----------------------------------------------------
        # HH:MM:SS
        # ----------------------------------------------------

        if ":" in value:

            parts = value.split(":")


            if len(parts) == 3:

                hours = float(parts[0])

                minutes = float(parts[1])

                seconds = float(parts[2])


                if (
                    hours < 0
                    or minutes < 0
                    or seconds < 0
                ):

                    raise ValueError(
                        "Time cannot be negative."
                    )


                if minutes >= 60:

                    raise ValueError(
                        "Minutes must be below 60."
                    )


                if seconds >= 60:

                    raise ValueError(
                        "Seconds must be below 60."
                    )


                return (
                    hours * 3600
                    + minutes * 60
                    + seconds
                )


            # ------------------------------------------------
            # MM:SS
            # ------------------------------------------------

            elif len(parts) == 2:

                minutes = float(parts[0])

                seconds = float(parts[1])


                if minutes < 0 or seconds < 0:

                    raise ValueError(
                        "Time cannot be negative."
                    )


                if seconds >= 60:

                    raise ValueError(
                        "Seconds must be below 60."
                    )


                return (
                    minutes * 60
                    + seconds
                )


            else:

                raise ValueError(
                    "Invalid time format."
                )


        # ----------------------------------------------------
        # Seconds
        # ----------------------------------------------------

        return float(value)


    # ========================================================
    # FORMAT TIME
    # ========================================================

    def seconds_to_hms(self, seconds):

        seconds = max(
            0,
            float(seconds)
        )


        hours = int(
            seconds // 3600
        )


        minutes = int(
            (seconds % 3600) // 60
        )


        secs = seconds % 60


        return (
            f"{hours:02d}:"
            f"{minutes:02d}:"
            f"{secs:05.2f}"
        )


    # ========================================================
    # CALCULATE CUT
    # ========================================================

    def calculate_cut(self):

        try:

            if self.cutter_mode.get() == "issue":

                issue = self.parse_time(
                    self.issue_entry.get()
                )


                duration = self.parse_time(
                    self.cut_duration_entry.get()
                )


                if duration <= 0:

                    raise ValueError(
                        "Cut duration must be greater than zero."
                    )


                # ------------------------------------------------
                # Issue Cutter formula
                # ------------------------------------------------

                half_duration = duration / 2


                start = issue - half_duration

                end = issue + half_duration


                # Don't allow negative start

                if start < 0:

                    start = 0

                    end = min(
                        duration,
                        self.video_duration
                    )


                # Don't exceed video

                if self.video_duration > 0:

                    if end > self.video_duration:

                        end = self.video_duration


                calculated_text = (
                    "Calculated cut: "
                    f"{self.seconds_to_hms(start)}"
                    "  →  "
                    f"{self.seconds_to_hms(end)}"
                    "  "
                    f"({self.seconds_to_hms(end - start)})"
                )


                self.calculated_label.config(
                    text=calculated_text
                )


                return start, end


            else:

                start = self.parse_time(
                    self.normal_start_entry.get()
                )


                end = self.parse_time(
                    self.normal_end_entry.get()
                )


                if end <= start:

                    raise ValueError(
                        "End time must be greater than start time."
                    )


                if (
                    self.video_duration > 0
                    and start >= self.video_duration
                ):

                    raise ValueError(
                        "Start time is beyond the video duration."
                    )


                if (
                    self.video_duration > 0
                    and end > self.video_duration
                ):

                    end = self.video_duration


                calculated_text = (
                    "Calculated cut: "
                    f"{self.seconds_to_hms(start)}"
                    "  →  "
                    f"{self.seconds_to_hms(end)}"
                    "  "
                    f"({self.seconds_to_hms(end - start)})"
                )


                self.calculated_label.config(
                    text=calculated_text
                )


                return start, end


        except ValueError as error:

            messagebox.showerror(
                "Invalid Cut Settings",
                str(error)
            )

            return None


    # ========================================================
    # GET ARCHIVE SIZE
    # ========================================================

    def get_archive_size(self):

        selected = self.split_size.get()


        if selected == "Custom":

            try:

                mb = float(
                    self.custom_mb_entry.get()
                )


            except ValueError:

                raise ValueError(
                    "Enter a valid custom archive size."
                )


            if mb <= 0:

                raise ValueError(
                    "Custom archive size must be greater than 0."
                )


            return f"{mb:g}m"


        # ----------------------------------------------------
        # Presets
        # ----------------------------------------------------

        if selected.endswith(" MB"):

            number = selected.replace(
                " MB",
                ""
            )

            return f"{number}m"


        if selected.endswith(" GB"):

            number = selected.replace(
                " GB",
                ""
            )

            return f"{number}g"


        raise ValueError(
            "Invalid archive split size."
        )


    # ========================================================
    # FIND 7-ZIP
    # ========================================================

    def find_7zip(self):

        if os.path.isfile(SEVEN_ZIP):

            return SEVEN_ZIP


        path = shutil.which(
            "7z"
        )


        if path:

            return path


        common_paths = [
            r"C:\Program Files\7-Zip\7z.exe",
            r"C:\Program Files (x86)\7-Zip\7z.exe",
            os.path.expandvars(
                r"%LOCALAPPDATA%\Programs\7-Zip\7z.exe"
            )
        ]


        for path in common_paths:

            if os.path.isfile(path):

                return path


        return None


    # ========================================================
    # START EXPORT
    # ========================================================

    def start_export(self):

        if self.export_running:

            return


        # ----------------------------------------------------
        # Validate FFmpeg
        # ----------------------------------------------------

        if not os.path.isfile(FFMPEG):

            messagebox.showerror(
                "FFmpeg Not Found",
                "FFmpeg could not be found.\n\n"
                f"Expected:\n{FFMPEG}"
            )

            return


        # ----------------------------------------------------
        # Validate video
        # ----------------------------------------------------

        if not self.video_path:

            messagebox.showerror(
                "No Video",
                "Please select a video."
            )

            return


        if not os.path.isfile(self.video_path):

            messagebox.showerror(
                "Video Not Found",
                "The selected video does not exist."
            )

            return


        # ----------------------------------------------------
        # Calculate cut
        # ----------------------------------------------------

        result = self.calculate_cut()


        if not result:

            return


        start_sec, end_sec = result


        if end_sec <= start_sec:

            messagebox.showerror(
                "Invalid Cut",
                "End time must be greater than start time."
            )

            return


        # ----------------------------------------------------
        # Output folder
        # ----------------------------------------------------

        output_dir = self.output_entry.get().strip()


        if not output_dir:

            output_dir = os.path.dirname(
                self.video_path
            )


        try:

            os.makedirs(
                output_dir,
                exist_ok=True
            )

        except Exception as error:

            messagebox.showerror(
                "Output Folder Error",
                str(error)
            )

            return


        # ----------------------------------------------------
        # Output name
        # ----------------------------------------------------

        output_name = (
            self.output_name_entry
            .get()
            .strip()
        )


        if not output_name:

            output_name = "trimmed_video"


        # ====================================================
        # IMPORTANT FILENAME FIX
        # ====================================================
        #
        # DO NOT use:
        #
        # os.path.splitext(output_name)[0]
        #
        # because a filename can contain multiple dots.
        #
        # Example:
        #
        # Issue_Video_02m_15s_IRI.29.01.12_A11
        #
        # must remain:
        #
        # Issue_Video_02m_15s_IRI.29.01.12_A11.mp4
        #
        # We only remove .mp4 if the user explicitly typed it.
        # ====================================================

        if output_name.lower().endswith(".mp4"):

            output_name = output_name[:-4]


        # ----------------------------------------------------
        # Create final output path
        # ----------------------------------------------------

        output_path = os.path.join(
            output_dir,
            output_name + ".mp4"
        )


        # ----------------------------------------------------
        # Don't overwrite existing output
        # ----------------------------------------------------

        output_path = self.get_unique_path(
            output_path
        )


        self.output_video_path = output_path


        # ----------------------------------------------------
        # Archive validation
        # ----------------------------------------------------

        if self.archive_enabled.get():

            seven_zip = self.find_7zip()


            if not seven_zip:

                messagebox.showerror(
                    "7-Zip Not Found",
                    "Archive creation requires 7-Zip.\n\n"
                    "Install 7-Zip or disable:\n"
                    "\"Create archive after trimming\""
                )

                return


            try:

                archive_size = self.get_archive_size()

            except ValueError as error:

                messagebox.showerror(
                    "Archive Settings",
                    str(error)
                )

                return


        else:

            archive_size = None


        # ----------------------------------------------------
        # Lock UI
        # ----------------------------------------------------

        self.export_running = True

        self.stop_requested = False


        self.start_export_btn.config(
            state=tk.DISABLED
        )


        self.stop_btn.config(
            state=tk.NORMAL
        )


        self.set_input_controls(
            state=tk.DISABLED
        )


        self.progress["value"] = 0


        self.progress_percent.config(
            text="0%"
        )


        self.status_label.config(
            text="Starting video export..."
        )


        self.clear_log()


        self.log(
            "Starting Video Cutter Pro..."
        )


        self.log(
            f"Input: {self.video_path}"
        )


        self.log(
            f"Output: {output_path}"
        )


        self.log(
            f"Start: {self.seconds_to_hms(start_sec)}"
        )


        self.log(
            f"End: {self.seconds_to_hms(end_sec)}"
        )


        # ----------------------------------------------------
        # Start worker
        # ----------------------------------------------------

        worker = threading.Thread(
            target=self.export_worker,
            args=(
                start_sec,
                end_sec,
                output_path,
                archive_size
            ),
            daemon=True
        )


        worker.start()


    # ========================================================
    # UNIQUE OUTPUT PATH
    # ========================================================

    def get_unique_path(self, path):

        if not os.path.exists(path):

            return path


        directory = os.path.dirname(
            path
        )


        filename = os.path.basename(
            path
        )


        base, extension = os.path.splitext(
            filename
        )


        counter = 1


        while True:

            new_path = os.path.join(
                directory,
                f"{base}_{counter}{extension}"
            )


            if not os.path.exists(new_path):

                return new_path


            counter += 1


    # ========================================================
    # EXPORT WORKER
    # ========================================================

    def export_worker(
        self,
        start_sec,
        end_sec,
        output_path,
        archive_size
    ):

        try:

            # ------------------------------------------------
            # FFmpeg
            # ------------------------------------------------

            success = self.run_ffmpeg(
                start_sec,
                end_sec,
                output_path
            )


            if not success:

                return


            if self.stop_requested:

                return


            # ------------------------------------------------
            # Archive
            # ------------------------------------------------

            if self.archive_enabled.get():

                self.root.after(
                    0,
                    lambda: self.status_label.config(
                        text="Creating archive..."
                    )
                )


                self.log(
                    "Video export completed."
                )


                archive_success = self.create_archive(
                    output_path,
                    archive_size
                )


                if not archive_success:

                    return


            # ------------------------------------------------
            # Success
            # ------------------------------------------------

            if not self.stop_requested:

                self.root.after(
                    0,
                    self.export_complete
                )


        except Exception as error:

            self.root.after(
                0,
                lambda: self.export_failed(
                    str(error)
                )
            )


    # ========================================================
    # FFMPEG EXPORT
    # ========================================================

    def run_ffmpeg(
        self,
        start_sec,
        end_sec,
        output_path
    ):

        duration = end_sec - start_sec

        creationflags = 0

        if os.name == "nt":
            creationflags = (
                subprocess.CREATE_NO_WINDOW
                | subprocess.BELOW_NORMAL_PRIORITY_CLASS
            )

        # ========================================================
        # FAST MODE
        # ========================================================
        # Stream copy is much faster because FFmpeg does not decode
        # and re-encode every frame. It is suitable when the source
        # codecs are compatible with the MP4 container.
        #
        # IMPORTANT:
        # Stream-copy cuts can only be exact at/near keyframes.
        # If copying fails, we automatically fall back to accurate
        # H.264/AAC re-encoding.
        # ========================================================

        if self.fast_cut_enabled.get():
            self.log(
                "Fast Cut enabled: trying stream copy first..."
            )

            fast_command = [
                FFMPEG,
                "-hide_banner",
                "-y",

                # Fast input seeking
                "-ss",
                str(start_sec),

                "-i",
                self.video_path,

                "-t",
                str(duration),

                # Copy streams without re-encoding
                "-map",
                "0:v:0",
                "-map",
                "0:a?",
                "-c",
                "copy",

                # MP4 compatibility / timestamp handling
                "-avoid_negative_ts",
                "make_zero",
                "-movflags",
                "+faststart",

                "-progress",
                "pipe:1",
                "-nostats",

                output_path
            ]

            fast_success = self._execute_ffmpeg(
                fast_command,
                duration,
                "Fast Cut"
            )

            if fast_success:
                self.log(
                    "Fast Cut completed using stream copy. "
                    "No video re-encoding was required."
                )
                return True

            # Remove failed/incomplete output before fallback.
            try:
                if os.path.exists(output_path):
                    os.remove(output_path)
            except Exception:
                pass

            if self.stop_requested:
                return False

            self.log(
                "Fast stream copy was not compatible with this "
                "source/container. Falling back to accurate re-encoding..."
            )

        # ========================================================
        # ACCURATE / FALLBACK MODE
        # ========================================================

        self.log(
            "FFmpeg accurate H.264/AAC export started..."
        )

        command = [
            FFMPEG,
            "-hide_banner",
            "-y",

            # Fast seeking
            "-ss",
            str(start_sec),

            "-i",
            self.video_path,

            # Cut duration
            "-t",
            str(duration),

            # Video encoding
            "-c:v",
            "libx264",

            # Faster than the previous veryfast setting.
            # This increases speed at the cost of a larger file.
            "-preset",
            FFMPEG_PRESET,

            "-crf",
            FFMPEG_CRF,

            "-threads",
            FFMPEG_THREADS,

            # Audio
            "-c:a",
            "aac",

            "-b:a",
            "128k",

            # Timestamp handling
            "-avoid_negative_ts",
            "make_zero",

            # MP4 playback optimization
            "-movflags",
            "+faststart",

            # Progress
            "-progress",
            "pipe:1",

            "-nostats",

            output_path
        ]

        success = self._execute_ffmpeg(
            command,
            duration,
            "Accurate Export"
        )

        if not success and not self.stop_requested:

            self.root.after(
                0,
                self.export_failed,
                "FFmpeg failed to export the video."
            )

        return success


    def _execute_ffmpeg(
        self,
        command,
        duration,
        operation_name
    ):

        try:

            self.ffmpeg_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=(
                    subprocess.CREATE_NO_WINDOW
                    | subprocess.BELOW_NORMAL_PRIORITY_CLASS
                    if os.name == "nt"
                    else 0
                )
            )

            while True:

                if self.stop_requested:

                    try:
                        self.ffmpeg_process.terminate()
                    except Exception:
                        pass

                    return False

                line = self.ffmpeg_process.stdout.readline()

                if not line:

                    if self.ffmpeg_process.poll() is not None:
                        break

                    continue

                line = line.strip()

                if line.startswith("out_time_us="):

                    try:

                        output_us = int(
                            line.split("=")[1]
                        )

                        current_seconds = (
                            output_us / 1_000_000
                        )

                        if duration > 0:

                            percent = (
                                current_seconds
                                / duration
                                * 100
                            )

                        else:

                            percent = 0

                        percent = max(
                            0,
                            min(
                                100,
                                percent
                            )
                        )

                        self.root.after(
                            0,
                            self.update_progress,
                            percent,
                            f"{operation_name}..."
                        )

                    except Exception:
                        pass

            return_code = self.ffmpeg_process.returncode

            self.ffmpeg_process = None

            if return_code != 0:

                return False

            self.root.after(
                0,
                self.update_progress,
                100,
                f"{operation_name} completed."
            )

            return True

        except Exception as error:

            self.ffmpeg_process = None

            # In fast mode this error is allowed to trigger the
            # accurate fallback. In accurate mode it is a real error.
            self.log(
                f"{operation_name} error: {error}"
            )

            return False


    # ========================================================
    # CREATE ARCHIVE
    # ========================================================

    def create_archive(
        self,
        video_path,
        archive_size
    ):

        seven_zip = self.find_7zip()


        if not seven_zip:

            self.root.after(
                0,
                lambda: self.export_failed(
                    "7-Zip executable was not found."
                )
            )

            return False


        archive_format = (
            self.archive_format.get()
        )


        # ----------------------------------------------------
        # Archive filename
        # ----------------------------------------------------

        base = os.path.splitext(
            os.path.basename(video_path)
        )[0]


        output_dir = os.path.dirname(
            video_path
        )


        if archive_format == "7z":

            archive_path = os.path.join(
                output_dir,
                base + ".7z"
            )

            archive_type = "7z"


        else:

            archive_path = os.path.join(
                output_dir,
                base + ".zip"
            )

            archive_type = "zip"


        # ----------------------------------------------------
        # Avoid overwriting
        # ----------------------------------------------------

        archive_path = self.get_unique_path(
            archive_path
        )


        # ----------------------------------------------------
        # 7-Zip command
        # ----------------------------------------------------

        command = [

            seven_zip,

            "a",

            "-y",

            f"-t{archive_type}",

            f"-v{archive_size}",

            # Fast archive creation:
            # 0 = automatically use available CPU threads.
            "-mmt=0",

            # Low compression level is much faster and is suitable
            # for already-compressed video files.
            "-mx=1",

            archive_path,

            video_path
        ]


        self.log(
            f"Creating {archive_format} archive..."
        )


        self.log(
            f"Split size: {archive_size}"
        )


        creationflags = 0


        if os.name == "nt":

            creationflags = (
                subprocess.CREATE_NO_WINDOW
                | subprocess.BELOW_NORMAL_PRIORITY_CLASS
            )


        try:

            self.archive_process = subprocess.Popen(
                command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                text=True,
                bufsize=1,
                creationflags=creationflags
            )


            while True:

                if self.stop_requested:

                    try:

                        self.archive_process.terminate()

                    except Exception:
                        pass

                    return False


                line = (
                    self.archive_process
                    .stdout
                    .readline()
                )


                if not line:

                    if (
                        self.archive_process.poll()
                        is not None
                    ):

                        break

                    continue


                line = line.strip()


                if line:

                    self.log(
                        line
                    )


                # ------------------------------------------------
                # Parse 7-Zip percentage
                # ------------------------------------------------

                match = re.search(
                    r"(\d+)%+",
                    line
                )


                if match:

                    percent = float(
                        match.group(1)
                    )


                    overall = (
                        50
                        + percent / 2
                    )


                    self.root.after(
                        0,
                        self.update_progress,
                        overall,
                        "Creating archive..."
                    )


            return_code = (
                self.archive_process.returncode
            )


            self.archive_process = None


            if return_code != 0:

                self.root.after(
                    0,
                    lambda: self.export_failed(
                        "7-Zip failed to create the archive."
                    )
                )

                return False


            self.root.after(
                0,
                self.update_progress,
                100,
                "Archive completed."
            )


            self.log(
                "Archive creation completed."
            )


            return True


        except Exception as error:

            self.archive_process = None


            self.root.after(
                0,
                lambda: self.export_failed(
                    str(error)
                )
            )


            return False


    # ========================================================
    # UPDATE PROGRESS
    # ========================================================

    def update_progress(
        self,
        percentage,
        status
    ):

        self.progress["value"] = percentage


        self.progress_percent.config(
            text=f"{percentage:.1f}%"
        )


        self.status_label.config(
            text=status
        )


    # ========================================================
    # STOP EXPORT
    # ========================================================

    def stop_export(self):

        if not self.export_running:

            return


        answer = messagebox.askyesno(
            "Stop Export",
            "Are you sure you want to stop the current operation?"
        )


        if not answer:

            return


        self.stop_requested = True


        self.status_label.config(
            text="Stopping..."
        )


        self.stop_btn.config(
            state=tk.DISABLED
        )


        # ----------------------------------------------------
        # Stop FFmpeg
        # ----------------------------------------------------

        if self.ffmpeg_process:

            try:

                self.ffmpeg_process.terminate()

            except Exception:
                pass


        # ----------------------------------------------------
        # Stop 7-Zip
        # ----------------------------------------------------

        if self.archive_process:

            try:

                self.archive_process.terminate()

            except Exception:
                pass


        self.log(
            "Stop requested."
        )


        self.root.after(
            1000,
            self.finish_stop
        )


    # ========================================================
    # FINISH STOP
    # ========================================================

    def finish_stop(self):

        if self.ffmpeg_process:

            try:

                self.ffmpeg_process.kill()

            except Exception:
                pass


        if self.archive_process:

            try:

                self.archive_process.kill()

            except Exception:
                pass


        self.export_running = False


        self.progress["value"] = 0


        self.progress_percent.config(
            text="0%"
        )


        self.status_label.config(
            text="Export stopped."
        )


        self.log(
            "Export stopped by user."
        )


        self.restore_ui()


        # ----------------------------------------------------
        # Remove incomplete output
        # ----------------------------------------------------

        if self.output_video_path:

            try:

                if os.path.exists(
                    self.output_video_path
                ):

                    os.remove(
                        self.output_video_path
                    )

            except Exception:
                pass


    # ========================================================
    # SUCCESS
    # ========================================================

    def export_complete(self):

        self.export_running = False


        self.progress["value"] = 100


        self.progress_percent.config(
            text="100%"
        )


        self.status_label.config(
            text="Export completed successfully."
        )


        self.log(
            "======================================"
        )


        self.log(
            "EXPORT COMPLETED SUCCESSFULLY"
        )


        self.log(
            f"Video: {self.output_video_path}"
        )


        if self.archive_enabled.get():

            self.log(
                "Archive created successfully."
            )


        self.restore_ui()


        messagebox.showinfo(
            "Export Complete",
            "Video export completed successfully!\n\n"
            f"Saved to:\n{self.output_video_path}"
        )


    # ========================================================
    # FAILURE
    # ========================================================

    def export_failed(
        self,
        error
    ):

        if not self.export_running:

            return


        self.export_running = False


        self.progress["value"] = 0


        self.progress_percent.config(
            text="0%"
        )


        self.status_label.config(
            text="Export failed."
        )


        self.log(
            "======================================"
        )


        self.log(
            f"ERROR: {error}"
        )


        self.restore_ui()


        messagebox.showerror(
            "Export Error",
            str(error)
        )


    # ========================================================
    # UI LOCK
    # ========================================================

    def set_input_controls(
        self,
        state
    ):

        self.browse_video_btn.config(
            state=state
        )


        self.browse_output_btn.config(
            state=state
        )


        self.issue_radio.config(
            state=state
        )


        self.normal_radio.config(
            state=state
        )


        self.calculate_btn.config(
            state=state
        )

        self.fast_cut_check.config(
            state=state
        )


        self.archive_check.config(
            state=state
        )


    # ========================================================
    # RESTORE UI
    # ========================================================

    def restore_ui(self):

        self.start_export_btn.config(
            state=tk.NORMAL
        )


        self.stop_btn.config(
            state=tk.DISABLED
        )


        self.set_input_controls(
            state=tk.NORMAL
        )


        self.update_archive_controls()


    # ========================================================
    # CLEAR LOG
    # ========================================================

    def clear_log(self):

        self.log_text.config(
            state=tk.NORMAL
        )


        self.log_text.delete(
            "1.0",
            tk.END
        )


        self.log_text.config(
            state=tk.DISABLED
        )


    # ========================================================
    # CLOSE APPLICATION
    # ========================================================

    def close_application(self):

        if self.export_running:

            answer = messagebox.askyesno(
                "Export Running",
                "An export is currently running.\n\n"
                "Do you want to stop it and exit?"
            )


            if not answer:

                return


            self.stop_requested = True


            if self.ffmpeg_process:

                try:

                    self.ffmpeg_process.kill()

                except Exception:
                    pass


            if self.archive_process:

                try:

                    self.archive_process.kill()

                except Exception:
                    pass


        self.root.destroy()


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":

    root = tk.Tk()

    app = VideoCutterPro(
        root
    )

    root.mainloop()