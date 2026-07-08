"""Task 11: energy-range expansion + editor widget (spec §3.3)."""
import pytest


def _qapp():
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


class TestExpandRanges:
    def test_single_range(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(500.0, 520.0, 3)]) == [500.0, 510.0, 520.0]

    def test_multiple_ranges_concatenate(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(500.0, 510.0, 2), (700.0, 700.0, 1)]) == [500.0, 510.0, 700.0]

    def test_single_point_range(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([(600.0, 640.0, 1)]) == [600.0]

    def test_empty(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        assert expand_ranges([]) == []

    def test_n_below_one_rejected(self):
        from lightfall_pystxmcontrol.energy_ranges import expand_ranges
        with pytest.raises(ValueError):
            expand_ranges([(500.0, 510.0, 0)])


class TestEditorWidget:
    def test_add_and_expand(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        ed.add_range(500.0, 520.0, 3)
        ed.add_range(700.0, 700.0, 1)
        assert ed.ranges() == [(500.0, 520.0, 3), (700.0, 700.0, 1)]
        assert ed.energies() == [500.0, 510.0, 520.0, 700.0]

    def test_changed_signal(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        with qtbot.waitSignal(ed.changed, timeout=1000):
            ed.add_range(500.0, 510.0, 2)

    def test_remove_selected(self, qtbot):
        from lightfall_pystxmcontrol.energy_ranges import EnergyRangesEditor
        _qapp()
        ed = EnergyRangesEditor()
        qtbot.addWidget(ed)
        ed.add_range(500.0, 510.0, 2)
        ed.add_range(700.0, 710.0, 2)
        ed._table.selectRow(0)
        ed.remove_selected()
        assert ed.ranges() == [(700.0, 710.0, 2)]
