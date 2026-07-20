# Test a forest with 2 tree cells

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Combine

from typing import Sequence
from test_cases import TestCase

import utils
from utils import fill_tree_cache, write_feature_word


async def reset(dut):
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    dut.enable.value = 0

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1

    await RisingEdge(dut.clk)


async def test_forest(dut, test_cases: Sequence[TestCase]):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for tc in test_cases:
        await reset(dut)

        # Write forest to tree evaluator cells
        tasks = []
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            tasks.append(
                cocotb.start_soon(fill_tree_cache(dut, cell_idx, tc.hexfile, mem_range))
            )
        await Combine(*tasks)

        # Write features to forest's caches, packed 2x16-bit per 32-bit word
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(dut, word_idx, word)

        dut.enable.value = 1

        await RisingEdge(dut.clk)
        dut.enable.value = 0

        cycle_count = 1
        completed = False

        while cycle_count <= tc.max_cycles:
            if dut.ready.value:
                assert not dut.busy.value

                winner, votes = tc.winning_vote()
                assert int(dut.prediction.value) == winner
                assert int(dut.num_votes.value) == votes

                completed = True
                break

            cycle_count += 1
            await RisingEdge(dut.clk)

        if not completed:
            raise TimeoutError(f"{tc.hexfile}: timed out after {tc.max_cycles} cycles")

        print(f"{tc.hexfile}: Completed in {cycle_count} cycles.")


async def test_restart(dut, test_cases: Sequence[TestCase]):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for tc in test_cases:
        await reset(dut)

        # Write forest to tree evaluator cells
        tasks = []
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            print(f"hex: {tc.hexfile}, range: {mem_range}")
            tasks.append(
                cocotb.start_soon(fill_tree_cache(dut, cell_idx, tc.hexfile, mem_range))
            )
        await Combine(*tasks)

        # Write features to forest's caches, packed 2x16-bit per 32-bit word
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(dut, word_idx, word)

        # Run 3 times to check if restarts work
        for _ in range(3):
            dut.enable.value = 1

            await RisingEdge(dut.clk)
            dut.enable.value = 0
            await RisingEdge(dut.clk)

            cycle_count = 1
            completed = False

            while cycle_count <= tc.max_cycles:
                if dut.ready.value:
                    assert not dut.busy.value

                    winner, votes = tc.winning_vote()
                    assert int(dut.prediction.value) == winner
                    assert int(dut.num_votes.value) == votes

                    completed = True
                    break

                cycle_count += 1
                await RisingEdge(dut.clk)

            if not completed:
                raise TimeoutError(
                    f"{tc.hexfile}: timed out after {tc.max_cycles} cycles"
                )

            print(f"{tc.hexfile}: Completed in {cycle_count} cycles.")
