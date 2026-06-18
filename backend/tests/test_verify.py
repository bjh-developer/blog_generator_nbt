from app.agents import verify
from app.schemas import Metric

TEXT = "Luma raised $3 million in 2020. It now has 250K+ active hosts across 150 countries."


def test_metric_grounded_high():
    assert verify.ground_score("250K+ active hosts", TEXT) >= 0.8


def test_metric_absent_low():
    assert verify.ground_score("900M users", TEXT) < 0.5


def test_filter_drops_ungrounded_metrics():
    kept = verify.filter_metrics(
        [Metric(label="Hosts", value="250K+"), Metric(label="Users", value="900M")],
        TEXT, threshold=0.5)
    assert [m.value for m in kept] == ["250K+"]
