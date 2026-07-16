import os
from pathlib import Path

import csv
from dataclasses import dataclass

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, First
from accel_driver import Driver, Model, ModelCache  # pyright: ignore[reportMissingImports]
from wb_driver import WbMaster  # pyright: ignore[reportMissingImports]
from perf_monitor import PerfMonitor

TOP = "lumberjack_Benchmark"
MODULE = "benchmark"

CLK_PERIOD_NS = 1

CACHE_FILES = os.environ["BENCH_CACHE_FILES"].split(",")
USED_CELLS = len(CACHE_FILES)
PERF_OUT = os.environ["BENCH_PERF_FILE"]
TEST_VEC_FILE = os.environ["BENCH_TEST_VECS"]
MODEL_NAME = os.environ["BENCH_MODEL"]
MODEL_PATH = os.environ["BENCH_MODEL_PATH"]
PLACEMENT_STRATEGY = os.environ["BENCH_PLACEMENT_STRATEGY"]
PARTITION_STRATEGY = os.environ["BENCH_PARTITION_STRATEGY"]


@dataclass
class TestVector:
    features: list[float]
    expected_prediction: int
    expected_num_votes: int


def load_test_vectors(path: str) -> list[TestVector]:
    vectors = []
    with open(path, newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            prediction = int(row.pop("prediction"))
            num_votes = int(row.pop("num_votes"))
            features = [float(v) for v in row.values()]
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
        await First(RisingEdge(dut.forest_top.ready), RisingEdge(dut.forest_top.error))

        assert not dut.forest_top.error.value, "Unexpected evaluation error"

        pred = await driver.prediction()
        pred_num_votes = await driver.num_votes()
        assert pred == vec.expected_prediction, (
            f"Wrong prediction at feature {i}! Got: {pred}, expected: {vec.expected_prediction}"
        )
        assert pred == vec.expected_prediction, (
            f"Wrong number of votes at feature {i}! Got: {pred_num_votes}, expected: {vec.expected_num_votes}"
        )

    SUPERSCALAR_EXECUTION = bool(dut.forest_top.USE_SUPERSCALAR.value)
    VOTE_FIFO_DEPTH = int(dut.forest_top.VOTE_FIFO_DEPTH.value)
    extra_data = {
        "used_cells": USED_CELLS,
        "model_path": MODEL_PATH,
        "test_vecs": TEST_VEC_FILE,
        "placement_strategy": PLACEMENT_STRATEGY,
        "partition_strategy": PARTITION_STRATEGY,
        "superscalar_execution": SUPERSCALAR_EXECUTION,
        "vote_fifo_depth": VOTE_FIFO_DEPTH,
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
    "forest/cell_driver.sv",
    "forest/vote_fifo.sv",
    "forest/forest.sv",
    "forest/ram_counter.sv",
    "forest/types.sv",
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

    runner = get_runner(sim)
    runner.build(
        sources=sources,
        hdl_toplevel=TOP,
        waves=True,
        build_args=[
            "--trace",
            "--trace-fst",
            "--trace-structs",
        ],
        always=True,
    )
    runner.test(hdl_toplevel=TOP, test_module=MODULE)
