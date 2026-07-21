import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tb"))


def pytest_addoption(parser):
    parser.addoption("--model", default=None)
    parser.addoption("--model-out", default=None)
    parser.addoption("--model-path", default=None)
    parser.addoption("--placement-strategy", default=None)
    parser.addoption("--partition-strategy", default=None)
    parser.addoption("--test-vecs", default=None)
    parser.addoption("--cache-files", default=None)
    parser.addoption("--perf-file", default=None)
    parser.addoption("--num-trees", default=None)
    parser.addoption("--max-node", default=None)
    parser.addoption("--run-id", default=None)


def pytest_configure(config):
    import os

    # Only inject env vars if actually provided (not cocotb's internal re-parse)
    if config.getoption("--model") is not None:
        os.environ["BENCH_MODEL"] = config.getoption("--model")
        os.environ["BENCH_MODEL_OUT"] = config.getoption("--model-out")
        os.environ["BENCH_MODEL_PATH"] = config.getoption("--model-path")
        os.environ["BENCH_PLACEMENT_STRATEGY"] = config.getoption(
            "--placement-strategy"
        )
        os.environ["BENCH_PARTITION_STRATEGY"] = config.getoption(
            "--partition-strategy"
        )
        os.environ["BENCH_TEST_VECS"] = config.getoption("--test-vecs")
        os.environ["BENCH_CACHE_FILES"] = config.getoption("--cache-files")
        os.environ["BENCH_PERF_FILE"] = config.getoption("--perf-file")
        os.environ["BENCH_NUM_TREES"] = config.getoption("--num-trees")
        os.environ["BENCH_MAX_NODE"] = config.getoption("--max-node")
        os.environ["BENCH_RUN_ID"] = config.getoption("--run-id")
