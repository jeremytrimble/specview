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
    pool.close()

