# Test a forest with 2 tree cells

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Combine

from typing import Sequence
from test_cases import TestCase

import utils
from utils import fill_tree_cache, write_feature_word


class ForestDut:
    """
    Flattens dut.forest_top signals transparently.
    Top-level signals (clk, rst, etc.) are accessed from dut directly.
    Everything else is proxied to dut.forest_top.
    """

    # signals that live at the top level
    _TOP_LEVEL = {
        "clk",
        "rst",
        "enable",
        "busy",
        "ready",
        "prediction",
        "num_votes",
        "dbg_fault",
        "dbg_cycle",
    }

    def __init__(self, dut):
        object.__setattr__(self, "_dut", dut)
        print(f"AAAAAA dir: {dir(dut.test_forest)}")
        object.__setattr__(self, "_child", dut._sub_handles["test_forest"])

    def __getattr__(self, name):
        if name in self._TOP_LEVEL:
            return getattr(self._dut, name)
        return getattr(self._child, name)

    def __setattr__(self, name, value):
        if name in self._TOP_LEVEL:
            setattr(self._dut, name, value)
        else:
            setattr(self._child, name, value)


async def reset(dut):
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    dut.test_forest.enable.value = 0

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1

    await RisingEdge(dut.clk)


async def test_forest(dut, test_cases: Sequence[TestCase]):
    fdut = ForestDut(dut)

    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    for tc in test_cases:
        await reset(fdut)

        # Write forest to tree evaluator cells
        tasks = []
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            tasks.append(
                cocotb.start_soon(
                    fill_tree_cache(fdut, cell_idx, tc.hexfile, mem_range)
                )
            )
        await Combine(*tasks)

        # Write features to forest's caches, packed 2x16-bit per 32-bit word
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(fdut, word_idx, word)

        fdut.enable.value = 1

        await RisingEdge(fdut.clk)
        fdut.enable.value = 0

        cycle_count = 1
        completed = False

        while cycle_count <= tc.max_cycles:
            if fdut.ready.value:
                assert not fdut.busy.value

                winner, votes = tc.winning_vote()
                assert int(fdut.prediction.value) == winner
                assert int(fdut.num_votes.value) == votes

                completed = True
                break

            cycle_count += 1
            await RisingEdge(fdut.clk)

        if not completed:
            raise TimeoutError(f"{tc.hexfile}: timed out after {tc.max_cycles} cycles")

        print(f"{tc.hexfile}: Completed in {cycle_count} cycles.")


async def test_restart(dut, test_cases: Sequence[TestCase]):
    fdut = ForestDut(dut)

    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    fdut = dut.test_forest

    for tc in test_cases:
        await reset(dut)

        # Write forest to tree evaluator cells
        tasks = []
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            print(f"hex: {tc.hexfile}, range: {mem_range}")
            tasks.append(
                cocotb.start_soon(
                    fill_tree_cache(fdut, cell_idx, tc.hexfile, mem_range)
                )
            )
        await Combine(*tasks)

        # Write features to forest's caches, packed 2x16-bit per 32-bit word
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(fdut, word_idx, word)

        # Run 3 times to check if restarts work
        for _ in range(3):
            fdut.enable.value = 1

            await RisingEdge(fdut.clk)
            fdut.enable.value = 0
            await RisingEdge(fdut.clk)

            cycle_count = 1
            completed = False

            while cycle_count <= tc.max_cycles:
                if fdut.ready.value:
                    assert not fdut.busy.value

                    winner, votes = tc.winning_vote()
                    assert int(fdut.prediction.value) == winner
                    assert int(fdut.num_votes.value) == votes

                    completed = True
                    break

                cycle_count += 1
                await RisingEdge(fdut.clk)

            if not completed:
                raise TimeoutError(
                    f"{tc.hexfile}: timed out after {tc.max_cycles} cycles"
                )

            print(f"{tc.hexfile}: Completed in {cycle_count} cycles.")
