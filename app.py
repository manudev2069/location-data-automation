import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from pathlib import Path
import threading
import queue
import pandas as pd

from fast_validator import FastValidator
from location_verifier_fast import LocationVerifier

PROJECT_DIR = Path(__file__).resolve().parent
REFERENCE_FILE = PROJECT_DIR / "reference" / "locations.csv"
OUTPUT_ROOT = PROJECT_DIR / "output"


class MultiFileAutomationApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Master Data Validation Automation")
        self.root.geometry("900x620")
        self.root.resizable(False, False)

        self.selected_files = []
        self.events = queue.Queue()
        self.running = False
        self.total_rows_all = 0
        self.completed_rows_all = 0

        self.status_var = tk.StringVar(value="Ready - select one or more files")
        self.percent_var = tk.StringVar(value="0.0%")
        self.count_var = tk.StringVar(value="0 / 0 rows")
        self.file_count_var = tk.StringVar(value="Files selected: 0")
        self.current_file_var = tk.StringVar(value="Current file: -")
        self.valid_var = tk.StringVar(value="Valid: 0")
        self.unknown_var = tk.StringVar(value="Unknown: 0")

        self.build_ui()
        self.root.after(100, self.poll_events)

    def build_ui(self):
        tk.Label(
            self.root,
            text="CSV / Excel Validation & Automation",
            font=("Segoe UI", 18, "bold")
        ).pack(pady=(18, 3))

        tk.Label(
            self.root,
            text="Select one or multiple files after running the code",
            font=("Segoe UI", 10)
        ).pack(pady=(0, 12))

        # Buttons
        button_frame = tk.Frame(self.root)
        button_frame.pack(pady=5)

        self.select_btn = tk.Button(
            button_frame,
            text="Select File(s)",
            command=self.select_files,
            font=("Segoe UI", 10, "bold"),
            padx=18,
            pady=8
        )
        self.select_btn.pack(side="left", padx=5)

        self.clear_btn = tk.Button(
            button_frame,
            text="Clear Selection",
            command=self.clear_files,
            font=("Segoe UI", 10),
            padx=18,
            pady=8,
            state="disabled"
        )
        self.clear_btn.pack(side="left", padx=5)

        # File list
        list_frame = tk.LabelFrame(
            self.root,
            text="Selected Files",
            font=("Segoe UI", 10, "bold"),
            padx=8,
            pady=8
        )
        list_frame.pack(fill="both", padx=30, pady=10)

        scrollbar = tk.Scrollbar(list_frame)
        scrollbar.pack(side="right", fill="y")

        self.file_list = tk.Listbox(
            list_frame,
            height=8,
            width=105,
            yscrollcommand=scrollbar.set,
            font=("Consolas", 9),
            selectmode="extended"
        )
        self.file_list.pack(fill="both", expand=True)
        scrollbar.config(command=self.file_list.yview)

        self.file_count_label = tk.Label(
            list_frame,
            textvariable=self.file_count_var,
            font=("Segoe UI", 9, "bold")
        )
        self.file_count_label.pack(anchor="w", pady=(6, 0))

        self.start_btn = tk.Button(
            self.root,
            text="▶  Start Automation",
            command=self.start_automation,
            font=("Segoe UI", 11, "bold"),
            padx=28,
            pady=9,
            state="disabled"
        )
        self.start_btn.pack(pady=10)

        # Current processing
        tk.Label(
            self.root,
            textvariable=self.current_file_var,
            font=("Segoe UI", 10, "bold")
        ).pack(pady=(2, 2))

        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Segoe UI", 10)
        ).pack(pady=(0, 6))

        self.progress = ttk.Progressbar(
            self.root,
            orient="horizontal",
            maximum=100,
            mode="determinate"
        )
        self.progress.pack(fill="x", padx=30, ipady=4)

        tk.Label(
            self.root,
            textvariable=self.percent_var,
            font=("Segoe UI", 11, "bold")
        ).pack(pady=4)

        tk.Label(
            self.root,
            textvariable=self.count_var,
            font=("Segoe UI", 9)
        ).pack()

        stats = tk.Frame(self.root)
        stats.pack(pady=7)

        tk.Label(
            stats,
            textvariable=self.valid_var,
            font=("Segoe UI", 10)
        ).pack(side="left", padx=20)

        tk.Label(
            stats,
            textvariable=self.unknown_var,
            font=("Segoe UI", 10)
        ).pack(side="left", padx=20)

    def select_files(self):
        paths = filedialog.askopenfilenames(
            parent=self.root,
            title="Select one or more CSV / Excel files",
            filetypes=[
                ("CSV files", "*.csv"),
                ("Excel files", "*.xlsx"),
                ("CSV and Excel files", "*.csv *.xlsx"),
                ("All files", "*.*")
            ]
        )

        if not paths:
            return

        # Replace selection with exactly what the user selected.
        self.selected_files = [Path(p) for p in paths]

        self.file_list.delete(0, tk.END)

        for path in self.selected_files:
            self.file_list.insert(
                tk.END,
                f"{path.name}    [{path.parent}]"
            )

        count = len(self.selected_files)
        self.file_count_var.set(f"Files selected: {count}")
        self.start_btn.config(state="normal")
        self.clear_btn.config(state="normal")
        self.status_var.set("Files selected. Ready to start.")
        self.current_file_var.set("Current file: -")
        self.progress["value"] = 0
        self.percent_var.set("0.0%")

    def clear_files(self):
        if self.running:
            return

        self.selected_files = []
        self.file_list.delete(0, tk.END)
        self.file_count_var.set("Files selected: 0")
        self.start_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.status_var.set("Ready - select one or more files")
        self.current_file_var.set("Current file: -")
        self.progress["value"] = 0
        self.percent_var.set("0.0%")
        self.count_var.set("0 / 0 rows")

    def start_automation(self):
        if not self.selected_files or self.running:
            return

        names = "\n".join(
            f"• {p.name}" for p in self.selected_files
        )

        answer = messagebox.askyesno(
            "Start Automation",
            f"You selected {len(self.selected_files)} file(s):\n\n"
            f"{names}\n\n"
            "Start validation for all selected files?",
            parent=self.root
        )

        if not answer:
            return

        self.running = True
        self.select_btn.config(state="disabled")
        self.clear_btn.config(state="disabled")
        self.start_btn.config(state="disabled")
        self.valid_var.set("Valid: 0")
        self.unknown_var.set("Unknown: 0")
        self.progress["value"] = 0
        self.percent_var.set("0.0%")

        threading.Thread(
            target=self.worker,
            daemon=True
        ).start()

    def read_file(self, path):
        suffix = path.suffix.lower()

        if suffix == ".csv":
            return pd.read_csv(
                path,
                dtype=str,
                keep_default_na=False,
                encoding="utf-8-sig"
            )

        if suffix == ".xlsx":
            return pd.read_excel(
                path,
                dtype=str,
                keep_default_na=False,
                engine="openpyxl"
            )

        raise ValueError(
            f"Unsupported file type: {path.name}. "
            "Please select CSV or XLSX files."
        )

    def worker(self):
        try:
            self.events.put(("status", "Reading selected files..."))

            # Read all selected files first only to calculate the total
            # progress denominator. The data is then processed one file at a time.
            file_data = []
            total_rows = 0

            for path in self.selected_files:
                self.events.put(("current", path.name))
                df = self.read_file(path)
                file_data.append((path, df))
                total_rows += len(df)

            self.events.put(("total", total_rows))

            verifier = LocationVerifier(str(REFERENCE_FILE))
            validator = FastValidator(verifier)

            completed_rows = 0
            total_valid = 0
            total_unknown = 0

            output_locations = []

            for file_index, (path, df) in enumerate(file_data, start=1):
                self.events.put((
                    "file_start",
                    file_index,
                    len(file_data),
                    path.name
                ))

                def callback(done, total, status):
                    self.events.put((
                        "progress_file",
                        completed_rows + done,
                        total_rows,
                        status
                    ))

                valid_df, unknown_df, summary = validator.process(
                    df,
                    progress_callback=callback
                )

                out_dir = OUTPUT_ROOT / path.stem
                out_dir.mkdir(parents=True, exist_ok=True)

                self.events.put((
                    "status",
                    f"Writing output for {path.name}..."
                ))

                valid_df.to_csv(
                    out_dir / "validated_data.csv",
                    index=False,
                    encoding="utf-8-sig"
                )

                unknown_df.to_csv(
                    out_dir / "unknown_data.csv",
                    index=False,
                    encoding="utf-8-sig"
                )

                pd.DataFrame([summary]).to_csv(
                    out_dir / "validation_report.csv",
                    index=False,
                    encoding="utf-8-sig"
                )

                completed_rows += len(df)
                total_valid += len(valid_df)
                total_unknown += len(unknown_df)
                output_locations.append(str(out_dir))

                self.events.put((
                    "progress_file",
                    completed_rows,
                    total_rows,
                    f"Completed: {path.name}"
                ))

            self.events.put((
                "done",
                len(file_data),
                total_rows,
                total_valid,
                total_unknown,
                output_locations
            ))

        except Exception as exc:
            self.events.put(("error", str(exc)))

    def poll_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]

                if kind == "status":
                    self.status_var.set(event[1])

                elif kind == "current":
                    self.current_file_var.set(
                        f"Current file: {event[1]}"
                    )

                elif kind == "total":
                    self.total_rows_all = event[1]
                    self.count_var.set(
                        f"0 / {event[1]:,} rows"
                    )

                elif kind == "file_start":
                    _, index, total_files, name = event
                    self.current_file_var.set(
                        f"File {index} of {total_files}: {name}"
                    )
                    self.status_var.set(
                        f"Processing {name}..."
                    )

                elif kind == "progress_file":
                    _, done, total, status = event
                    pct = done * 100 / total if total else 0

                    self.progress["value"] = pct
                    self.percent_var.set(f"{pct:.1f}%")
                    self.count_var.set(
                        f"{done:,} / {total:,} rows"
                    )
                    self.status_var.set(status)

                elif kind == "done":
                    _, files_done, total_rows, valid, unknown, outputs = event

                    self.running = False
                    self.select_btn.config(state="normal")
                    self.clear_btn.config(state="normal")
                    self.start_btn.config(state="normal")

                    self.progress["value"] = 100
                    self.percent_var.set("100.0%")
                    self.count_var.set(
                        f"{total_rows:,} / {total_rows:,} rows"
                    )
                    self.status_var.set("All selected files completed")
                    self.valid_var.set(f"Valid: {valid:,}")
                    self.unknown_var.set(f"Unknown: {unknown:,}")

                    output_text = "\n".join(outputs)

                    messagebox.showinfo(
                        "Automation Completed",
                        f"Completed files: {files_done}\n"
                        f"Total rows: {total_rows:,}\n"
                        f"Valid rows: {valid:,}\n"
                        f"Unknown rows: {unknown:,}\n\n"
                        f"Output folders:\n{output_text}",
                        parent=self.root
                    )

                elif kind == "error":
                    self.running = False
                    self.select_btn.config(state="normal")
                    self.clear_btn.config(
                        state="normal" if self.selected_files else "disabled"
                    )
                    self.start_btn.config(
                        state="normal" if self.selected_files else "disabled"
                    )
                    self.status_var.set("Error")
                    messagebox.showerror(
                        "Automation Error",
                        event[1],
                        parent=self.root
                    )

        except queue.Empty:
            pass

        self.root.after(100, self.poll_events)


if __name__ == "__main__":
    root = tk.Tk()
    MultiFileAutomationApp(root)
    root.mainloop()
