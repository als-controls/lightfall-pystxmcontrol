"""Energy-range definition: rows of (start, stop, n_points) expanding to the
flat eV list the stxm_energy_stack plan takes (spec §3.3). Absorbs the
FUNCTION of pystxmcontrol's energyDef.py on Lightfall idioms — no code import.
"""
from __future__ import annotations

import numpy as np
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDoubleSpinBox, QHBoxLayout, QPushButton, QSpinBox, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)


def expand_ranges(ranges: list[tuple[float, float, int]]) -> list[float]:
    """Expand (start, stop, n) rows to a flat energies list.

    n == 1 yields [start]. n < 1 raises ValueError. Rows concatenate in order;
    no dedup (a shared boundary point appearing twice is the user's intent).
    """
    energies: list[float] = []
    for start, stop, n in ranges:
        if n < 1:
            raise ValueError(f"range ({start}, {stop}) needs n >= 1, got {n}")
        energies.extend(float(v) for v in np.linspace(start, stop, int(n)))
    return energies


class EnergyRangesEditor(QWidget):
    """Table of (start eV, stop eV, points) rows + add/remove controls."""

    changed = Signal()

    _COLS = ("Start (eV)", "Stop (eV)", "Points")

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._table = QTableWidget(0, len(self._COLS), self)
        self._table.setHorizontalHeaderLabels(self._COLS)
        self._start = QDoubleSpinBox(self); self._start.setRange(0.0, 100000.0); self._start.setValue(500.0)
        self._stop = QDoubleSpinBox(self); self._stop.setRange(0.0, 100000.0); self._stop.setValue(520.0)
        self._n = QSpinBox(self); self._n.setRange(1, 100000); self._n.setValue(3)
        add = QPushButton("Add", self)
        add.clicked.connect(lambda: self.add_range(self._start.value(), self._stop.value(), self._n.value()))
        rm = QPushButton("Remove", self)
        rm.clicked.connect(self.remove_selected)

        row = QHBoxLayout()
        for w in (self._start, self._stop, self._n, add, rm):
            row.addWidget(w)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.addLayout(row)
        lay.addWidget(self._table)

    def add_range(self, start: float, stop: float, n: int) -> None:
        r = self._table.rowCount()
        self._table.insertRow(r)
        for c, v in enumerate((start, stop, int(n))):
            item = QTableWidgetItem(str(v))
            # Cells are read-only (spec §3.3 defines the surface as add/remove
            # rows only): inline editing would bypass the `changed` signal and
            # feed unguarded float()/int() parsing in ranges(). Rows are
            # edited by remove + re-add; inline editing (with validation and
            # changed wiring) is deliberately out of scope for this slice.
            item.setFlags(item.flags() & ~Qt.ItemIsEditable)
            self._table.setItem(r, c, item)
        self.changed.emit()

    def remove_selected(self) -> None:
        rows = sorted({i.row() for i in self._table.selectedIndexes()}, reverse=True)
        for r in rows:
            self._table.removeRow(r)
        if rows:
            self.changed.emit()

    def ranges(self) -> list[tuple[float, float, int]]:
        out = []
        for r in range(self._table.rowCount()):
            out.append((float(self._table.item(r, 0).text()),
                        float(self._table.item(r, 1).text()),
                        int(self._table.item(r, 2).text())))
        return out

    def energies(self) -> list[float]:
        return expand_ranges(self.ranges())
