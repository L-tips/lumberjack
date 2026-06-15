# Test a forest with 2 tree cells

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

from typing import Sequence
from test_cases import TestCase

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
    port = dut.cell_cache_ports[tree_idx]
    bus_width = len(port.write_data)

    if bus_width % 8 != 0:
        raise ValueError(f"Bus width must be byte-aligned, got {bus_width} bits.")

    bytes_per_word = bus_width // 8
    bwe = (1 << bytes_per_word) - 1

    if rng.start % bytes_per_word != 0 or rng.stop % bytes_per_word != 0:
        raise ValueError(
            f"Address range must be aligned to {bytes_per_word}-byte words "
            f"for a {bus_width}-bit bus."
        )

    start_word = rng.start // bytes_per_word
    end_word = rng.stop // bytes_per_word
    mem_words = utils.into_chunks_le(mem_data, bus_width)

    port.enable.value = True
    port.byte_write_enable.value = bwe

    for word_addr in range(start_word, end_word):
        port.address.value = word_addr - start_word
        port.write_data.value = mem_words[word_addr]
        await RisingEdge(dut.clk)

    port.enable.value = False
    port.write_data.value = 0
    port.byte_write_enable.value = 0

async def write_feature(dut, feature_idx, feature):
    dut.feature_write_bus.write_enable.value = True
    dut.feature_write_bus.address.value = feature_idx
    dut.feature_write_bus.data.value = feature

    await RisingEdge(dut.clk)

async def test_forest(dut, test_cases: Sequence[TestCase]):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for tc in test_cases:
        await reset(dut)

        # Write forest to tree evaluator cells
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            await fill_tree_cache(dut, cell_idx, tc.hexfile, mem_range)

        # Write features to forest's caches
        for i, feat in enumerate(tc.features):
            await write_feature(dut, i, feat)

        dut.enable.value = 1
        dut.num_trees.value = tc.num_trees
        dut.num_features.value = len(tc.features)

        await RisingEdge(dut.clk)
        dut.enable.value = 0

        cycle_count = 1
        completed = False

        while cycle_count <= tc.max_cycles:
            if dut.error.value:
                if tc.expect_error:
                    completed = True
                    break
                raise Exception("Forest returned error, expected ready")

            if dut.ready.value:
                if tc.expect_error:
                    raise Exception("Forest returned ready, expected error")

                assert int(dut.prediction.value) == tc.expected_prediction
                assert int(dut.num_votes.value) == tc.expected_votes
                completed = True
                break

            cycle_count += 1
            await RisingEdge(dut.clk)

        if not completed:
            raise TimeoutError(f"{tc.hexfile}: timed out after {tc.max_cycles} cycles")

        print(f"{tc.hexfile}: Completed in {cycle_count} cycles.")
