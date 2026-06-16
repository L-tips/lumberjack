"""
Cocotb testbench for TestRam2Wb
================================

The DUT instantiates Bram2Wishbone + SinglePortBlockRam internally.
No external BRAM model or driver needed — reads are verified by
issuing a second WB transaction.

Known widths from TestRam2Wb constants:
  WB_ADDR_WIDTH  = 32
  WB_DATA_WIDTH  = 32
  RAM_NUM_COL    = 8      → RAM_DATA_WIDTH = 64
  RAM_SIZE       = 1024   → RAM_ADDR_WIDTH = 10

Internal signal paths (Veryl modport elaboration):
  bus.cyc / stb / addr / write_data / write_enable / select
  bus.ack / err / stall / read_data
  dut.ram_port.enable / address / write_data / byte_write_enable / read_data
"""

import random
import logging
import math

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, ClockCycles

from wb_driver import Transaction, WbMaster

log = logging.getLogger("tb")
log.setLevel(logging.DEBUG)

CLK_PERIOD_NS = 10

# ---------------------------------------------------------------------------
# Widths — derived from TestRam2Wb constants; change here if they change
# ---------------------------------------------------------------------------
WB_ADDR_WIDTH  = 32
WB_DATA_WIDTH  = 32
RAM_NUM_COL    = 8
RAM_DATA_WIDTH = RAM_NUM_COL * 8   # 64
RAM_SIZE       = 1024
RAM_ADDR_WIDTH = int(math.log2(RAM_SIZE))  # 10

WB_COL_WIDTH   = WB_DATA_WIDTH  // 8   # 4  (byte lanes on WB side)
RAM_COL_WIDTH  = RAM_DATA_WIDTH // 8   # 8  (byte lanes in RAM word)
SUBWORD_COUNT  = RAM_COL_WIDTH  // WB_COL_WIDTH  # 2

WB_ADDR_SHIFT  = int(math.log2(WB_COL_WIDTH))   # 2
RAM_ADDR_SHIFT = int(math.log2(RAM_COL_WIDTH))  # 3

FULL_SEL       = (1 << WB_COL_WIDTH) - 1   # 0xF

# ---------------------------------------------------------------------------
# Reset
# ---------------------------------------------------------------------------

async def do_reset(dut, cycles: int = 4):
    dut.wb_rst.value             = 1
    dut.ram_busy.value        = 0
    dut.wb.cyc.value          = 0
    dut.wb.stb.value          = 0
    dut.wb.write_enable.value = 0
    dut.wb.select.value       = 0
    dut.wb.addr.value         = 0
    dut.wb.write_data.value   = 0
    await ClockCycles(dut.clk, cycles)
    dut.wb_rst.value = 0
    await ClockCycles(dut.clk, 2)

async def clear_ram_range(wb_master, start_word: int, count: int):
    for ram_word in range(start_word, start_word + count):
        for sub in range(SUBWORD_COUNT):
            addr = wb_byte_addr(ram_word=ram_word, sub_idx=sub)
            await wb_master.transaction(Transaction(addr=addr, wdata=0, we=1))

# ---------------------------------------------------------------------------
# Address helpers
# ---------------------------------------------------------------------------

def wb_byte_addr(ram_word: int, sub_idx: int = 0, byte_lane: int = 0) -> int:
    """
    Compute the WB byte address for a given RAM word index, sub-word
    index within that RAM word, and byte lane within the sub-word.
    """
    return (ram_word << RAM_ADDR_SHIFT) + (sub_idx << WB_ADDR_SHIFT) + byte_lane

# ---------------------------------------------------------------------------
# Test 0 - Issue pipelined transactions
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_pipelined_transactions(dut):
    """Write a 32-bit word and read it back via a second transaction."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)

    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=4, sub_idx=0)

    transactions = []
    for addr in range(0, 20, 4):
        transactions.append(Transaction(addr=addr, we=True, wdata=addr))

    responses = await wb.pipelined_transactions(transactions)
    for i, (ack, err, _) in enumerate(responses):
        assert ack == 1 and err == 0, f"Write failed at tx {i}"

    transactions = []
    for addr in range(0, 20, 4):
        transactions.append(Transaction(addr=addr, we=False))

    responses = await wb.pipelined_transactions(transactions)
    for i, (ack, err, rdata) in enumerate(responses):
        assert ack == 1 and err == 0, "Read failed"
        assert rdata == i * 4, f"Read-back: 0x{rdata:08x}"

    log.info("test_pipelined_transactions PASSED")


# ---------------------------------------------------------------------------
# Test 1 — full-word write then read-back
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_full_word_write_read(dut):
    """Write a 32-bit word and read it back via a second transaction."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)

    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=4, sub_idx=0)

    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0xDEADBEEF, we=1))
    assert ack == 1 and err == 0, "Write failed"

    ack, err, rdata = await wb.transaction(Transaction(addr=addr))
    assert ack == 1 and err == 0, "Read failed"
    assert rdata == 0xDEADBEEF,   f"Read-back: 0x{rdata:08x}"

    log.info("test_full_word_write_read PASSED")


# ---------------------------------------------------------------------------
# Test 2 — second sub-word of a 64-bit RAM word is independent
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_subword_independence(dut):
    """
    Write distinct values to the lower and upper 32-bit sub-words of
    a single 64-bit RAM word, then verify each reads back correctly
    and that writing one does not disturb the other.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)

    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr_lo = wb_byte_addr(ram_word=0, sub_idx=0)
    addr_hi = wb_byte_addr(ram_word=0, sub_idx=1)

    # Write lower sub-word
    ack, err, _ = await wb.transaction(Transaction(addr=addr_lo, wdata=0x11111111, we=1))
    assert ack == 1 and err == 0, "Lower sub-word write failed"

    # Write upper sub-word
    ack, err, _ = await wb.transaction(Transaction(addr=addr_hi, wdata=0x22222222, we=1))
    assert ack == 1 and err == 0, "Upper sub-word write failed"

    # Read lower — must still be 0x11111111
    ack, err, rdata = await wb.transaction(Transaction(addr=addr_lo))
    assert ack == 1 and err == 0
    assert rdata == 0x11111111, f"Lower sub-word: 0x{rdata:08x}"

    # Read upper — must still be 0x22222222
    ack, err, rdata = await wb.transaction(Transaction(addr=addr_hi))
    assert ack == 1 and err == 0
    assert rdata == 0x22222222, f"Upper sub-word: 0x{rdata:08x}"

    log.info("test_subword_independence PASSED")


# ---------------------------------------------------------------------------
# Test 3 — byte reads, all 4 lanes
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_byte_reads(dut):
    """Plant a full word, then read each byte lane individually."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=1, sub_idx=0)

    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0xAABBCCDD, we=1))
    assert ack == 1 and err == 0, "Seed write failed"

    # Each lane returns only the relevant byte (others masked to 0)
    expected_bytes = [0xDD, 0xCC, 0xBB, 0xAA]   # little-endian
    for lane in range(WB_COL_WIDTH):
        byte_addr = addr + lane
        ack, err, rdata = await wb.transaction(
            Transaction(addr=byte_addr, sel=1 << lane)
        )
        assert ack == 1 and err == 0, f"Byte read lane {lane} failed"
        got = (rdata >> (lane * 8)) & 0xFF
        assert got == expected_bytes[lane], \
            f"Lane {lane}: got 0x{got:02x} expected 0x{expected_bytes[lane]:02x}"

    log.info("test_byte_reads PASSED")


# ---------------------------------------------------------------------------
# Test 4 — byte writes, verify adjacent lanes untouched
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_byte_writes(dut):
    """Write each byte lane individually; read back the whole word."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    # Zero the target word first
    addr = wb_byte_addr(ram_word=2, sub_idx=0)
    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0x00000000, we=1))
    assert ack == 1 and err == 0

    pattern = [0xAA, 0xBB, 0xCC, 0xDD]
    for lane, val in enumerate(pattern):
        byte_addr = addr + lane
        wdata     = val << (lane * 8)
        ack, err, _ = await wb.transaction(
            Transaction(addr=byte_addr, wdata=wdata, we=1, sel=1 << lane)
        )
        assert ack == 1 and err == 0, f"Byte write lane {lane} failed"

    ack, err, rdata = await wb.transaction(Transaction(addr=addr))
    assert ack == 1 and err == 0
    assert rdata == 0xDDCCBBAA, f"Full read-back: 0x{rdata:08x}"

    log.info("test_byte_writes PASSED")


# ---------------------------------------------------------------------------
# Test 5 — halfword reads (lower and upper)
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_halfword_reads(dut):
    """Write a word, read back each halfword with appropriate sel."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=3, sub_idx=0)
    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0x1234ABCD, we=1))
    assert ack == 1 and err == 0

    # Lower halfword: sel=0b0011, addr offset 0
    ack, err, rdata = await wb.transaction(Transaction(addr=addr, sel=0b0011))
    assert ack == 1 and err == 0
    assert rdata & 0xFFFF == 0xABCD, f"Lower HW: 0x{rdata & 0xFFFF:04x}"

    # Upper halfword: sel=0b1100, addr offset 2
    ack, err, rdata = await wb.transaction(Transaction(addr=addr + 2, sel=0b1100))
    assert ack == 1 and err == 0
    assert rdata >> 16 == 0x1234, f"Upper HW: 0x{rdata >> 16:04x}"

    log.info("test_halfword_reads PASSED")


# ---------------------------------------------------------------------------
# Test 6 — halfword writes, verify other half untouched
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_halfword_writes(dut):
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=5, sub_idx=0)

    # Seed with all-ones
    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0xFFFFFFFF, we=1))
    assert ack == 1 and err == 0

    # Overwrite lower halfword only
    ack, err, _ = await wb.transaction(
        Transaction(addr=addr, wdata=0x0000BEEF, we=1, sel=0b0011)
    )
    assert ack == 1 and err == 0

    ack, err, rdata = await wb.transaction(Transaction(addr=addr))
    assert ack == 1 and err == 0
    assert rdata == 0xFFFFBEEF, \
        f"After lower HW write: 0x{rdata:08x} (upper half should be 0xFFFF)"

    # Overwrite upper halfword only
    ack, err, _ = await wb.transaction(
        Transaction(addr=addr + 2, wdata=0xDEAD0000, we=1, sel=0b1100)
    )
    assert ack == 1 and err == 0

    ack, err, rdata = await wb.transaction(Transaction(addr=addr))
    assert ack == 1 and err == 0
    assert rdata == 0xDEADBEEF, f"After upper HW write: 0x{rdata:08x}"

    log.info("test_halfword_writes PASSED")


# ---------------------------------------------------------------------------
# Test 7 — misaligned accesses → ERR, no ram_port.enable pulse
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_misaligned(dut):
    """
    Misaligned = lowest set sel bit does not match addr[ADDR_SHIFT-1:0].
    Expect ERR=1, ACK=0, and ram_port.enable must never pulse.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())

    en_pulses = []
    async def watch_en():
        while True:
            await RisingEdge(dut.clk)
            if int(dut.ram_port.enable.value):
                en_pulses.append(1)
    cocotb.start_soon(watch_en())

    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=6, sub_idx=0)

    # sel=0b0110 implies access starts at byte lane 1,
    # but addr[1:0]=0b00 implies lane 0 — mismatch.
    ack, err, _ = await wb.transaction(Transaction(addr=addr, sel=0b0110))
    assert err == 1, "Expected ERR for misaligned halfword"
    assert ack == 0, "Expected no ACK for misaligned access"

    # sel=0b0100 (byte lane 2) but addr[1:0]=0b00 (lane 0) — mismatch.
    ack, err, _ = await wb.transaction(Transaction(addr=addr, sel=0b0100))
    assert err == 1, "Expected ERR for misaligned byte"
    assert ack == 0

    # sel=0b1000 (byte lane 3) but addr[1:0]=0b01 (lane 1) — mismatch.
    ack, err, _ = await wb.transaction(Transaction(addr=addr + 1, sel=0b1000))
    assert err == 1, "Expected ERR for misaligned byte (lane 3 vs offset 1)"
    assert ack == 0

    assert not en_pulses, \
        f"ram_port.enable pulsed {len(en_pulses)} times on misaligned accesses"

    log.info("test_misaligned PASSED")


# ---------------------------------------------------------------------------
# Test 8 — ram_busy stalls the master
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_ram_busy(dut):
    """ram_busy held high for several cycles; transaction must still complete."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    addr = wb_byte_addr(ram_word=7, sub_idx=0)

    # Pre-write without busy
    ack, err, _ = await wb.transaction(Transaction(addr=addr, wdata=0x600DC0DE, we=1))
    assert ack == 1 and err == 0

    # Now assert busy, issue a read, release after 8 cycles
    dut.ram_busy.value = 1

    async def release_after(n):
        await ClockCycles(dut.clk, n)
        dut.ram_busy.value = 0

    cocotb.start_soon(release_after(8))

    ack, err, rdata = await wb.transaction(Transaction(addr=addr))
    assert ack == 1 and err == 0
    assert rdata == 0x600DC0DE, f"0x{rdata:08x}"

    log.info("test_ram_busy PASSED")


# ---------------------------------------------------------------------------
# Test 9 — back-to-back full-word transactions
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_back_to_back(dut):
    """Write N words sequentially then read them all back."""
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    N = 16
    for i in range(N):
        addr = wb_byte_addr(ram_word=i, sub_idx=0)
        ack, err, _ = await wb.transaction(
            Transaction(addr=addr, wdata=0xA0000000 | i, we=1)
        )
        assert ack == 1 and err == 0, f"Write {i} failed"

    for i in range(N):
        addr = wb_byte_addr(ram_word=i, sub_idx=0)
        ack, err, rdata = await wb.transaction(Transaction(addr=addr))
        assert ack == 1 and err == 0, f"Read {i} failed"
        assert rdata == 0xA0000000 | i, \
            f"Word {i}: 0x{rdata:08x}"

    log.info("test_back_to_back PASSED")


# ---------------------------------------------------------------------------
# Test 10 — upper sub-word of every RAM word in a range
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_upper_subword_range(dut):
    """
    Specifically exercise the upper 32-bit slot (sub_idx=1) of several
    consecutive 64-bit RAM words to stress the sub-word index logic.
    """
    N = 8

    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    # Reset RAM contents to 0
    await clear_ram_range(wb, start_word=0, count=N)

    for i in range(N):
        addr = wb_byte_addr(ram_word=i, sub_idx=1)
        ack, err, _ = await wb.transaction(
            Transaction(addr=addr, wdata=0xB0000000 | i, we=1)
        )
        assert ack == 1 and err == 0, f"Upper sub-word write {i} failed"

    for i in range(N):
        # Lower sub-word must read as 0 (RAM was reset)
        addr_lo = wb_byte_addr(ram_word=i, sub_idx=0)
        ack, err, rdata = await wb.transaction(Transaction(addr=addr_lo))
        assert ack == 1 and err == 0
        assert rdata == 0, \
            f"Lower sub-word of RAM word {i} should be 0, got 0x{rdata:08x}"

        # Upper sub-word must hold our written value
        addr_hi = wb_byte_addr(ram_word=i, sub_idx=1)
        ack, err, rdata = await wb.transaction(Transaction(addr=addr_hi))
        assert ack == 1 and err == 0
        assert rdata == 0xB0000000 | i, \
            f"Upper sub-word of RAM word {i}: 0x{rdata:08x}"

    log.info("test_upper_subword_range PASSED")


# ---------------------------------------------------------------------------
# Test 11 — randomised stress with reference model
# ---------------------------------------------------------------------------
@cocotb.test()
async def test_stress(dut):
    """
    300 randomised transactions: full-word writes, full-word reads,
    byte writes, misaligned (expect ERR).  A software reference model
    tracks expected memory state.  Intermittent ram_busy throughout.
    """
    cocotb.start_soon(Clock(dut.clk, CLK_PERIOD_NS, unit="ns").start())
    await do_reset(dut)
    wb = WbMaster(WB_DATA_WIDTH, dut.clk, dut.wb)

    DEPTH  = 64    # RAM words we will touch (well within RAM_SIZE=1024)
    NTRANS = 300
    rng    = random.Random(0xC0FFEE42)

    # Reset RAM contents to 0
    await clear_ram_range(wb, start_word=0, count=DEPTH)

    # Reference memory: DEPTH entries, each RAM_DATA_WIDTH bits wide
    refmem = [0] * DEPTH

    def ref_write(ram_word: int, sub_idx: int, data: int, sel: int):
        old     = refmem[ram_word % DEPTH]
        bit_off = sub_idx * WB_DATA_WIDTH
        for b in range(WB_COL_WIDTH):
            if sel & (1 << b):
                byte_off = bit_off + b * 8
                old = (old & ~(0xFF << byte_off)) | \
                      (((data >> (b * 8)) & 0xFF) << byte_off)
        refmem[ram_word % DEPTH] = old

    def ref_read(ram_word: int, sub_idx: int, sel: int) -> int:
        word    = refmem[ram_word % DEPTH]
        bit_off = sub_idx * WB_DATA_WIDTH
        result  = 0
        for b in range(WB_COL_WIDTH):
            if sel & (1 << b):
                byte_off = bit_off + b * 8
                result  |= ((word >> byte_off) & 0xFF) << (b * 8)
        return result

    # Intermittent busy
    async def busy_gen():
        while True:
            dut.ram_busy.value = 0
            await ClockCycles(dut.clk, rng.randint(4, 15))
            dut.ram_busy.value = 1
            await ClockCycles(dut.clk, rng.randint(1, 4))

    busy_task = cocotb.start_soon(busy_gen())
    failures  = []

    for i in range(NTRANS):
        kind     = rng.choice(["read", "write", "byte_write", "misaligned"])
        ram_word = rng.randint(0, DEPTH - 1)
        sub_idx  = rng.randint(0, SUBWORD_COUNT - 1)
        addr     = wb_byte_addr(ram_word=ram_word, sub_idx=sub_idx)

        if kind == "misaligned":
            # Pick a sel whose lowest set bit doesn't match addr[1:0] = 0
            lane    = rng.randint(1, WB_COL_WIDTH - 1)
            bad_sel = 1 << lane   # lowest set bit is `lane`, but addr[1:0]=0
            ack, err, _ = await wb.transaction(Transaction(addr=addr, sel=bad_sel))
            if err != 1:
                failures.append(
                    f"[{i}] misaligned addr=0x{addr:08x} sel=0b{bad_sel:04b}: "
                    f"expected ERR, got ack={ack} err={err}"
                )

        elif kind == "write":
            wdata = rng.randint(0, 0xFFFFFFFF)
            ack, err, _ = await wb.transaction(
                Transaction(addr=addr, wdata=wdata, we=1)
            )
            if err or not ack:
                failures.append(
                    f"[{i}] write failed addr=0x{addr:08x} "
                    f"(ack={ack} err={err})"
                )
            else:
                ref_write(ram_word, sub_idx, wdata, FULL_SEL)

        elif kind == "byte_write":
            lane      = rng.randint(0, WB_COL_WIDTH - 1)
            sel       = 1 << lane
            byte_addr = addr + lane
            wdata     = rng.randint(0, 0xFF) << (lane * 8)
            ack, err, _ = await wb.transaction(
                Transaction(addr=byte_addr, wdata=wdata, we=1, sel=sel)
            )
            if err or not ack:
                failures.append(
                    f"[{i}] byte write failed addr=0x{byte_addr:08x} "
                    f"lane={lane} (ack={ack} err={err})"
                )
            else:
                ref_write(ram_word, sub_idx, wdata, sel)

        else:  # read
            ack, err, rdata = await wb.transaction(Transaction(addr=addr))
            if err or not ack:
                failures.append(
                    f"[{i}] read failed addr=0x{addr:08x} "
                    f"(ack={ack} err={err})"
                )
            else:
                expected = ref_read(ram_word, sub_idx, FULL_SEL)
                if rdata != expected:
                    failures.append(
                        f"[{i}] read mismatch ram[{ram_word}] sub{sub_idx}: "
                        f"got 0x{rdata:08x} expected 0x{expected:08x}"
                    )

    busy_task.cancel()
    dut.ram_busy.value = 0

    if failures:
        for f in failures[:20]:
            log.error(f)
        if len(failures) > 20:
            log.error(f"... and {len(failures) - 20} more")
        raise AssertionError(f"{len(failures)}/{NTRANS} transactions failed")

    log.info(f"test_stress PASSED ({NTRANS} transactions)")