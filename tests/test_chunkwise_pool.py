from specview.chunkwise_compute import ProcessingPoolManager, RangeComputedCallback

import time

def add5(x):
    print (f"Adding 5 to {x}")
    return x+5


def test_chunkwise_pool_basics():
    ppm = ProcessingPoolManager.get_instance()
    assert ppm is not None

    pool = ppm.get_pool()

    results = []
    def handle_result_cb(res):
        print(f"Got result: {res}")
        results.append(res)

    pool.map_async(add5, (10,11,12,13,100), callback=handle_result_cb, error_callback=lambda e: print(f"Error in pool: {e}")).get()

    assert results == [[15,16,17,18,105]]
    del pool
    ppm.close() # Call close() on the ProcessingPoolManager, not on the pool itself, since the pool is managed by the manager

def test_chunkwise_pool_can_restart():
    ppm = ProcessingPoolManager.get_instance()
    assert ppm is not None

    pool = ppm.get_pool()

    results = []
    def handle_result_cb(res):
        print(f"Got result: {res}")
        results.append(res)

    pool.map_async(add5, (10,11,12,13,100), callback=handle_result_cb, error_callback=lambda e: print(f"Error in pool: {e}")).get()
    assert results == [[15,16,17,18,105]]
    del pool
    ppm.close()

    # Restart the pool and run another job
    pool = ppm.get_pool()
    results.clear()
    pool.map_async(add5, (20,21), callback=handle_result_cb, error_callback=lambda e: print(f"Error in pool: {e}")).get()
    del pool
    assert results == [[25,26]]
    ppm.close()

