import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

def assert_ack(dut, index):
    assert (dut.ack.value.to_unsigned() & 0b1 << index) >> index == 1


@cocotb.test()
async def arbiter_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    await RisingEdge(dut.clk)

    dut.rst.value = 1

    await RisingEdge(dut.clk)

    dut.valid.value = 0xffff_ffff
    dut.classes.value = list(range(0, 32))
    
    for i in range(0, 32):
        await RisingEdge(dut.clk)
        assert_ack(dut, i)
        assert dut.increment_addr.value == i

