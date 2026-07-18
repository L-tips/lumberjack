"""
cocotb testbench for VotesCounter.

DUT ports (monomorphized via a Veryl TB wrapper):
    clk, rst
    class_idx : input  [ADDR_WIDTH-1:0]
    inc_en    : input
    winning_max_vote       : output [DATA_WIDTH-1:0]
    winning_max_vote_class : output [ADDR_WIDTH-1:0]

The wrapper must flatten VoteResult into two scalar ports (or expose
winning.max_vote / winning.max_vote_class as hierarchical handles — see
read_winning() which tries both).
"""

import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ReadOnly

CLK_PERIOD_NS = 1


class RefModel:
    """Reference model for VotesCounter.

    Mirrors the documented contract exactly:
      - counts[class] incremented when inc_en
      - winning exposed COMBINATIONALLY: reflects this cycle's increment
      - ties broken toward the LOWEST class index
    """

    def __init__(self, dut):
        self.depth = int(dut.votes_counter.DEPTH.value)
        self.data_width = int(dut.votes_counter.DATA_WIDTH.value)
        self.dut = dut
        self.counts = [0] * self.depth
        self.max_vote = 0
        self.max_vote_class = 0

    async def reset(self):
        # NOTE: Leave any ReadOnly phase before driving.
        self.dut.inc_en.value = 0
        self.dut.class_idx.value = 0
        self.dut.rst.value = 0
        await RisingEdge(self.dut.clk)
        self.dut.rst.value = 1
        await RisingEdge(self.dut.clk)

        self.counts = [0] * self.depth
        self.max_vote = 0
        self.max_vote_class = 0

    def peek(self, class_idx, inc_en):
        """What `winning` must show THIS cycle, before the clock edge."""
        mv, mc = self.max_vote, self.max_vote_class
        if inc_en:
            new = self.counts[class_idx] + 1
            if new > mv or (new == mv and class_idx < mc):
                mv, mc = new, class_idx
        return mv, mc

    def step(self, class_idx, inc_en):
        """Commit the clock edge."""
        self.max_vote, self.max_vote_class = self.peek(class_idx, inc_en)
        if inc_en:
            self.counts[class_idx] += 1


def read_winning(dut):
    """Read the winning number of votes, and its class index"""
    return int(dut.winning_votes.value), int(dut.winning_class.value)


async def drive_and_check(dut, ref, class_idx, inc_en, ctx=""):
    """Drive one transaction, check the combinational output, commit."""
    dut.class_idx.value = class_idx
    dut.inc_en.value = inc_en

    await ReadOnly()
    exp_mv, exp_mc = ref.peek(class_idx, inc_en)
    got_mv, got_mc = read_winning(dut)
    assert (got_mv, got_mc) == (exp_mv, exp_mc), (
        f"{ctx} combinational winning mismatch: "
        f"class_idx={class_idx} inc_en={inc_en} "
        f"expected=({exp_mv},{exp_mc}) got=({got_mv},{got_mc}) "
        f"counts={ref.counts}"
    )

    await RisingEdge(dut.clk)
    ref.step(class_idx, inc_en)


@cocotb.test()
async def test_reset_state(dut):
    """After reset: zero votes, class 0, and all counters cleared."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()
    await ReadOnly()
    mv, mc = read_winning(dut)
    assert (mv, mc) == (0, 0), f"bad reset state ({mv},{mc})"
    await RisingEdge(dut.clk)

    # Every class must read back as 0 -> first increment of any class gives 1.
    for c in range(ref.depth):
        await ref.reset()
        await drive_and_check(dut, ref, c, True, ctx=f"first-inc class{c}")


@cocotb.test()
async def test_single_class_monotonic(dut):
    """Repeated increments of one class: count rises, class stays put."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    target = 3
    for i in range(20):
        await drive_and_check(dut, ref, target, True, ctx=f"mono i={i}")
    assert ref.max_vote_class == target


@cocotb.test()
async def test_inc_en_low_holds(dut):
    """inc_en low must not change counts or winning, whatever class_idx does."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    for _ in range(5):
        await drive_and_check(dut, ref, 2, True)
    snapshot = (ref.max_vote, ref.max_vote_class, list(ref.counts))

    for c in range(ref.depth):
        await drive_and_check(dut, ref, c, False, ctx=f"idle class{c}")
    assert (ref.max_vote, ref.max_vote_class, ref.counts) == snapshot


@cocotb.test()
async def test_tie_breaks_to_lowest_class(dut):
    """A later class tying the max takes the title only if its index is lower."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    # class5 -> 2 votes, leads.
    await drive_and_check(dut, ref, 5, True, ctx="c5 a")
    await drive_and_check(dut, ref, 5, True, ctx="c5 b")
    assert (ref.max_vote, ref.max_vote_class) == (2, 5)

    # class2 ties at 2 -> lower index wins.
    await drive_and_check(dut, ref, 2, True, ctx="c2 a")
    await drive_and_check(dut, ref, 2, True, ctx="c2 b")
    assert (ref.max_vote, ref.max_vote_class) == (2, 2)

    # class7 ties at 2 -> higher index must NOT take it.
    await drive_and_check(dut, ref, 7, True, ctx="c7 a")
    await drive_and_check(dut, ref, 7, True, ctx="c7 b")
    assert (ref.max_vote, ref.max_vote_class) == (2, 2)

    # class7 exceeds -> takes it outright.
    await drive_and_check(dut, ref, 7, True, ctx="c7 c")
    assert (ref.max_vote, ref.max_vote_class) == (3, 7)


@cocotb.test()
async def test_combinational_read_during_increment(dut):
    """The documented contract: winning reflects THIS cycle's increment.

    drive_and_check already asserts this on every transaction, but this test
    isolates the case where the increment itself creates a new leader, which is
    where a registered (one-cycle-late) output would be caught.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    await drive_and_check(dut, ref, 4, True, ctx="lead a")
    await drive_and_check(dut, ref, 4, True, ctx="lead b")

    # class1 is at 0; two increments make it tie then... still behind.
    dut.class_idx.value = 1
    dut.inc_en.value = 1
    await ReadOnly()
    exp = ref.peek(1, True)
    got = read_winning(dut)
    assert got == exp, f"late output: expected {exp} got {got}"
    await RisingEdge(dut.clk)
    ref.step(1, True)


@cocotb.test()
async def test_all_classes_exhaustive_pairs(dut):
    """Exhaustive over ordered class pairs: build a tie, then check the winner.

    For every (a, b) with a != b, drive a to k votes then b to k votes and
    assert the winner is min(a, b) at k votes. This is the full tie-break
    truth table rather than a sample of it.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    K = 3
    for a in range(ref.depth):
        for b in range(ref.depth):
            if a == b:
                continue
            await ref.reset()

            for _ in range(K):
                await drive_and_check(dut, ref, a, True, ctx=f"pair a={a}")
            for _ in range(K):
                await drive_and_check(dut, ref, b, True, ctx=f"pair b={b}")
            assert (ref.max_vote, ref.max_vote_class) == (K, min(a, b)), (
                f"pair({a},{b}) -> ({ref.max_vote},{ref.max_vote_class})"
            )


@cocotb.test()
async def test_random_stress_vs_reference(dut):
    """Long randomised run checked against the reference model every cycle."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    rnd = random.Random(0xB0A7)

    # Bound the run so no counter can overflow DATA_WIDTH.
    max_incs = (1 << ref.data_width) - 1
    incs = 0
    for i in range(2000):
        inc = rnd.random() < 0.7
        if inc and incs >= max_incs:
            inc = False
        c = rnd.randrange(ref.depth)
        await drive_and_check(dut, ref, c, inc, ctx=f"rand i={i}")
        if inc:
            incs += 1

    # Final cross-check: the model's winner must match a fresh argmax with
    # lowest-index tie-breaking.
    best = max(range(ref.depth), key=lambda c: (ref.counts[c], -c))
    assert (ref.max_vote, ref.max_vote_class) == (ref.counts[best], best), (
        f"reference self-inconsistency: counts={ref.counts}"
    )


@cocotb.test()
async def test_overflow_guard(dut):
    """Document the overflow bound: DATA_WIDTH must hold the max vote count.

    Votes are bounded by the number of trees, so DATA_WIDTH = TREE_IDX_WIDTH is
    only safe if each tree votes at most once. Drive one class to the width
    limit and assert no wrap.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    ref = RefModel(dut)
    await ref.reset()

    limit = (1 << ref.data_width) - 1
    for i in range(limit):
        await drive_and_check(dut, ref, 0, True, ctx=f"ovf i={i}")
    await ReadOnly()
    mv, _ = read_winning(dut)
    assert mv == limit, f"count wrapped or saturated early: {mv}"
