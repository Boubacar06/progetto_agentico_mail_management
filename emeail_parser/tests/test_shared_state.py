from email_agents.shared_state import SharedState

def test_shared_state_log():
    s = SharedState(raw_email="x")
    s.log("tester", "action", foo=1)
    assert len(s.history) == 1
    assert s.history[0].agent == "tester"
