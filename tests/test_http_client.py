from core import http


def test_singleton_client_is_reused():
    http.close_client()  # reset state at start
    c1 = http.get_client()
    c2 = http.get_client()
    assert c1 is c2


def test_close_client_clears_singleton():
    http.close_client()
    c1 = http.get_client()
    http.close_client()
    c2 = http.get_client()
    assert c1 is not c2
