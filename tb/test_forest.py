# Test a forest with 2 tree cells

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

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

async def fill_tree_cache(dut, mem_width, tree_idx, mem_file, rng):
    mem_data = read_hex(mem_file)
    mem_data = utils.into_chunks_le(mem_data, mem_width)

    if mem_width == 128:
        bwe = 0xffff
    elif mem_width == 64:
        bwe = 0xff
    else:
        raise ValueError("Memory bus width should be either 64 or 128 bits.")

    port = dut.forest.tree_ram_ports[tree_idx]

    port.enable.value = True
    port.byte_write_enable.value = bwe

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

async def test_forest(dut, mem_width, test_cases):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for file, cache_mem_ranges in test_cases:
        await reset(dut)

        # Write forest to tree evaluator cells
        for cell_idx, mem_range in enumerate(cache_mem_ranges):
            await fill_tree_cache(dut, mem_width, cell_idx, file, mem_range)

        # Write features to forest's caches
        features = [0x4110, 0x4130, 0x4110]
        for i, feat in enumerate(features):
            await write_feature(dut, i, feat)

        dut.enable.value = 1
        dut.num_trees.value = 2
        dut.num_features.value = 3

        await RisingEdge(dut.clk)
        
        dut.enable.value = 0

        cycle_count = 1
        while not dut.ready.value == 1:
            cycle_count += 1
            await RisingEdge(dut.clk)

            if dut.error.value:
                raise Exception("Forest returned error, expected ready")

        # Forest should predict class #1 with 2 votes
        assert dut.prediction.value == 1
        assert dut.num_votes.value == 2

        dut.enable.value = 0
        await RisingEdge(dut.clk)

        print(f"{file}: Prediction took {cycle_count} cycles.")
