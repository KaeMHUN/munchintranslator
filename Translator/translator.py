#!/usr/bin/env python3
"""Munchkin Translation TUI — 3-column editor. Only saves Hungarian file."""

from pathlib import Path
from textual import on # type: ignore
from textual.app import App, ComposeResult # type: ignore
from textual.binding import Binding # type: ignore
from textual.containers import Horizontal, Vertical # type: ignore
from textual.screen import ModalScreen # type: ignore
from textual.widgets import DataTable, Header, Footer, Input, Label, Button # type: ignore

EN_FILE = Path(__file__).parent / "localization_en_US.txt"
HU_FILE = Path(__file__).parent / "hungarian.txt"


class EditDialog(ModalScreen):
    BINDINGS = [Binding("escape", "cancel", "Cancel")]

    def __init__(self, row_idx: int, key_name: str, current: str):
        super().__init__()
        self.row_idx = row_idx
        self.key_name = key_name
        self.current = current

    def compose(self):
        yield Vertical(
            Label(f"[b]{self.key_name}[/b] \u2014 Hungarian"),
            Input(value=self.current, id="editor"),
            Horizontal(
                Button("Save", id="save", variant="primary"),
                Button("Cancel", id="cancel"),
            ),
            id="dialog",
        )

    def on_input_submitted(self, event: Input.Submitted):
        event.stop()
        self.dismiss((self.row_idx, event.value))

    def action_cancel(self):
        self.dismiss()

    def on_button_pressed(self, event: Button.Pressed):
        if event.button.id == "save":
            val = self.query_one("#editor", Input).value
            self.dismiss((self.row_idx, val))
        else:
            self.dismiss()


class TranslatorApp(App):
    CSS = """
    #bar { height: 3; padding: 0 1; align: center middle; }
    #table { height: 1fr; }
    #status { width: 1fr; padding: 0 2; }
    #dialog { width: 90%; height: auto; margin: 1 2; padding: 1 2; border: solid $primary; background: $surface; }
    #dialog Input { width: 100%; }
    #dialog Horizontal { height: 3; align: center middle; }
    """

    BINDINGS = [
        Binding("ctrl+s", "save", "Save"),
        Binding("ctrl+q", "quit", "Quit"),
    ]

    def __init__(self):
        super().__init__()
        self.entries, self.header = _load()
        self.dirty: set[int] = set()
        self._editing = False

    def compose(self):
        yield Header()
        yield Horizontal(
            Button("Save", id="save", variant="primary"),
            Label("", id="status"),
            id="bar",
        )
        from shutil import get_terminal_size
        tw = get_terminal_size().columns
        kw = 14
        ew = hw = max((tw - kw - 8) // 2, 28)
        tbl = DataTable(id="table")
        tbl.cursor_type = "cell"
        tbl.show_row_labels = False
        tbl.zebra_stripes = True
        self._col_key = tbl.add_column("Key", width=kw)
        self._col_en = tbl.add_column("English", width=ew)
        self._col_hu = tbl.add_column("Hungarian", width=hw)
        yield tbl
        yield Footer()

    def on_mount(self):
        tbl = self.query_one("#table", DataTable)
        for i, (k, en, hu) in enumerate(self.entries):
            tbl.add_row(k, en, hu, key=str(i))
        self.query_one("#status", Label).update(f"{len(self.entries)} rows loaded")

    @on(Button.Pressed, "#save")
    def action_save(self):
        lines_hu = [self.header]
        for k, en, hu in self.entries:
            lines_hu.append(f"{k}={hu}")
        HU_FILE.write_text("\n".join(lines_hu) + "\n", encoding="utf-8")
        self.dirty.clear()
        self.query_one("#status", Label).update("Saved")

    @on(DataTable.CellSelected, "#table")
    def on_cell_selected(self, event: DataTable.CellSelected):
        if self._editing:
            return
        self._editing = True
        event.stop()
        row_idx = event.coordinate.row
        current = self.entries[row_idx][2]
        key = self.entries[row_idx][0]

        def cb(result):
            if result is not None:
                ri, val = result
                e = list(self.entries[ri])
                e[2] = val
                self.entries[ri] = tuple(e)
                self.dirty.add(ri)
                self.query_one("#table", DataTable).update_cell(str(ri), self._col_hu, val)
                self.query_one("#status", Label).update(f"Modified: {len(self.dirty)}")
            self.set_timer(0.3, self._reset_editing)

        self.push_screen(EditDialog(row_idx, key, current), cb)

    def _reset_editing(self):
        self._editing = False


def _parse(fp):
    d = {}
    header = None
    for line in fp.read_text(encoding="utf-8").splitlines():
        if header is None:
            header = line
            continue
        if "=" not in line:
            continue
        k, v = line.split("=", 1)
        d[k] = v
    return d, header


def _load():
    en, hdr = _parse(EN_FILE)
    hu, _ = _parse(HU_FILE)
    keys = sorted(set(en) | set(hu))
    entries = [(k, en.get(k, ""), hu.get(k, "")) for k in keys]
    return entries, hdr


if __name__ == "__main__":
    TranslatorApp().run()