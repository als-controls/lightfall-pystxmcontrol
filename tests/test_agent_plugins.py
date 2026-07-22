# tests/test_agent_plugins.py
import pytest

from lightfall_pystxmcontrol.agents.stxm_data_analysis import StxmDataAnalysisAgent
from lightfall_pystxmcontrol.agents.stxm_scan_setup import StxmScanSetupAgent
from lightfall_pystxmcontrol.agents.stxm_technique_guide import StxmTechniqueGuideAgent
from lightfall_pystxmcontrol.manifest import manifest

AGENT_CLASSES = [StxmScanSetupAgent, StxmTechniqueGuideAgent, StxmDataAnalysisAgent]


@pytest.fixture(params=AGENT_CLASSES, ids=lambda c: c.__name__)
def agent(request):
    return request.param()


def test_identity(agent):
    assert agent.name and agent.name == agent.name.lower()
    assert agent.category in ("acquisition", "analysis", "operations")
    assert agent.get_system_prompt().strip()
    assert agent.description


def test_references_ship_with_package(agent):
    refs = agent.get_references_dir()
    assert refs is not None and refs.is_dir()
    files = list(refs.iterdir())
    assert files
    for p in files:
        assert p.suffix == ".md" and p.stat().st_size > 0


def test_prompt_mentions_each_reference_file(agent):
    # If a reference is renamed without updating the prompt, the agent can't
    # find it — keep the pointers honest.
    prompt = agent.get_system_prompt()
    for p in agent.get_references_dir().iterdir():
        assert p.name in prompt


def test_manifest_registers_agent_entries():
    entries = {(e.type_name, e.name) for e in manifest.plugins}
    for cls in AGENT_CLASSES:
        assert ("agent", cls().name) in entries


def test_scan_setup_expected_reference_names():
    refs = StxmScanSetupAgent().get_references_dir()
    assert {"scan_setup.md", "bl5322_numbers.md"} <= {p.name for p in refs.iterdir()}


def test_technique_guide_expected_reference_names():
    refs = StxmTechniqueGuideAgent().get_references_dir()
    assert {"techniques.md", "als_beamlines.md"} <= {p.name for p in refs.iterdir()}
