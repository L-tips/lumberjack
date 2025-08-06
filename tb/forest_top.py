import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils

FOREST_START_ADDR = 0x10064
FEATURES_START_ADDR = 0x100C4


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


def debug_mark(dut, value):
    dut.dbg_mark.value = value


@cocotb.test()
async def forest_top_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    debug_mark(dut, 0)

    await utils.init_memory(dut.ram.ram.mem, "forest_2_trees_6_nodes.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset

    # Set num_trees
    begin_write(dut, 0xC, 2, 0b1111)

    await RisingEdge(dut.clk)

    # Set first_node
    begin_write(dut, 0x10, FOREST_START_ADDR, 0b1111)

    await RisingEdge(dut.clk)

    # Check that first_node reads on
    begin_read(dut, 0x10, 0b1111)

    await RisingEdge(dut.clk)

    # Set num_features
    begin_write(dut, 0x14, 3, 0b1111)

    await RisingEdge(dut.clk)

    assert read_data(dut) == FOREST_START_ADDR
    assert dut.forest.forest_start_addr.value == FOREST_START_ADDR

    # Set first_feature
    begin_write(dut, 0x18, FEATURES_START_ADDR, 0b1111)

    await RisingEdge(dut.clk)

    begin_read(dut, 0x18, 0b1111)

    await RisingEdge(dut.clk)

    # Enable
    begin_write(dut, 0x0, 0x1, 0b1)

    await RisingEdge(dut.clk)

    assert read_data(dut) == FEATURES_START_ADDR
    assert dut.forest.features_start_addr.value == FEATURES_START_ADDR

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
    assert dut.forest.features_start_addr.value == FEATURES_START_ADDR
    assert dut.forest.forest_start_addr.value == FOREST_START_ADDR
    assert dut.forest.num_trees.value == 2

    # BUSY and ENABLE should be set
    assert read_data(dut) == 0b11

    # Check that features_start_addr is actually enable-protected
    begin_write(dut, 0x18, 0x00, 0b1111)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)

    # Check that first_feature hasn't changed (enable protection works)
    assert dut.forest.features_start_addr.value == FEATURES_START_ADDR

    # Enable the interrupt
    begin_write(dut, 0x24, 0b01, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    await utils.wait_with_timeout(dut.clk, dut.forest.ready, 1, 50)

    await RisingEdge(dut.clk)

    # Forest should predict class #1 with 2 votes
    assert dut.forest.prediction.value == 1
    assert dut.forest.num_votes.value == 2

    # Interrupt line should be set
    assert dut.interrupt_line.value == 1

    # Clear the interrupt by reading prediction
    begin_read(dut, 0x1C, 0b1111)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    assert dut.interrupt_line.value == 1

    await RisingEdge(dut.clk)

    # Also make sure that reading the prediction works
    # correctly by the same occasion
    prediction = read_data(dut)

    assert prediction == 1

    # Interrupt should now be inactive
    assert dut.interrupt_line.value == 0
    # Also read the number of votes
    begin_read(dut, 0x20, 0b1111)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    num_votes = read_data(dut)
    assert num_votes == 2

    await RisingEdge(dut.clk)

    # Restart a second time
    begin_write(dut, 0x0, 0x1, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    await utils.wait_with_timeout(dut.clk, dut.forest.ready, 1, 50)

    await RisingEdge(dut.clk)

    assert dut.interrupt_line == 1

    # Clear the interrupt by writing a 1 to INTFLAG
    begin_write(dut, 0x2C, 0b01, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    assert dut.interrupt_line == 1

    await RisingEdge(dut.clk)

    assert dut.interrupt_line == 0

    # Disable the interrupt
    begin_write(dut, 0x28, 0b01, 0b1)

    await RisingEdge(dut.clk)

    # Restart for a 3rd time
    begin_write(dut, 0x0, 0x1, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    await utils.wait_with_timeout(dut.clk, dut.forest.ready, 1, 50)

    # Interrupt should not fire
    assert dut.interrupt_line == 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Check that the control/status signals
    # are what we expect, and that the HW hasn't
    # unexpectedly changed them from under our noses
    assert dut.forest.busy.value == 0
    assert dut.forest.ready.value == 1
    assert dut.forest.enable.value == 0


@cocotb.test()
async def rejects_circular_forests(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    debug_mark(dut, 0)

    await utils.init_memory(dut.ram.ram.mem, "forest_1_tree_2_nodes_circular.hex")

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset

    # Set num_trees
    begin_write(dut, 0xC, 1, 0b1111)

    await RisingEdge(dut.clk)

    # Set first_node
    begin_write(dut, 0x10, FOREST_START_ADDR, 0b1111)

    await RisingEdge(dut.clk)

    # Set num_features
    begin_write(dut, 0x14, 1, 0b1111)

    await RisingEdge(dut.clk)

    # Set first_feature
    begin_write(dut, 0x18, 0x10084, 0b1111)

    await RisingEdge(dut.clk)

    # Enable
    begin_write(dut, 0x0, 0x1, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)

    # Enable the ERROR interrupt, but not the READY bit
    begin_write(dut, 0x24, 0b10, 0b1)

    await RisingEdge(dut.clk)

    finish_txn(dut)

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    await utils.wait_with_timeout(dut.clk, dut.forest.error, 1, 50)

    await RisingEdge(dut.clk)
    # Interrupt should fire
    assert dut.interrupt_line == 1

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Check that the interrupt is still on
    # a few cycles later
    assert dut.interrupt_line == 1
