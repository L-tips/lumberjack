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

    # Always return "11" as the feature
    dut.feature_port.data.value = 11

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1

    await RisingEdge(dut.clk)

    # Initialize memory
    await utils.init_memory(dut.ram.ram.mem, "single_tree_2_nodes.hex")

    await RisingEdge(dut.clk)

    # ...and start tree prediction
    dut.start.value = 1
    dut.first_node_addr.value = 0

    await RisingEdge(dut.clk)

    dut.start.value = 0
    assert dut.tree.busy.value == 1

    # Takes 4 cycles to fetch the full node
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.tree.state.value == 1
    assert dut.tree.fetch_counter.value == 3

    # Plus another cycle to evaluate the node
    await RisingEdge(dut.clk)

    assert dut.tree.state.value == 2
    # We're taking the right branch, which is
    # a node pointer
    assert dut.tree.next_node_ptr.value == 0x10
    # Which means we're going to be evaluating
    # another node
    assert dut.tree.next_ready.value == 0
    assert dut.tree.next_busy.value == 1

    # Now we're fetching the next node
    await RisingEdge(dut.clk)

    assert dut.tree.state.value == 1
    assert dut.tree.fetch_counter.value == 0

    # Again, takes a total of 5 cycles to evaluate
    # the node (4 fetch + 1 execute)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.tree.state.value == 2
    assert dut.tree.busy.value == 1
    assert dut.tree.ready.value == 0

    await RisingEdge(dut.clk)

    # Result should now be available
    assert dut.ready.value == 1
    assert dut.busy.value == 0
    # According to the tree and the input
    # feature, predicted class should
    # be 2
    assert dut.prediction == 2

    # Make sure the mem bus is released
    assert dut.ram_bus.cyc == 0
    assert dut.ram_bus.stb == 0

    # Now let's try to take another branch.
    # Always return 6 as the input feature
    dut.feature_port.data.value = 6
    dut.start.value = 1

    await RisingEdge(dut.clk)

    dut.start.value = 0

    # The first node is directly a prediction.
    # Entire prediction sequence should complete
    # in a total of 6 cycles after START has been
    # set.
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.ready.value == 1
    assert dut.busy.value == 0
    # Predicted class should be 0
    assert dut.prediction == 0

    # Let's test the behavior when
    # we stall the bus.
    dut.start.value = 1
    await RisingEdge(dut.clk)

    dut.start.value = 0
    dut.ram_bus.stall.value = 1

    await RisingEdge(dut.clk)

    # State should not change...
    assert dut.tree.fetch_counter.value == 0
    assert dut.tree.state.value == 1

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.tree.fetch_counter.value == 0
    assert dut.tree.state.value == 1
    
    # ...until we release STALL
    dut.ram_bus.stall.value = 0

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.tree.fetch_counter.value == 1
    assert dut.tree.state.value == 1

    # Let's wait for the prediction to complete
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.ready.value == 1
    assert dut.busy.value == 0
    assert dut.prediction.value == 0

    # Intentionally don't reset start to 0.
    # Prediction should never show ready.

    dut.start.value = 1
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    # Even though the state is idle,
    assert dut.tree.state.value == 0
    # the status still isn't ready
    assert dut.ready.value == 0
    assert dut.busy.value == 1

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
