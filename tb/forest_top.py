import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils

def begin_write(dut, address, data, byte_enable):
    dut.control_bus.cyc.value = 1
    dut.control_bus.stb.value = 1
    dut.control_bus.write_enable.value = 1
    dut.control_bus.select.value = byte_enable
    dut.control_bus.addr.value = address
    dut.control_bus.write_data.value = data

def begin_read(dut, address, byte_enable):
    dut.control_bus.cyc.value = 1
    dut.control_bus.stb.value = 1
    dut.control_bus.write_enable.value = 0
    dut.control_bus.select.value = byte_enable
    dut.control_bus.addr.value = address

def read_data(dut):
    assert dut.control_bus.ack.value == 1
    return dut.control_bus.read_data.value

def finish_txn(dut):
    dut.control_bus.cyc.value = 0
    dut.control_bus.stb.value = 0
    dut.control_bus.write_enable.value = 0
    dut.control_bus.select.value = 0
    dut.control_bus.addr.value = 0
    dut.control_bus.write_data.value = 0
    return dut.control_bus.read_data.value


@cocotb.test()
async def forest_top_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    
    await utils.init_memory(dut.ram.mem, "forest_2_trees_6_nodes.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset

    # Set num_trees
    begin_write(dut, 0xC, 2, 0b1111)

    await RisingEdge(dut.clk)

    # Set first_node
    begin_write(dut, 0x10, 0, 0b1111)

    await RisingEdge(dut.clk)

    # Set num_features
    begin_write(dut, 0x14, 3, 0b1111)

    await RisingEdge(dut.clk)

    # Set first_feature
    begin_write(dut, 0x18, 0x60, 0b1111)

    await RisingEdge(dut.clk)

    # Enable
    begin_write(dut, 0x0, 0x1, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)

    # Now read the status register while the evaluator
    # is working.
    begin_read(dut, 0x00, 0b1111)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)

    # Check that our writes have propagated correctly
    assert dut.forest.num_features.value == 3
    assert dut.forest.first_feature_addr.value == 0x60
    assert dut.forest.first_node_addr.value == 0x00
    assert dut.forest.num_trees.value == 2

    # BUSY and ENABLE should be set
    assert read_data(dut) == 0b101

    # Check that first_feature_addr is actually enable-protected
    begin_write(dut, 0x18, 0x00, 0b1111)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)

    # Check that first_feature hasn't changed (enable protection works)
    assert dut.forest.first_feature_addr.value == 0x60

    while not dut.forest.ready.value == 1:
        await RisingEdge(dut.clk)

    await RisingEdge(dut.clk)

    # Forest should predict class #1 with 2 votes
    assert dut.forest.prediction.value == 1
    assert dut.forest.num_votes.value == 2
