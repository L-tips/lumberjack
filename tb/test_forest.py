import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils

@cocotb.test()
async def forest_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    
    await utils.init_memory(dut.ram.ram.mem, "forest_2_trees_6_nodes.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset

    await RisingEdge(dut.clk)

    dut.enable.value = 1
    dut.forest_start_addr.value = 0
    dut.num_trees.value = 2

    dut.features_start_addr = 0x60
    dut.num_features.value = 3

    await RisingEdge(dut.clk)

    cycle_count = 1

    while not dut.ready.value == 1:
        cycle_count += 1
        await RisingEdge(dut.clk)

    # Forest should predict class #1 with 2 votes
    assert dut.prediction.value == 1
    assert dut.num_votes.value == 2

    dut.enable.value = 0
    await RisingEdge(dut.clk)

    print(f"Prediction took {cycle_count} cycles.")