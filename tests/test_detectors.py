from datetime import datetime, timedelta

from predarb.config import DetectorConfig, BrokerConfig
from predarb.detectors.parity import ParityDetector
from predarb.detectors.ladder import LadderDetector
from predarb.detectors.duplicates import DuplicateDetector
from predarb.detectors.exclusivesum import ExclusiveSumDetector
from predarb.detectors.timelag import TimeLagDetector
from predarb.detectors.consistency import ConsistencyDetector
from predarb.models import Market, Outcome


def test_parity_detector():
    cfg = DetectorConfig(parity_threshold=0.99)
    broker_cfg = BrokerConfig()
    m = Market(
        id="p1",
        question="YesNo",
        outcomes=[Outcome(id="y", label="Yes", price=0.45), Outcome(id="n", label="No", price=0.45)],
    )
    opps = ParityDetector(cfg, broker_cfg).detect([m])
    assert len(opps) == 1
    assert opps[0].net_edge > 0


def test_ladder_violation(markets):
    opps = LadderDetector(DetectorConfig()).detect(markets)
    assert any(o.type == "LADDER" for o in opps)


def test_duplicates_detector(markets):
    opps = DuplicateDetector(DetectorConfig(duplicate_price_diff_threshold=0.05)).detect(markets)
    assert any("Duplicate" in o.description or o.type == "DUPLICATE" for o in opps)


def test_exclusive_sum_detector(markets):
    opps = ExclusiveSumDetector(DetectorConfig(exclusive_sum_tolerance=0.02)).detect(markets)
    assert any(o.type == "EXCLUSIVE_SUM" for o in opps)


def test_timelag_detector():
    cfg = DetectorConfig(timelag_persistence_minutes=1, timelag_price_jump=0.05)
    now = datetime.utcnow()
    det = TimeLagDetector(cfg, now_fn=lambda: now + timedelta(minutes=2))
    old = Market(id="t1", question="Will BTC hit 90k?", outcomes=[Outcome(id="y", label="Yes", price=0.4)])
    det.history["t1"] = (0.3, now)
    # peer stale
    det.history["t2"] = (0.5, now)
    m_new = Market(id="t1", question="Will BTC hit 90k?", outcomes=[Outcome(id="y", label="Yes", price=0.42)])
    m_peer = Market(id="t2", question="Will BTC hit 90k?", outcomes=[Outcome(id="y", label="Yes", price=0.5)])
    opps = det.detect([m_new, m_peer])
    assert any(o.type == "TIMELAG" for o in opps)


def test_consistency_detector(markets):
    opps = ConsistencyDetector(DetectorConfig(exclusive_sum_tolerance=0.01)).detect(markets)
    assert any(o.type == "CONSISTENCY" for o in opps)
