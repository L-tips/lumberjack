# Test a forest with 2 tree cells

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils
import utils
from utils import n_cycles, read_hex

async def reset(dut):
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    dut.enable.value = 0

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1

    await RisingEdge(dut.clk)

async def fill_tree_cache(dut, tree_idx, mem_file, rng):
    mem_data = read_hex(mem_file)
    mem_data = utils.into_64b_chunks_le(mem_data)

    port = dut.forest.tree_ram_ports[tree_idx]

    port.enable.value = True
    port.byte_write_enable.value = 0b11111111

    for addr in rng:
        port.address.value = addr - rng.start
        port.write_data.value = mem_data[addr]
        await RisingEdge(dut.clk)

    port.enable.value = False
    port.write_data.value = 0
    port.byte_write_enable.value = 0

async def write_feature(dut, feature_idx, feature):
    dut.feature_write_bus.write_enable.value = True
    dut.feature_write_bus.address.value = feature_idx
    dut.feature_write_bus.data.value = feature

    await RisingEdge(dut.clk)

@cocotb.test()
async def forest_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    
    await reset(dut)

    # Write forest to tree evaluator cells
    await fill_tree_cache(dut, 0, "forest_2_trees_6_nodes.hex", range(1,5))
    await fill_tree_cache(dut, 1, "forest_2_trees_6_nodes.hex", range(5,9))

    # Write features to forest's caches
    await write_feature(dut, 0, 0x4110)
    await write_feature(dut, 1, 0x4130)
    await write_feature(dut, 2, 0x4110)

    await RisingEdge(dut.clk)

    dut.enable.value = 1
    dut.num_trees.value = 2
    dut.num_features.value = 3

    await RisingEdge(dut.clk)
    
    dut.enable.value = 0

    cycle_count = 1

    while not dut.ready.value == 1:
        cycle_count += 1
        await RisingEdge(dut.clk)

    # Forest should predict class #1 with 2 votes
    assert dut.prediction.value == 1
    assert dut.num_votes.value == 2

    dut.enable.value = 0
    await RisingEdge(dut.clk)

    print(f"Prediction took {cycle_count} cycles.")
