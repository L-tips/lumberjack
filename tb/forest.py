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
    # Insert features in the feat vector
    dut.feature_registers.registers.value = [11,11]
    await utils.init_memory(dut.ram.mem, "forest_2_trees_6_nodes.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset
    await RisingEdge(dut.clk)
    
    await RisingEdge(dut.clk)
    print(utils.binary_to_hex(dut.tree_1.node.value))
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)