import os
from pathlib import Path
from cocotb_tools.runner import get_runner

import cocotb
from cocotb.clock import Clock
from accel_driver import Driver, Model, ModelCache
from wb_driver import WbMaster
from perf_monitor import PerfMonitor

TOP = "lumberjack_Benchmark"
MODULE = "benchmark"

CLK_PERIOD_NS = 1

NUM_CELLS = int(os.environ["BENCH_NUM_CELLS"])
CACHE_FILES = os.environ["BENCH_CACHE_FILES"].split(",")


@cocotb.test()
async def test_single_inference(dut):
    # Clock
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    # Wire up buses
    csr_bus = WbMaster(dut.clk, dut.control_bus)
    cell_cache_ports = list(
        map(lambda bus: WbMaster(dut.clk, bus), dut.cell_cache_ports)
    )

    cache_data = [ModelCache(f) for f in CACHE_FILES]
    model = Model(cache_data)

    monitor = PerfMonitor(clk=dut.clk, dut=dut.forest_top)
    monitor.start()
    driver = Driver(dut.clk, csr_bus, cell_cache_ports)

    await driver.reset(dut.rst, cycles=1)
    await driver.write_caches(model)

    features = [0.5, -1.2]
    await driver.enable_interrupt()
    await driver.start(features)

    # # Wait for result (choose one)
    await driver.wait_ready_irq(dut.interrupt_line)
    # # await driver.wait_ready_poll()

    assert not await driver.error(), "Accelerator flagged an error"

    pred = await driver.prediction()
    print(f"Prediction : {pred}")
    votes = await driver.num_votes()
    print(f"Votes      : {votes}")

    await monitor.stop(report_path=Path("perf.yml"))


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
