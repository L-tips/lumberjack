import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "tb"))


def pytest_addoption(parser):
    parser.addoption("--model", required=True)
    parser.addoption("--model-out", required=True)
    parser.addoption("--test-vecs", required=True)
    parser.addoption("--cache-files", required=True)
    parser.addoption("--num-cells", type=int, required=True)


def pytest_configure(config):
    import os

    os.environ["BENCH_MODEL"] = config.getoption("--model")
    os.environ["BENCH_MODEL_OUT"] = config.getoption("--model-out")
    os.environ["BENCH_TEST_VECS"] = config.getoption("--test-vecs")
    os.environ["BENCH_CACHE_FILES"] = config.getoption("--cache-files")
    os.environ["BENCH_NUM_CELLS"] = str(config.getoption("--num-cells"))
