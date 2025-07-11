import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

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

    # Insert features in the feat vector, must be done after reset
    dut.forest.feature_registers.registers.value = [
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

    for _ in range(0,100):
        await RisingEdge(dut.clk)