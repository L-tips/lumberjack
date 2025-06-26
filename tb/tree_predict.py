import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

TREE_MEM = """
// --- Node 0 ---
00000000 // left: prediction: class 0
00000001 // right: ptr: 1
0000000A // split: 0xA = 10
80000000 // left: true, right: false, split feat: 0 
// --- Node 1 ---
00000001 // left: prediction: class 1
00000002 // right: prediction: class 2
0000000A // split: 0xA = 10
c0000001 // left: true, right: true, split feat: 1
"""

def binary_to_hex(bin_str):
    # Convert binary string to hexadecimal
    hex_str = hex(int(str(bin_str), 2))[2:]
    hex_str = hex_str.zfill(8)
    return hex_str.upper()

@cocotb.coroutine
async def init_memory(mem, hexfile):
    offset = 0
    for raw_data in hexfile.splitlines() :
        str_data = raw_data.split("/")[0].strip()
        # Skip empty lines
        if str_data != "":
            print(str_data)
            data = int(str_data, 16)
            mem[offset].value = data
            offset += 1
    

@cocotb.test()
async def tree_test(dut):
   # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, units="ns").start())
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0
    # Always return "11" as the feature
    dut.feature_port.feature.value = 11
    await init_memory(dut.tree.tree_mem, TREE_MEM)

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
