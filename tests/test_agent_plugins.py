# tests/test_agent_plugins.py
from lightfall_pystxmcontrol.agents.stxm_scan_setup import StxmScanSetupAgent
from lightfall_pystxmcontrol.manifest import manifest


def test_scan_setup_identity():
    plugin = StxmScanSetupAgent()
    assert plugin.name == "stxm_scan_setup"
    assert plugin.category == "acquisition"
    assert plugin.get_system_prompt().strip()


def test_scan_setup_references_ship_with_package():
    refs = StxmScanSetupAgent().get_references_dir()
    assert refs is not None and refs.is_dir()
    names = {p.name for p in refs.iterdir()}
    assert {"scan_setup.md", "bl5322_numbers.md"} <= names
    # every reference file the prompt points at must be non-empty
    for p in refs.iterdir():
        assert p.stat().st_size > 0


def test_prompt_mentions_each_reference_file():
    # If a reference is renamed without updating the prompt, the agent can't
    # find it — keep the pointers honest.
    plugin = StxmScanSetupAgent()
    prompt = plugin.get_system_prompt()
    for p in plugin.get_references_dir().iterdir():
        assert p.name in prompt


def test_manifest_registers_agent_entry():
    entries = {(e.type_name, e.name) for e in manifest.plugins}
    assert ("agent", "stxm_scan_setup") in entries
