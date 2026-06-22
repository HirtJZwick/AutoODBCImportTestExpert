"""
gui.py
======
Tkinter GUI for the testXpert III Database Mapping Tool.

Wraps the full workflow in a single window:
  Step 1 — Connect to an ODBC database (DSN)
  Step 2 — Select a table
  Step 3 — View columns and sample data
  Step 4 — Suggest testXpert III parameter mappings (AI)
  Step 5 — Generate and save the INI configuration file
  Step 6 — Save the static ZIMT import script to disk
"""

import shutil
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from database_connector import DatabaseConnector
from ini_file_generator import IniFileGenerator
from parameter_mapper import (
    MappingSuggestion,
    ParameterMapper,
    build_column_context,
    load_parameter_catalog,
)

PROJECT_ROOT           = Path(__file__).resolve().parents[1]
STATIC_ZIMT_SCRIPT     = PROJECT_ROOT / "Config" / "generic_import.zimt"
PARAMETER_CATALOG_PATH = PROJECT_ROOT / "Config" / "testxpert_parameters.json"
API_KEY_FILE           = PROJECT_ROOT / "api_key.txt"

_FONT_HEADER = ("Segoe UI", 12, "bold")
_FONT_NORMAL = ("Segoe UI", 9)
_FONT_MONO   = ("Consolas", 9)
_COLOR_OK    = "#2e7d32"
_COLOR_ERR   = "#c62828"
_COLOR_INFO  = "#1565c0"


class App(tk.Tk):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.title("testXpert III — Database Mapping Tool")
        self.geometry("960x880")
        self.minsize(820, 780)

        self._db               = DatabaseConnector()
        self._columns: list[dict]              = []
        self._rows:    list[list]              = []
        self._suggestions: list[MappingSuggestion] = []
        self._selected_table   = ""

        self._build_ui()
        self._unlock(step=1)

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self):
        tk.Label(
            self,
            text="testXpert III — Database Mapping Tool",
            font=_FONT_HEADER,
            fg="#1a237e",
        ).pack(fill="x", padx=12, pady=(10, 2))
        ttk.Separator(self).pack(fill="x", padx=12, pady=(0, 4))

        # ── Step 1: Connection ──────────────────────────────────────
        self._f1 = ttk.LabelFrame(self, text=" Step 1 — Connect to Database ", padding=8)
        self._f1.pack(fill="x", padx=12, pady=4)

        tk.Label(self._f1, text="DSN:", font=_FONT_NORMAL).grid(row=0, column=0, sticky="w")
        self._dsn_var = tk.StringVar(value="Porsche_DB")
        ttk.Entry(self._f1, textvariable=self._dsn_var, width=28, font=_FONT_NORMAL).grid(
            row=0, column=1, padx=(6, 4)
        )
        self._btn_connect = ttk.Button(self._f1, text="Connect", command=self._on_connect)
        self._btn_connect.grid(row=0, column=2, padx=4)
        self._lbl_conn = tk.Label(
            self._f1, text="● Not connected", font=_FONT_NORMAL, fg=_COLOR_ERR
        )
        self._lbl_conn.grid(row=0, column=3, padx=12, sticky="w")

        # ── Step 2: Table selection ─────────────────────────────────
        self._f2 = ttk.LabelFrame(self, text=" Step 2 — Select Table ", padding=8)
        self._f2.pack(fill="x", padx=12, pady=4)

        list_row = tk.Frame(self._f2)
        list_row.pack(fill="x")
        self._tbl_listbox = tk.Listbox(
            list_row, height=4, font=_FONT_NORMAL, selectmode="single", exportselection=False
        )
        sb_tbl = ttk.Scrollbar(list_row, command=self._tbl_listbox.yview)
        self._tbl_listbox.configure(yscrollcommand=sb_tbl.set)
        self._tbl_listbox.pack(side="left", fill="x", expand=True)
        sb_tbl.pack(side="left", fill="y")

        self._btn_load = ttk.Button(
            self._f2, text="Load Table →", command=self._on_load_table
        )
        self._btn_load.pack(anchor="e", pady=(6, 0))

        # ── Step 3: Columns & sample data ───────────────────────────
        self._f3 = ttk.LabelFrame(self, text=" Step 3 — Columns & Sample Data ", padding=8)
        self._f3.pack(fill="x", padx=12, pady=4)

        self._data_tree = ttk.Treeview(self._f3, show="headings", height=5)
        sb_dx = ttk.Scrollbar(self._f3, orient="horizontal", command=self._data_tree.xview)
        sb_dy = ttk.Scrollbar(self._f3, orient="vertical",   command=self._data_tree.yview)
        self._data_tree.configure(xscrollcommand=sb_dx.set, yscrollcommand=sb_dy.set)
        self._data_tree.grid(row=0, column=0, sticky="nsew")
        sb_dy.grid(row=0, column=1, sticky="ns")
        sb_dx.grid(row=1, column=0, sticky="ew")
        self._f3.columnconfigure(0, weight=1)

        # ── Step 4: Mapping suggestions ─────────────────────────────
        self._f4 = ttk.LabelFrame(self, text=" Step 4 — Parameter Mappings ", padding=8)
        self._f4.pack(fill="both", expand=True, padx=12, pady=4)

        self._btn_suggest = ttk.Button(
            self._f4, text="✦  Suggest Mappings (AI)", command=self._on_suggest
        )
        self._btn_suggest.pack(anchor="w", pady=(0, 6))

        self._map_tree = ttk.Treeview(
            self._f4,
            columns=("column", "parameter", "section", "confidence"),
            show="headings",
            height=7,
        )
        for cid, hdr, w in [
            ("column",     "DB Column",            150),
            ("parameter",  "testXpert Parameter",  250),
            ("section",    "Mapping Section",       150),
            ("confidence", "Confidence",             90),
        ]:
            self._map_tree.heading(cid, text=hdr)
            self._map_tree.column(cid, width=w, anchor="w")

        sb_map = ttk.Scrollbar(self._f4, command=self._map_tree.yview)
        self._map_tree.configure(yscrollcommand=sb_map.set)
        self._map_tree.pack(side="left", fill="both", expand=True)
        sb_map.pack(side="left", fill="y")

        # ── Step 5: Generate INI ─────────────────────────────────────
        self._f5 = ttk.LabelFrame(self, text=" Step 5 — Generate INI File ", padding=8)
        self._f5.pack(fill="x", padx=12, pady=(4, 12))

        tk.Label(self._f5, text="Output path:", font=_FONT_NORMAL).grid(
            row=0, column=0, sticky="w"
        )
        self._ini_path_var = tk.StringVar()
        ttk.Entry(self._f5, textvariable=self._ini_path_var, width=52, font=_FONT_MONO).grid(
            row=0, column=1, padx=(6, 4), sticky="ew"
        )
        ttk.Button(self._f5, text="Browse…", command=self._on_browse).grid(
            row=0, column=2, padx=4
        )
        self._btn_gen = ttk.Button(
            self._f5, text="Generate INI", command=self._on_generate
        )
        self._btn_gen.grid(row=0, column=3, padx=(4, 0))
        self._f5.columnconfigure(1, weight=1)

        self._lbl_ini_status = tk.Label(self._f5, text="", font=_FONT_NORMAL)
        self._lbl_ini_status.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

        # ── Step 6: Save ZIMT import script ─────────────────────────
        self._f6 = ttk.LabelFrame(
            self, text=" Step 6 — Save ZIMT Import Script ", padding=8
        )
        self._f6.pack(fill="x", padx=12, pady=(4, 12))

        tk.Label(self._f6, text="Output path:", font=_FONT_NORMAL).grid(
            row=0, column=0, sticky="w"
        )
        self._zimt_path_var = tk.StringVar()
        ttk.Entry(self._f6, textvariable=self._zimt_path_var, width=52, font=_FONT_MONO).grid(
            row=0, column=1, padx=(6, 4), sticky="ew"
        )
        ttk.Button(self._f6, text="Browse…", command=self._on_browse_zimt).grid(
            row=0, column=2, padx=4
        )
        self._btn_gen_zimt = ttk.Button(
            self._f6, text="Save ZIMT", command=self._on_generate_zimt
        )
        self._btn_gen_zimt.grid(row=0, column=3, padx=(4, 0))
        self._f6.columnconfigure(1, weight=1)

        self._lbl_zimt_status = tk.Label(self._f6, text="", font=_FONT_NORMAL)
        self._lbl_zimt_status.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))

    # ------------------------------------------------------------------
    # Progressive unlock
    # ------------------------------------------------------------------

    def _unlock(self, step: int):
        """Enable widgets in steps 1..N and disable the rest."""
        for n, frame in enumerate([self._f1, self._f2, self._f3, self._f4, self._f5, self._f6], 1):
            self._set_frame_state(frame, enabled=(n <= step))

    def _set_frame_state(self, frame: tk.Widget, enabled: bool):
        state = "normal" if enabled else "disabled"
        for child in frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    # ------------------------------------------------------------------
    # Event handlers
    # ------------------------------------------------------------------

    def _on_connect(self):
        dsn = self._dsn_var.get().strip()
        if not dsn:
            messagebox.showwarning("Input required", "Please enter a DSN name.")
            return

        self._btn_connect.configure(state="disabled", text="Connecting…")
        self._lbl_conn.configure(text="● Connecting…", fg=_COLOR_INFO)

        def task():
            self._db.connect(dsn)
            return self._db.get_tables()

        def done(tables, err):
            self._btn_connect.configure(state="normal", text="Connect")
            if err:
                self._lbl_conn.configure(text=f"● {err}", fg=_COLOR_ERR)
                return
            self._lbl_conn.configure(text=f"● Connected to '{dsn}'", fg=_COLOR_OK)
            self._tbl_listbox.delete(0, "end")
            for t in tables:
                self._tbl_listbox.insert("end", t)
            self._unlock(step=2)

        self._thread(task, done)

    def _on_load_table(self):
        sel = self._tbl_listbox.curselection()
        if not sel:
            messagebox.showwarning("No selection", "Please select a table from the list.")
            return

        self._selected_table = self._tbl_listbox.get(sel[0])
        self._btn_load.configure(state="disabled", text="Loading…")

        def task():
            cols = self._db.get_columns(self._selected_table)
            rows = self._db.get_sample_data(self._selected_table, num_rows=3)
            return cols, rows

        def done(result, err):
            self._btn_load.configure(state="normal", text="Load Table →")
            if err:
                messagebox.showerror("Error loading table", str(err))
                return
            self._columns, self._rows = result
            self._populate_data_tree()
            self._ini_path_var.set(
                str(PROJECT_ROOT / "Config" / f"{self._dsn_var.get().strip()}_config.ini")
            )
            self._zimt_path_var.set(
                str(PROJECT_ROOT / "Config" / f"{self._dsn_var.get().strip()}_import.zimt")
            )
            self._unlock(step=4)

        self._thread(task, done)

    def _on_suggest(self):
        self._btn_suggest.configure(state="disabled", text="Thinking…")
        self._map_tree.delete(*self._map_tree.get_children())

        def task():
            api_key  = API_KEY_FILE.read_text(encoding="utf-8").strip()
            catalog  = load_parameter_catalog(str(PARAMETER_CATALOG_PATH))
            context  = build_column_context(self._columns, self._rows)
            mapper   = ParameterMapper(api_key=api_key)
            return mapper.suggest_mappings(context, catalog)

        def done(suggestions, err):
            self._btn_suggest.configure(state="normal", text="✦  Suggest Mappings (AI)")
            if err:
                messagebox.showerror("Mapping error", str(err))
                return
            self._suggestions = suggestions
            for s in suggestions:
                param = (
                    f"{s.parameter_id} — {s.parameter_name}"
                    if s.parameter_id else "(unmapped)"
                )
                self._map_tree.insert(
                    "", "end",
                    values=(s.column, param, s.mapping_section or "—", f"{s.confidence:.0%}"),
                )
            self._unlock(step=5)

        self._thread(task, done)

    def _on_browse(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".ini",
            filetypes=[("INI files", "*.ini"), ("All files", "*.*")],
            initialdir=str(PROJECT_ROOT / "Config"),
            title="Save INI file as…",
        )
        if path:
            self._ini_path_var.set(path)

    def _on_generate(self):
        out_path = self._ini_path_var.get().strip()
        if not out_path:
            messagebox.showwarning("No path", "Please specify an output path.")
            return
        try:
            gen     = IniFileGenerator()
            content = gen.generate(
                self._dsn_var.get().strip(),
                self._selected_table,
                self._suggestions,
            )
            saved = gen.save(content, out_path)
            self._lbl_ini_status.configure(text=f"✓ Saved: {saved}", fg=_COLOR_OK)
            self._unlock(step=6)
            messagebox.showinfo("Done", f"INI file saved to:\n{saved}")
        except Exception as exc:
            self._lbl_ini_status.configure(text=f"✗ {exc}", fg=_COLOR_ERR)

    def _on_browse_zimt(self):
        path = filedialog.asksaveasfilename(
            defaultextension=".zimt",
            filetypes=[("ZIMT scripts", "*.zimt"), ("All files", "*.*")],
            initialdir=str(PROJECT_ROOT / "Config"),
            title="Save ZIMT script as…",
        )
        if path:
            self._zimt_path_var.set(path)

    def _on_generate_zimt(self):
        out_path = self._zimt_path_var.get().strip()
        if not out_path:
            messagebox.showwarning("No path", "Please specify an output path.")
            return
        try:
            dest = Path(out_path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(STATIC_ZIMT_SCRIPT, dest)
            self._lbl_zimt_status.configure(text=f"✓ Saved: {dest.resolve()}", fg=_COLOR_OK)
            messagebox.showinfo("Done", f"ZIMT script saved to:\n{dest.resolve()}")
        except Exception as exc:
            self._lbl_zimt_status.configure(text=f"✗ {exc}", fg=_COLOR_ERR)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _populate_data_tree(self):
        tree = self._data_tree
        tree.delete(*tree.get_children())
        col_names = [c["name"] for c in self._columns]
        tree.configure(columns=col_names)
        for name in col_names:
            tree.heading(name, text=name)
            tree.column(name, width=130, anchor="w", minwidth=80)
        for row in self._rows:
            tree.insert("", "end", values=row)

    def _thread(self, task_fn, done_fn):
        """Run task_fn in a background thread; call done_fn(result, error) on the main thread."""
        def worker():
            try:
                result = task_fn()
                self.after(0, lambda r=result: done_fn(r, None))
            except Exception as exc:
                self.after(0, lambda e=exc: done_fn(None, e))
        threading.Thread(target=worker, daemon=True).start()
