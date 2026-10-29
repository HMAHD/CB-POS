def test_throwaway_ci_failure():
    assert 1 == 2, "Deliberate failure to verify CI turns red on failure"
