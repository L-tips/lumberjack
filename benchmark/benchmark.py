import os
from pathlib import Path

import csv
from dataclasses import dataclass

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge
from accel_driver import Driver, Model, ModelCache  # pyright: ignore[reportMissingImports]
from wb_driver import WbMaster  # pyright: ignore[reportMissingImports]
from perf_monitor import PerfMonitor
import ml_dtypes
import numpy as np

TOP = "lumberjack_Benchmark"
MODULE = "benchmark"

CLK_PERIOD_NS = 1


def parse_yaml_bool(s: str) -> bool:
    import yaml

    result = yaml.safe_load(s)
    if not isinstance(result, bool):
        raise ValueError(f"Cannot parse {s!r} as a boolean")
    return result


BENCH_NAME = os.environ["BENCH_NAME"]
CACHE_FILES = os.environ["BENCH_CACHE_FILES"].split(",")
NUM_CELLS = len(CACHE_FILES)
PERF_OUT = os.environ["BENCH_PERF_FILE"]
TEST_VEC_FILE = os.environ["BENCH_TEST_VECS"]
MODEL_NAME = os.environ["BENCH_MODEL_NAME"]
MODEL_PATH = os.environ["BENCH_MODEL_PATH"]
PLACEMENT_STRATEGY = os.environ["BENCH_PLACEMENT_STRATEGY"]
PARTITION_STRATEGY = os.environ["BENCH_PARTITION_STRATEGY"]
NUM_TREES = int(os.environ["BENCH_NUM_TREES"])
MAX_NODE = int(os.environ["BENCH_MAX_NODE"])
RUN_ID = os.environ["BENCH_RUN_ID"]
VOTE_FIFO_DEPTH = int(os.environ["BENCH_VOTE_FIFO_DEPTH"])
USE_SUPERSCALAR = parse_yaml_bool(os.environ["BENCH_USE_SUPERSCALAR"])


@dataclass
class TestVector:
    features: list[any]
    expected_prediction: int
    expected_num_votes: int


def load_test_vectors(path: str) -> list[TestVector]:
    vectors = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prediction = int(row.pop("prediction"))
            num_votes = int(row.pop("num_votes"))
            features = features = [
                np.uint16(int(v, 16)).view(ml_dtypes.bfloat16) for v in row.values()
            ]
            vectors.append(
                TestVector(
                    features=features,
                    expected_prediction=prediction,
                    expected_num_votes=num_votes,
                )
            )
    return vectors


@cocotb.test()
async def perf_benchmark(dut):
    # Clock
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    # Wire up buses
    csr_bus = WbMaster(dut.clk, dut.control_bus)
    cell_cache_ports = list(
        map(lambda bus: WbMaster(dut.clk, bus), dut.cell_cache_ports)
    )

    cache_data = [ModelCache(f"../{f}") for f in CACHE_FILES]
    model = Model(cache_data)

    monitor = PerfMonitor(clk=dut.clk, dut=dut.forest_top)
    monitor.start()
    driver = Driver(dut.clk, csr_bus, cell_cache_ports)

    await driver.reset(dut.rst, cycles=1)
    await driver.write_caches(model)

    test_vectors = load_test_vectors(f"../{TEST_VEC_FILE}")

    for i, vec in enumerate(test_vectors):
        await driver.start(vec.features)
        await RisingEdge(dut.forest_top.ready)

        pred = await driver.prediction()
        pred_num_votes = await driver.num_votes()
        assert pred == vec.expected_prediction, (
            f"Wrong prediction at feature {i}! Got: {pred}, expected: {vec.expected_prediction}. Features: {vec.features}"
        )
        assert pred_num_votes == vec.expected_num_votes, (
            f"Wrong number of votes at feature {i}! Got: {pred_num_votes}, expected: {vec.expected_num_votes}. Features: {vec.features}"
        )

    NUM_TEST_VECTORS = len(test_vectors)
    extra_data = {
        "bench_name": BENCH_NAME,
        "model_name": MODEL_NAME,
        "run_id": RUN_ID,
        "num_cells": NUM_CELLS,
        "model_path": MODEL_PATH,
        "test_vecs": TEST_VEC_FILE,
        "num_test_vectors": NUM_TEST_VECTORS,
        "placement_strategy": PLACEMENT_STRATEGY,
        "partition_strategy": PARTITION_STRATEGY,
        "superscalar_execution": USE_SUPERSCALAR,
        "vote_fifo_depth": VOTE_FIFO_DEPTH,
        "num_trees": NUM_TREES,
        "maxnode": MAX_NODE,
    }

    await monitor.stop(report_path=Path(PERF_OUT), extra_data=extra_data)


VERYL_SOURCES = [
    "benchmark.sv",
    "csr.sv",
    "csr_types.sv",
    "forest_top.sv",
    "forest_top_std.sv",
    "ram2wb.sv",
    "self_arbiter.sv",
    "types.sv",
    "common/test_layout.sv",
    "forest/cell_controller.sv",
    "forest/forest.sv",
    "forest/votes_counter.sv",
    "forest/votes_arbiter.sv",
    "tree/bram_demux.sv",
    "tree/float_leq.sv",
    "tree/node_evaluator.sv",
    "tree/tree_cell.sv",
    "ibex_bus/ibex_bus.sv",
    "ibex_bus/wb2ibex_bus.sv",
    "test_forest_top.sv",
]

DEPENDENCY_SOURCES = [
    "memutils/src/bram/bram_bus.sv",
    "memutils/src/bram/dp_bram.sv",
    "memutils/src/bram/sp_bram.sv",
    "memutils/src/scratchpad_ram.sv",
    "memutils/src/wb/ram2wb.sv",
    "memutils/src/wb/wb_demux.sv",
    "memutils/src/wb/wb_dp_ram.sv",
    "memutils/src/wb/wb_mux.sv",
    "memutils/src/wb/wb_ram.sv",
    "memutils/src/wb/wishbone_if.sv",
    "std/edge_detector/edge_detector.sv",
    "std/fifo/fifo.sv",
    "std/fifo/fifo_controller.sv",
    "std/ram/ram.sv",
]


def test_run_benchmark():
    from cocotb_tools.runner import get_runner

    sim = os.getenv("SIM", "verilator")
    repo_root = Path(__file__).resolve().parent.parent
    veryl_out = repo_root / "target" / "veryl"
    deps = repo_root / "dependencies"

    sources = [veryl_out / s for s in VERYL_SOURCES] + [
        deps / s for s in DEPENDENCY_SOURCES
    ]

    print(f"superscalar bit: {int(USE_SUPERSCALAR)}, {USE_SUPERSCALAR}")

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=TOP,
        waves=True,
        build_args=[
            "--trace",
            "--trace-fst",
            "--trace-structs",
            "../../verilator_config.vlt",
            f"-GCELL_INSTANCES={NUM_CELLS}",
            f"-GVOTE_FIFO_DEPTH={VOTE_FIFO_DEPTH}",
            f"-GUSE_SUPERSCALAR={int(USE_SUPERSCALAR)}",
        ],
        always=True,
    )
    runner.test(hdl_toplevel=TOP, test_module=MODULE)
