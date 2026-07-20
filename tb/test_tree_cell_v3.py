import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer
from collections import Counter

import utils
from utils import fill_tree_cache, write_feature_word
from test_cases import TestCase

# Settle delay after each clock edge: lets NBA updates land before we read.
SETTLE_NS = 1
CLOCK_PERIOD = 10


class CellModel:
    def __init__(self, dut):
        self.dut = dut
        self.clk = dut.clk

    async def tick(self):
        """Advance exactly one cycle and settle. Outputs are readable after."""
        await RisingEdge(self.clk)
        await Timer(SETTLE_NS, unit="ns")

    async def reset(self):
        self.dut.rst.value = 0
        self.dut.start.value = 0
        self.dut.restart.value = 0
        self.dut.pred_ack.value = 0
        await self.tick()
        self.dut.rst.value = 1
        await self.tick()

    async def init_mem(self, tc: TestCase):
        await fill_tree_cache(self.dut, 0, tc.hexfile, tc.cache_mem_ranges[0])

    async def load_features(self, tc: TestCase):
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            await write_feature_word(self.dut, word_idx, word)

    # ---- control ---------------------------------------------------------
    def drive(self, start=False, restart=False, ack=False):
        """Set control inputs for the cycle about to be clocked in."""
        self.dut.start.value = 1 if start else 0
        self.dut.restart.value = 1 if restart else 0
        self.dut.pred_ack.value = 1 if ack else 0

    def idle(self):
        self.drive()

    async def strobe(self, start=False, restart=False, ack=False):
        """Drive a one-cycle strobe, clock it in, then deassert."""
        self.drive(start=start, restart=restart, ack=ack)
        await self.tick()
        self.idle()

    async def zero_fill_cache(self):
        # TODO: hardcoded
        FILL_DEPTH = 20
        port = self.dut.cell_cache_ports[0]

        for addr in range(FILL_DEPTH):
            port.address.value = addr
            port.write_data.value = 0
            port.byte_write_enable.value = -1  # all lanes
            port.enable.value = 1
            await RisingEdge(self.clk)
        port.enable.value = 0
        port.byte_write_enable.value = 0
        await RisingEdge(self.clk)

    # ---- observation -----------------------------------------------------
    @property
    def pred_valid(self):
        return bool(self.dut.pred_valid.value)

    @property
    def prediction(self):
        return int(self.dut.prediction.value)

    @property
    def busy(self):
        return bool(self.dut.busy.value)

    @property
    def num_trees(self):
        return int(self.dut.num_trees_in_cell.value)

    async def await_valid(self, timeout=1000):
        """Advance until pred_valid is high. Returns cycles waited.

        Leaves the sim settled just after an edge, so the caller may read
        outputs and/or drive immediately.
        """
        for n in range(timeout):
            if self.pred_valid:
                return n
            await self.tick()
        raise TimeoutError("pred_valid never asserted")

    async def restart_forest(self, expected_num_trees=None):
        """start+restart, then check num_trees_in_cell the following cycle."""
        await self.strobe(start=True, restart=True)
        if expected_num_trees is not None:
            assert self.num_trees == expected_num_trees, (
                f"num_trees_in_cell={self.num_trees}, expected {expected_num_trees}"
            )


async def run_case_min_latency(dut, tc):
    """Ack each prediction as soon as it is valid, starting the next
    traversal on the same cycle. Covers pred_valid rising the cycle after
    start, and the coincident ack+start release."""

    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()
    await model.init_mem(tc)
    await model.load_features(tc)

    votes = Counter()
    await model.restart_forest(tc.num_trees)

    for tree_id in range(tc.num_trees):
        await model.await_valid()
        votes[model.prediction] += 1

        last = tree_id == tc.num_trees - 1
        # Ack now; coincidentally launch the next traversal.
        await model.strobe(ack=True, start=not last)

    assert not model.busy, "cell still busy after final ack"
    assert votes == tc.expected_votes


async def run_case_with_holds(dut, tc, hold_cycles):
    """Delay every ack by `hold_cycles`, asserting pred_valid, prediction and
    busy all stay stable for the whole hold."""

    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()
    await model.init_mem(tc)
    await model.load_features(tc)

    votes = Counter()
    await model.restart_forest(tc.num_trees)

    for tree_id in range(tc.num_trees):
        await model.await_valid()
        held = model.prediction

        # Hold with ack low; nothing may move.
        model.idle()
        for c in range(hold_cycles):
            await model.tick()
            assert model.pred_valid, (
                f"tree {tree_id}: pred_valid dropped during hold (cycle {c})"
            )
            assert model.prediction == held, (
                f"tree {tree_id}: prediction changed during hold (cycle {c}): "
                f"{held} -> {model.prediction}"
            )
            assert model.busy, (
                f"tree {tree_id}: busy deasserted while holding (cycle {c})"
            )

        votes[held] += 1
        last = tree_id == tc.num_trees - 1
        await model.strobe(ack=True, start=not last)

    assert not model.busy, "cell still busy after final ack"
    assert votes == tc.expected_votes


async def run_case_delayed_start(dut, tc, gap_cycles):
    """Ack, then wait `gap_cycles` idle cycles before starting the next tree.

    Exercises the hold -> idle -> read_header path (as opposed to the
    coincident ack+start hold -> read_header path), including the cache
    changing hands via master_select while the forest is mid-flight."""

    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()
    await model.init_mem(tc)
    await model.load_features(tc)

    votes = Counter()
    await model.restart_forest(tc.num_trees)

    for tree_id in range(tc.num_trees):
        await model.await_valid()
        votes[model.prediction] += 1

        last = tree_id == tc.num_trees - 1
        # Ack alone -- no coincident start.
        await model.strobe(ack=True)

        if not last:
            # Idle gap. The cell should be quiescent and not busy.
            model.idle()
            for c in range(gap_cycles):
                await model.tick()
                assert not model.pred_valid, (
                    f"tree {tree_id}: pred_valid still high {c} cycles after ack"
                )
                assert not model.busy, (
                    f"tree {tree_id}: busy still high {c} cycles after ack "
                    f"(cache not released to ram_port)"
                )
            # Resume without restart: must continue from next_tree_addr_q.
            await model.strobe(start=True)

    assert not model.busy, "cell still busy after final ack"
    assert votes == tc.expected_votes


async def run_case_random_holds(dut, tc: TestCase):
    """Per-tree random hold lengths; seeded so failures reproduce."""
    import random

    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    rnd = random.Random(0xBEEF)

    model = CellModel(dut)
    await model.reset()
    await model.init_mem(tc)
    await model.load_features(tc)

    votes = Counter()
    holds = [rnd.randint(0, 8) for _ in range(tc.num_trees)]
    await model.restart_forest(tc.num_trees)

    for tree_id in range(tc.num_trees):
        await model.await_valid()
        held = model.prediction
        model.idle()
        for c in range(holds[tree_id]):
            await model.tick()
            assert model.pred_valid and model.prediction == held, (
                f"tree {tree_id} unstable during hold, holds={holds}"
            )
        votes[held] += 1
        last = tree_id == tc.num_trees - 1
        await model.strobe(ack=True, start=not last)

    assert votes == tc.expected_votes


async def run_case_two_forests(dut, tc: TestCase):
    """Run a full forest, then restart and run it again.

    Exercises next_tree_addr chaining across a whole cell and the restart-to-0
    path independently of the initial reset."""
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()
    await model.init_mem(tc)
    await model.load_features(tc)

    results = []
    for run in range(2):
        predictions = Counter()
        await model.restart_forest(tc.num_trees)
        for tree_id in range(tc.num_trees):
            await model.await_valid()
            predictions[model.prediction] += 1
            last = tree_id == tc.num_trees - 1
            await model.strobe(ack=True, start=not last)
        results.append(predictions)

    assert results[0] == results[1], (
        f"second forest differed: {dict(results[0])} vs {dict(results[1])}"
    )
    assert results[0] == tc.expected_votes


async def test_cell_empty_cache(dut):
    """A cell whose cache reports 0 trees must return to idle without predicting.

    Drives the cache bus to return all-zero, so the header read yields
    trees_in_cell == 0. The cell must:
      - report num_trees_in_cell == 0 the cycle following start && restart
      - deassert busy by 2 cycles after the restart strobe
      - never assert pred_valid
    """
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()

    # Force the cache to read back all zeros -> header with trees_in_cell == 0.
    await model.zero_fill_cache()

    # start + restart. model.strobe() drives for one cycle then ticks, so we
    # are settled at (restart + 1) when it returns.
    await model.strobe(start=True, restart=True)

    # Cycle +1: num_trees_in_cell is guaranteed valid here per the spec.
    assert model.num_trees == 0, (
        f"num_trees_in_cell={model.num_trees}, expected 0 for an empty cache"
    )
    assert not model.pred_valid, "pred_valid asserted on an empty cache"

    # Cycle +2: the cell must have given up and returned to idle.
    await model.tick()
    assert not model.busy, (
        "busy still asserted 2 cycles after restart with 0 trees in cache"
    )
    assert not model.pred_valid, "pred_valid asserted on an empty cache"

    # Stay quiet: no late prediction, no spontaneous re-arming.
    for c in range(20):
        await model.tick()
        assert not model.busy, f"busy re-asserted {c + 3} cycles after restart"
        assert not model.pred_valid, (
            f"pred_valid asserted {c + 3} cycles after restart on empty cache"
        )


async def test_cell_empty_then_populated(dut, tc: TestCase):
    """After an empty-cache bailout, a normal forest must still run correctly.

    Guards against the empty case leaving the cell wedged or corrupting
    next_tree_addr_q / current_header_addr_q for the following restart.
    """
    cocotb.start_soon(Clock(dut.clk, CLOCK_PERIOD, unit="ns").start())

    model = CellModel(dut)
    await model.reset()
    await model.zero_fill_cache()
    await model.strobe(start=True, restart=True)
    await model.tick()
    assert not model.busy, "cell did not return to idle on empty cache"

    # Now load a real case and run it end to end.
    await model.init_mem(tc)
    await model.load_features(tc)

    votes = Counter()
    await model.restart_forest(tc.num_trees)
    for tree_id in range(tc.num_trees):
        await model.await_valid()
        votes[model.prediction] += 1
        last = tree_id == tc.num_trees - 1
        await model.strobe(ack=True, start=not last)

    assert votes == tc.expected_votes
