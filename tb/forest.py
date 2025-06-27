import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer

TREE_MEM = """
00000000 // left: prediction: class 0
00000001 // right: ptr: 1
0000000A // split: 0xA
80000000 // left: true, right: 0, split feat: 0 
00000001 // left: prediction: class 1
00000002 // right: prediction: class 2
0000000A // split: 0xA
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
    # Insert features in the feat vector
    dut.feature_registers.registers.value = [11,11]
    await init_memory(dut.tree_1.tree_mem, TREE_MEM)

    await RisingEdge(dut.clk)
    dut.rst.value = 1  # release reset
    await RisingEdge(dut.clk)
    
    await RisingEdge(dut.clk)
    print(binary_to_hex(dut.tree_1.node.value))
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)