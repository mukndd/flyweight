import pytest

from services.brain import neural, preprocess


@pytest.fixture
def graph(tmp_path, monkeypatch):
    monkeypatch.setattr(preprocess, "PROCESSED", tmp_path)
    monkeypatch.setattr(neural, "PROCESSED", tmp_path)
    preprocess.synthetic(64, 783)
    return neural.Graph(synthetic=True)
