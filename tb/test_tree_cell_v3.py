import cocotb
from cocotb.clock import Clock
from cocotb.triggers import Combine, RisingEdge

import utils
from utils import fill_tree_cache, write_feature_word
from test_cases import TestCase, get_winner

from collections import Counter


class CellModel:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk

    async def reset(self):
        await RisingEdge(self.clk)

        # Init and reset
        self.dut.rst.value = 0

        self.dut.start.value = 0
        self.dut.restart.value = 0
        self.dut.pred_ack.value = 0

        await RisingEdge(self.clk)
        # Release reset
        self.dut.rst.value = 1

        await RisingEdge(self.clk)

    async def init_mem(self, tc: TestCase):
        await fill_tree_cache(self.dut, 0, tc.hexfile, tc.cache_mem_ranges[0])

    async def start(self):
        """Send a start strobe"""
        self.dut.start.value = True
        await RisingEdge(self.clk)
        self.dut.start.value = False
        await RisingEdge(self.clk)

    async def send_ack(self):
        """ACK a prediction"""
        self.dut.pred_ack.value = True
        await RisingEdge(self.clk)
        self.dut.pred_ack.value = False
        await RisingEdge(self.clk)

    async def restart(self, num_trees_in_cell):
        """Send start+restart strobes"""
        self.dut.start.value = True
        self.dut.restart.value = True
        await RisingEdge(self.clk)

        self.dut.start.value = False
        self.dut.restart.value = False
        await RisingEdge(self.clk)
        assert int(self.dut.num_trees_in_cell.value) == num_trees_in_cell


async def test_cell(dut, cases):

    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    model = CellModel(dut)

    for tc in cases:
        await model.reset()
        await model.init_mem(tc)

        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(dut, word_idx, word)

        predictions = Counter()

        # Start model and wait for valid prediction
        await model.restart(tc.num_trees)

        for tree_id in range(0, tc.num_trees):
            if not dut.pred_valid.value:
                await RisingEdge(dut.pred_valid)

            predictions[int(dut.prediction.value)] += 1

            if tree_id < tc.num_trees - 1:
                # Ack it and immediately restart
                await Combine(
                    cocotb.start_soon(model.send_ack()),
                    cocotb.start_soon(model.start()),
                )
            else:
                await model.send_ack()

        winner, votes = get_winner(predictions)

        print(f"winner: {winner}, votes: {votes}")
        print(f"expected winner: {tc.expected_prediction}, votes: {tc.expected_votes}")
        print(predictions)

        assert winner == tc.expected_prediction
        assert votes == tc.expected_votes
