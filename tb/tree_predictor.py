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
    # Always return "11" as the feature
    dut.feature_port.feature.value = 11
    await utils.init_memory(dut.tree.tree_mem, "single_tree_2_nodes.hex")

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1
    # ...and start tree prediction
    dut.start.value = 1
    await RisingEdge(dut.clk)

    dut.start.value = 0

    # Here we are evaluating node 0
    assert dut.tree.node_ptr.value == 0
    assert dut.tree.ready.value == 0
    assert dut.tree.busy.value == 0

    await RisingEdge(dut.clk)

     # Right branch is taken
    assert dut.tree.node_ptr.value == 4
    assert dut.tree.ready.value == 0
    assert dut.tree.busy.value == 1

    await RisingEdge(dut.clk)

    # Prediction should be ready on the 2nd cycle and return 2
    assert dut.tree.ready.value == 1
    assert dut.tree.busy.value == 0
    assert dut.tree.prediction.value == 2

    # Now let's try to take another branch.
    # Always return "6" as the feature
    dut.feature_port.feature.value = 6
    dut.start.value = 1

    await RisingEdge(dut.clk)

    dut.start.value = 0

    await RisingEdge(dut.clk)

    # This time the left branch of node 0 is directly
    # a prediction. Should complete in 1 cycle
    # and prediction == 0
    assert dut.tree.ready.value == 1
    assert dut.tree.busy.value == 0
    assert dut.tree.prediction.value == 0

    dut.start.value = 1
    # Set the feature to at least take one branch
    # so that traversal takes > 1 cycle
    dut.feature_port.feature.value = 11

    await RisingEdge(dut.clk)

    # Intentionally trigger error by not resetting
    # start to 0. Prediction should still complete
    # with expected outcome

    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)

    assert dut.tree.ready.value == 1
    assert dut.tree.busy.value == 0
    assert dut.tree.prediction.value == 2
    assert dut.tree.error.value == 1
