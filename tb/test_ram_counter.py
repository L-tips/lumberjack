import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


@cocotb.test()
async def ram_counter_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    await RisingEdge(dut.clk)

    dut.rst.value = 1

    await RisingEdge(dut.clk)

    address = 4

    dut.read_address.value = address
    dut.inc_address.value = address
    dut.inc_en.value = 1

    await Timer(1, unit="ns")

    assert dut.read_data.value == 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    assert dut.read_data.value == 1

    await RisingEdge(dut.clk)
    assert dut.read_data.value == 2

    dut.read_address.value = 0

    await Timer(1, unit="ns")

    assert dut.read_data.value == 0

