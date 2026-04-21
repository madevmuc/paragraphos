from core.workers import WorkerPool


def test_submit_and_gather():
    pool = WorkerPool(max_workers=2)
    futures = [pool.submit(lambda x=i: x * 2) for i in range(4)]
    results = sorted(pool.gather(futures))
    assert results == [0, 2, 4, 6]
    pool.shutdown()


def test_shutdown_waits_clean():
    pool = WorkerPool(max_workers=1)
    f = pool.submit(lambda: 42)
    pool.shutdown(wait=True)
    assert f.result() == 42
