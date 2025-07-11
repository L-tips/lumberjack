import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils

@cocotb.test()
async def tree_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    
    await utils.init_memory(dut.ram.mem, "forest_2_trees_6_nodes.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset

    # Insert features in the scratchpad, must be done after reset
    dut.forest.features.mem.value = [
        9,
        11,
        9,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
        11,
    ]

    await RisingEdge(dut.clk)

    dut.en.value = 1
    dut.first_node_addr.value = 0
    dut.num_trees.value = 2

    await RisingEdge(dut.clk)

    dut.en.value = 0

    cycle_count = 1

    while not dut.ready.value == 1:
        cycle_count += 1
        await RisingEdge(dut.clk)

    print(f"Prediction took {cycle_count} cycles.")