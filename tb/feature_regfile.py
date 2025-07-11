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
    
    await RisingEdge(dut.clk)

    dut.rst.value = 1

    await RisingEdge(dut.clk)

    dut.write_enable.value = 1
    dut.write_data.value = 0xDEADBEEF
    dut.write_address.value = 0x0
    dut.feature_port.address.value = 0x0

    await RisingEdge(dut.clk)
    
    dut.write_enable.value = 0

    await RisingEdge(dut.clk)

    assert dut.feature_port.feature.value == 0xDEADBEEF