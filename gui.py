import os
import queue
import threading
import tkinter as tk

from tkinter import ttk
from tkinter import filedialog
from tkinter import messagebox
from tkinter import scrolledtext

from cancellation import OperationCancelled
from duplicates import run_remove_duplicates, run_remove_video_duplicates
from similar import run_find_similar
from sorter import run_sort


class App:

    def __init__(self, root):

        self.root = root
        self._messages = queue.Queue()
        self._cancel_event = None
        self._worker = None
        self._folder_scan_queue = queue.Queue()
        self._folder_scan_active = False
        self._closing = False

        root.title("Foto-Sortierer")
        root.geometry("900x700")
        root.minsize(850, 600)
        root.grid_rowconfigure(0, weight=1)
        root.grid_columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(root, highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        scrollbar = ttk.Scrollbar(
            root,
            orient="vertical",
            command=self.canvas.yview
        )
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.content_frame = ttk.Frame(self.canvas)
        self.content_window = self.canvas.create_window(
            (0, 0),
            window=self.content_frame,
            anchor="nw"
        )
        self.content_frame.bind(
            "<Configure>",
            self._update_scroll_region
        )
        self.canvas.bind(
            "<Configure>",
            self._resize_content
        )

        # --------------------------------------------------
        # Variablen
        # --------------------------------------------------

        self.folder_var = tk.StringVar()

        self.mode_var = tk.StringVar(
            value="test"
        )

        self.action_var = tk.StringVar(
            value="sort"
        )

        self.status_var = tk.StringVar(
            value="Bereit"
        )

        self.file_count_var = tk.StringVar(
            value="Dateien: -"
        )

        self.folder_count_var = tk.StringVar(
            value="Ordner: -"
        )

        self.folder_size_var = tk.StringVar(
            value="Größe: -"
        )
        self.log_height_var = tk.StringVar(
            value="10 Zeilen"
        )

        # --------------------------------------------------
        # Header
        # --------------------------------------------------

        header = ttk.Frame(
            self.content_frame,
            padding=15
        )

        header.pack(fill="x")

        ttk.Label(
            header,
            text="Foto-Sortierer",
            font=("Segoe UI", 20, "bold")
        ).pack(anchor="w")

        ttk.Label(
            header,
            text=(
                "Willkommen beim Foto-Sortierer.\n"
                "Dieses Programm kann Fotos und Videos sortieren,\n"
                "Duplikate erkennen und ähnliche Bilder finden."
            )
        ).pack(
            anchor="w",
            pady=(5, 0)
        )

        # --------------------------------------------------
        # Ordnerauswahl
        # --------------------------------------------------

        folder_frame = ttk.LabelFrame(
            self.content_frame,
            text="Ordner auswählen",
            padding=15
        )

        folder_frame.pack(
            fill="x",
            padx=15,
            pady=8
        )

        self.folder_button = ttk.Button(
            folder_frame,
            text="Ordner auswählen",
            command=self.select_folder
        )
        self.folder_button.pack(
            anchor="w"
        )

        ttk.Label(
            folder_frame,
            textvariable=self.folder_var,
            foreground="blue"
        ).pack(
            anchor="w",
            pady=(10, 8)
        )

        info_frame = ttk.Frame(folder_frame)
        info_frame.pack(fill="x")

        ttk.Label(
            info_frame,
            textvariable=self.file_count_var
        ).pack(
            side="left",
            padx=(0, 30)
        )

        ttk.Label(
            info_frame,
            textvariable=self.folder_count_var
        ).pack(
            side="left",
            padx=(0, 30)
        )

        ttk.Label(
            info_frame,
            textvariable=self.folder_size_var
        ).pack(
            side="left"
        )

        # --------------------------------------------------
        # Modus
        # --------------------------------------------------

        mode_frame = ttk.LabelFrame(
            self.content_frame,
            text="Modus",
            padding=15
        )

        mode_frame.pack(
            fill="x",
            padx=15,
            pady=8
        )

        self.mode_buttons = []
        test_mode_button = ttk.Radiobutton(
            mode_frame,
            text="Testlauf",
            variable=self.mode_var,
            value="test"
        )
        test_mode_button.pack(
            side="left",
            padx=(0, 25)
        )
        self.mode_buttons.append(test_mode_button)

        real_mode_button = ttk.Radiobutton(
            mode_frame,
            text="Echter Lauf",
            variable=self.mode_var,
            value="real"
        )
        real_mode_button.pack(
            side="left"
        )
        self.mode_buttons.append(real_mode_button)

        # --------------------------------------------------
        # Aktion
        # --------------------------------------------------

        action_frame = ttk.LabelFrame(
            self.content_frame,
            text="Aktion auswählen",
            padding=15
        )

        action_frame.pack(
            fill="x",
            padx=15,
            pady=8
        )

        self.action_buttons = []
        sort_button = ttk.Radiobutton(
            action_frame,
            text="Fotos / Videos sortieren",
            variable=self.action_var,
            value="sort"
        )
        sort_button.pack(
            side="left",
            padx=(0, 25)
        )
        self.action_buttons.append(sort_button)

        duplicates_button = ttk.Radiobutton(
            action_frame,
            text="Exakte Duplikate entfernen",
            variable=self.action_var,
            value="duplicates"
        )
        duplicates_button.pack(
            side="left",
            padx=(0, 25)
        )
        self.action_buttons.append(duplicates_button)

        video_duplicates_button = ttk.Radiobutton(
            action_frame,
            text="Video-Duplikate finden",
            variable=self.action_var,
            value="video_duplicates"
        )
        video_duplicates_button.pack(
            side="left",
            padx=(0, 25)
        )
        self.action_buttons.append(video_duplicates_button)

        similar_button = ttk.Radiobutton(
            action_frame,
            text="Ähnliche Fotos finden",
            variable=self.action_var,
            value="similar"
        )
        similar_button.pack(
            side="left"
        )
        self.action_buttons.append(similar_button)

        # --------------------------------------------------
        # Fortschritt
        # --------------------------------------------------

        progress_frame = ttk.LabelFrame(
            self.content_frame,
            text="Fortschritt",
            padding=15
        )

        progress_frame.pack(
            fill="x",
            padx=15,
            pady=8
        )

        self.progress = ttk.Progressbar(
            progress_frame,
            mode="determinate"
        )

        self.progress.pack(fill="x")

        # --------------------------------------------------
        # Startbutton
        # --------------------------------------------------

        button_frame = ttk.Frame(
            self.content_frame,
            padding=10
        )

        button_frame.pack(fill="x")

        self.start_button = ttk.Button(
            button_frame,
            text="START",
            command=self.start_pressed
        )
        self.start_button.pack(side="left", padx=(0, 8))

        self.cancel_button = ttk.Button(
            button_frame,
            text="Abbrechen",
            command=self.cancel_pressed,
            state="disabled"
        )
        self.cancel_button.pack(side="left")

        # --------------------------------------------------
        # Logfenster
        # --------------------------------------------------

        log_frame = ttk.LabelFrame(
            self.content_frame,
            text="Ausgabe / Protokoll",
            padding=10
        )

        log_frame.pack(
            fill="both",
            padx=15,
            pady=8
        )

        log_controls = ttk.Frame(log_frame)
        log_controls.pack(fill="x", pady=(0, 5))

        ttk.Label(
            log_controls,
            text="Protokollhöhe:"
        ).pack(side="left")

        self.log_height = ttk.Scale(
            log_controls,
            from_=8,
            to=40
        )
        self.log_height.set(10)
        self.log_height.pack(
            side="left",
            fill="x",
            expand=True,
            padx=(8, 10)
        )

        ttk.Label(
            log_controls,
            textvariable=self.log_height_var,
            width=10
        ).pack(side="right")

        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            font=("Consolas", 10),
            height=10
        )
        self.log_height.configure(
            command=self.set_log_height
        )
        self.set_log_height(self.log_height.get())

        self.log_box.pack(
            fill="both",
            expand=True
        )

        # --------------------------------------------------
        # Statusleiste
        # --------------------------------------------------

        ttk.Label(
            self.content_frame,
            textvariable=self.status_var
        ).pack(
            anchor="w",
            padx=10,
            pady=5
        )

        self.log("Programm gestartet.")
        self.log("Bitte einen Ordner auswählen.")
        self.root.protocol("WM_DELETE_WINDOW", self.close_window)

    def _update_scroll_region(self, _event):
        self.canvas.configure(
            scrollregion=self.canvas.bbox("all")
        )

    def _resize_content(self, event):
        self.canvas.itemconfigure(
            self.content_window,
            width=event.width
        )

    def set_log_height(self, value):
        rows = round(float(value))
        self.log_box.configure(height=rows)
        self.log_height_var.set(f"{rows} Zeilen")

    # --------------------------------------------------
    # Ordner auswählen
    # --------------------------------------------------

    def select_folder(self):

        path = filedialog.askdirectory(
            title="Bilderordner auswählen"
        )

        if not path:
            return

        self.folder_var.set(path)
        self.file_count_var.set("Dateien: wird gezählt ...")
        self.folder_count_var.set("Ordner: wird gezählt ...")
        self.folder_size_var.set("Größe: wird berechnet ...")
        self._folder_scan_active = True
        self.folder_button.configure(state="disabled")
        self.start_button.configure(state="disabled")
        self.status_var.set("Ordner wird eingelesen ...")
        self._folder_scan_queue = queue.Queue()
        threading.Thread(
            target=self._scan_folder,
            args=(path, self._folder_scan_queue),
            daemon=True
        ).start()
        self.root.after(50, self._poll_folder_scan)

    @staticmethod
    def _scan_folder(path, result_queue):
        try:
            file_count = 0
            folder_count = 0
            total_size = 0

            for root, dirs, files in os.walk(path):
                folder_count += len(dirs)
                file_count += len(files)

                for filename in files:
                    try:
                        total_size += os.path.getsize(
                            os.path.join(root, filename)
                        )
                    except OSError:
                        pass

            result_queue.put(("done", file_count, folder_count, total_size))
        except Exception as error:
            result_queue.put(("error", error))

    def _poll_folder_scan(self):
        try:
            result = self._folder_scan_queue.get_nowait()
        except queue.Empty:
            self.root.after(50, self._poll_folder_scan)
            return

        self._folder_scan_active = False
        self.folder_button.configure(state="normal")
        self.start_button.configure(state="normal")
        if result[0] == "error":
            self.status_var.set("Ordner konnte nicht eingelesen werden")
            messagebox.showerror("Ordneranalyse fehlgeschlagen", str(result[1]))
        else:
            _, file_count, folder_count, total_size = result
            self.file_count_var.set(f"Dateien: {file_count:,}")
            self.folder_count_var.set(f"Ordner: {folder_count:,}")
            self.folder_size_var.set(
                f"Größe: {total_size / (1024 ** 3):.2f} GB"
            )
            self.status_var.set("Bereit")

    # --------------------------------------------------
    # Logging
    # --------------------------------------------------

    def log(self, text):

        self.log_box.insert(
            tk.END,
            text + "\n"
        )

        self.log_box.see(
            tk.END
        )

    # --------------------------------------------------
    # Start
    # --------------------------------------------------

    def start_pressed(self):

        if self._worker is not None:
            return

        folder = self.folder_var.get()

        if not folder:

            messagebox.showwarning(
                "Ordner fehlt",
                "Bitte zuerst einen Ordner auswählen."
            )

            return

        if not os.path.isdir(folder):
            messagebox.showerror(
                "Ordner nicht gefunden",
                "Der ausgewählte Ordner ist nicht mehr verfügbar."
            )
            return

        if self.mode_var.get() == "real":

            ok = messagebox.askyesno(
                "Echtlauf bestätigen",
                (
                    "Sie haben 'Echter Lauf' gewählt.\n\n"
                    "Dateien können verändert werden.\n\n"
                    "Fortfahren?"
                )
            )

            if not ok:
                return

        action_names = {
            "sort": "Fotos / Videos sortieren",
            "duplicates": "Exakte Duplikate entfernen",
            "video_duplicates": "Video-Duplikate finden",
            "similar": "Ähnliche Fotos finden"
        }

        self.log("")
        self.log("=" * 50)
        self.log(f"Ordner: {folder}")

        self.log(
            f"Modus: {'Testlauf' if self.mode_var.get() == 'test' else 'Echter Lauf'}"
        )

        self.log(
            f"Aktion: {action_names[self.action_var.get()]}"
        )

        test_mode = self.mode_var.get() == "test"
        self.progress["value"] = 0
        action = self.action_var.get()
        self.status_var.set("Suche Mediendateien ...")
        self.root.config(cursor="watch")

        self._cancel_event = threading.Event()
        self._messages = queue.Queue()
        self.start_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.folder_button.configure(state="disabled")
        for button in self.mode_buttons + self.action_buttons:
            button.configure(state="disabled")
        self._worker = threading.Thread(
            target=self._run_action,
            args=(folder, action, test_mode, self._cancel_event),
            daemon=True
        )
        self._worker.start()
        self.root.after(50, self._poll_worker)

    def _run_action(self, folder, action, test_mode, cancel_event):
        def log_from_worker(text):
            self._messages.put(("log", text))

        def progress_from_worker(processed, total):
            self._messages.put(("progress", processed, total))

        try:
            if action == "duplicates":
                result = run_remove_duplicates(
                    folder,
                    test_mode,
                    log_from_worker,
                    progress_from_worker,
                    cancel_event
                )
            elif action == "video_duplicates":
                result = run_remove_video_duplicates(
                    folder,
                    test_mode,
                    log_from_worker,
                    progress_from_worker,
                    cancel_event
                )
            elif action == "similar":
                result = run_find_similar(
                    folder,
                    test_mode,
                    log_from_worker,
                    progress_from_worker,
                    cancel_event
                )
            else:
                result = run_sort(
                    folder,
                    test_mode,
                    log_from_worker,
                    progress_from_worker,
                    cancel_event
                )
        except OperationCancelled:
            self._messages.put(("cancelled",))
        except Exception as error:
            self._messages.put(("error", error))
        else:
            self._messages.put(("done", action, test_mode, result))

    def cancel_pressed(self):
        if self._cancel_event is not None:
            self._cancel_event.set()
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Abbruch wird ausgeführt ...")

    def _poll_worker(self):
        terminal_message = None
        log_lines = []
        latest_progress = None

        for _ in range(250):
            try:
                message = self._messages.get_nowait()
            except queue.Empty:
                break

            if message[0] == "log":
                log_lines.append(message[1])
            elif message[0] == "progress":
                latest_progress = message[1:]
            else:
                terminal_message = message
                break

        if log_lines:
            self.log("\n".join(log_lines))
        if latest_progress is not None:
            processed, total = latest_progress
            self.progress["maximum"] = max(total, 1)
            self.progress["value"] = processed
            self.status_var.set(f"Untersucht: {processed} von {total}")

        if terminal_message is not None:
            self._finish_operation(terminal_message)
            return

        self.root.after(50, self._poll_worker)

    def _finish_operation(self, message):
        self._worker = None
        self._cancel_event = None
        self.root.config(cursor="")
        self.start_button.configure(state="normal")
        self.cancel_button.configure(state="disabled")
        self.folder_button.configure(state="normal")
        for button in self.mode_buttons + self.action_buttons:
            button.configure(state="normal")

        if message[0] == "cancelled":
            self.log("Vorgang abgebrochen. Bereits ausgeführte Dateiänderungen bleiben bestehen.")
            self.status_var.set("Abgebrochen")
        elif message[0] == "error":
            error = message[1]
            messagebox.showerror(
                "Vorgang fehlgeschlagen",
                str(error)
            )
            self.status_var.set("Fehler bei der Verarbeitung")
        else:
            _, action, test_mode, result = message
            if action == "similar" and test_mode:
                self.status_var.set(
                    f"Testlauf fertig: {result['eligible_groups']} Serien ab "
                    f"4 Bildern, {result['below_threshold_groups']} kleinere "
                    "Serien nur protokolliert; CSV erstellt"
                )
            elif action == "similar":
                self.status_var.set(
                    f"Fertig: {result['moved']} Bilder in "
                    f"{result['eligible_groups']} Serien verschoben; "
                    f"{result['below_threshold_groups']} kleinere Serien "
                    "nur protokolliert, "
                    f"{result['errors']} Fehler"
                )
            elif action == "duplicates" and test_mode:
                self.status_var.set(
                    f"Testlauf fertig: {result['duplicates']} Duplikate gefunden; "
                    "CSV erstellt"
                )
            elif action == "duplicates":
                self.status_var.set(
                    f"Fertig: {result['duplicates']} Duplikate verschoben, "
                    f"{result['errors']} Fehler"
                )
            elif action == "video_duplicates" and test_mode:
                self.status_var.set(
                    f"Testlauf fertig: {result['duplicates']} Video-Duplikate "
                    "gefunden; CSV erstellt"
                )
            elif action == "video_duplicates":
                self.status_var.set(
                    f"Fertig: {result['duplicates']} Video-Duplikate verschoben, "
                    f"{result['errors']} Fehler"
                )
            elif test_mode:
                self.status_var.set(
                    f"Testlauf fertig: {result['sorted']} verschoben, "
                    f"{result['unsortable']} nicht sortierbar, "
                    f"{result['errors']} Fehler; CSV erstellt"
                )
            else:
                self.status_var.set(
                    f"Fertig: {result['sorted']} sortiert, "
                    f"{result['unsortable']} nicht sortierbar, "
                    f"{result['errors']} Fehler"
                )
        if self._closing:
            self.root.destroy()

    def close_window(self):
        if self._folder_scan_active:
            self._closing = True
            self.status_var.set("Ordneranalyse wird beendet ...")
            self.root.after(50, self._wait_for_folder_scan)
            return

        if self._worker is None:
            self.root.destroy()
            return

        self._closing = True
        self.cancel_pressed()

    def _wait_for_folder_scan(self):
        if self._folder_scan_active:
            self.root.after(50, self._wait_for_folder_scan)
        else:
            self.root.destroy()