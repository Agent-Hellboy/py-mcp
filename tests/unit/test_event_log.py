from pymcp.session.events import EventLog


def test_event_log_replay_after_sequence():
    log = EventLog(limit=10)
    log.record("stream-a:1", '{"one": true}')
    log.record("stream-a:2", '{"two": true}')
    log.record("stream-a:3", '{"three": true}')

    assert log.should_resume("stream-a:1") == ("stream-a", 1)
    replay = log.replay("stream-a", after_seq=1)
    assert replay == [("stream-a:2", '{"two": true}'), ("stream-a:3", '{"three": true}')]


def test_event_log_resume_unknown_stream_returns_none():
    log = EventLog(limit=10)
    assert log.should_resume("missing:1") == (None, None)


def test_event_log_next_event_id_increments_per_stream():
    log = EventLog(limit=10)
    assert log.next_event_id("stream-b") == "stream-b:1"
    assert log.next_event_id("stream-b") == "stream-b:2"
