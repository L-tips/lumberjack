import cocotb
from cocotb.triggers import RisingEdge, ClockCycles, Combine

from typing import Optional

import utils
from wb_driver import WbMaster, Transaction
import struct


class CSR:
    CTRL = 0x00
    CTRL_SET = 0x04
    CTRL_CLR = 0x08
    PREDICTION = 0x1C
    VOTES = 0x20
    INTEN_SET = 0x24
    INTEN_CLR = 0x28
    INTFLAG = 0x2C
    PERF = 0x30
    NUM_CELLS = 0x34
    # feat_write(i) is at a base offset + i*4
    FEAT_BASE = 0x40


# CSR bit masks
CTRL_ENABLE = 1 << 0
CTRL_BUSY = 1 << 1
INTFLAG_READY = 1 << 0
INTFLAG_ERROR = 1 << 1


# ---------------------------------------------------------------------------
# bf16 helper
# ---------------------------------------------------------------------------
def pack_feat_word(chunk0_bits: int, chunk1_bits: int = 0) -> int:
    """Pack two bf16 values into a 32-bit word (chunk0 in [15:0], chunk1 in [31:16])."""
    return ((chunk1_bits & 0xFFFF) << 16) | (chunk0_bits & 0xFFFF)


# ---------------------------------------------------------------------------
# Model data helper
# ---------------------------------------------------------------------------
class ModelCache:
    """Holds the binary data destined for one hardware cache."""

    def __init__(self, filename):
        with open(filename, "rb") as f:
            self.bytes = f.read()

    def to_words(self) -> list[tuple[int, int]]:
        """
        Reinterpret bytes as 32-bit little-endian words.
        Last word is zero-padded if len(bytes) % 4 != 0.
        Returns (word, sel) tuples — sel masks out padding bytes.
        """
        data = self.bytes
        remainder = len(data) % 4
        if remainder:
            pad = 4 - remainder
            data = data + b"\x00" * pad
            # sel has a 1 bit per valid byte lane: e.g. 3 valid bytes → 0b0111
            last_sel = (1 << remainder) - 1
        else:
            last_sel = 0xF

        words = struct.unpack_from(f"<{len(data) // 4}I", data)

        # All words use full sel except the last one
        result = [(w, 0xF) for w in words[:-1]]
        result.append((words[-1], last_sel))
        return result


class Model:
    """
    Mirrors the Rust Model type.  Provide the raw cache data as a list of
    ModelCache objects (one per cell), pre-parsed from your binary format.
    num_features must match the hardware CSR.
    """

    def __init__(self, caches: list[ModelCache]):
        self.caches = caches

    def num_cells(self) -> int:
        return len(self.caches)


# ---------------------------------------------------------------------------
# Accelerator Driver
# ---------------------------------------------------------------------------
class Driver:
    """
    Python/cocotb port of the Rust Accelerator driver.

    Parameters
    ----------
    csr_bus    : WbMaster for the CSR port
    cache_buses: list of WbMaster, one per cache cell (same order as
                 L::cache_start_addrs)
    cache_base_addrs : list of base byte addresses for each cache SRAM,
                       as seen from the cache WB buses (typically 0x0 each,
                       since each cache has its own dedicated bus)
    """

    def __init__(
        self,
        clk,
        control_bus: WbMaster,
        cache_buses: list[WbMaster],
        cache_base_addrs: Optional[list[int]] = None,
    ):
        self.clk = clk
        self.control_bus = control_bus
        self.cache_buses = cache_buses
        self.cache_base = cache_base_addrs or [0x0] * len(cache_buses)

    async def reset(self, rst, cycles: int = 1):
        await ClockCycles(self.clk, cycles)

        rst.value = 0

        self.control_bus.reset()
        for bus in self.cache_buses:
            bus.reset()

        await ClockCycles(self.clk, cycles)

        rst.value = 1
        await ClockCycles(self.clk, cycles)

    # ------------------------------------------------------------------
    # Mirrors Accelerator::write_caches()
    # Each cache gets a burst of pipelined WB writes on its own bus.
    # ------------------------------------------------------------------
    async def write_caches(self, model):
        assert len(model.caches) <= len(self.cache_buses), (
            f"Model needs {len(model.caches)} cache buses, "
            f"only {len(self.cache_buses)} provided"
        )
        tasks = []
        for cache, bus, base in zip(model.caches, self.cache_buses, self.cache_base):
            txns = [
                Transaction(addr=base + i * 4, wdata=word, we=True, sel=sel)
                for i, (word, sel) in enumerate(cache.to_words())
            ]
            tasks.append(cocotb.start_soon(bus.pipelined(txns)))
        await Combine(*tasks)

    # ------------------------------------------------------------------
    # Mirrors Accelerator::start()
    # ------------------------------------------------------------------
    async def start(self, features: list[float]) -> None:
        # Write feature pairs as 32-bit words, matching Rust's chunks(2)
        for i in range(0, len(features), 2):
            chunk0 = utils.float_to_bf16_bits(features[i])
            chunk1 = (
                utils.float_to_bf16_bits(features[i + 1])
                if i + 1 < len(features)
                else 0
            )
            word = pack_feat_word(chunk0, chunk1)
            await self.write_reg_32(CSR.FEAT_BASE + (i // 2) * 4, word)

        await self.write_reg_32(CSR.CTRL_SET, CTRL_ENABLE)

    async def read_reg(self, addr) -> int:
        _, _, rdata = await self.control_bus.transaction(
            Transaction(
                addr=addr,
            )
        )
        return rdata

    async def write_reg_32(self, addr, wdata):
        return await self.control_bus.transaction(
            Transaction(addr=addr, wdata=wdata, sel=0xF, we=True)
        )

    # ------------------------------------------------------------------
    # Status / result accessors — mirror the Rust methods
    # ------------------------------------------------------------------
    async def ready(self) -> bool:
        v = await self.read_reg(CSR.INTFLAG)
        return bool(v & INTFLAG_READY)

    async def error(self) -> bool:
        v = await self.read_reg(CSR.INTFLAG)
        return bool(v & INTFLAG_ERROR)

    async def busy(self) -> bool:
        v = await self.read_reg(CSR.CTRL)
        return bool(v & CTRL_BUSY)

    async def enable_interrupt(self):
        await self.write_reg_32(CSR.INTEN_SET, INTFLAG_READY)

    async def disable_interrupt(self):
        await self.write_reg_32(CSR.INTEN_CLR, INTFLAG_READY)

    async def prediction(self) -> int:
        v = await self.read_reg(CSR.PREDICTION)
        return v

    async def num_votes(self) -> int:
        v = await self.read_reg(CSR.VOTES)
        return v

    async def num_cycles(self) -> int:
        v = await self.read_reg(CSR.PERF)
        return v

    # ------------------------------------------------------------------
    # Wait helpers (useful in testbenches)
    # ------------------------------------------------------------------
    async def wait_ready_poll(self, timeout_cycles: int = 10_000) -> None:
        """Poll INTFLAG.ready until asserted (no IRQ wiring needed)."""
        for _ in range(timeout_cycles):
            if await self.ready():
                return
            await RisingEdge(self.clk)
        raise TimeoutError("Accelerator did not assert ready within timeout")

    async def wait_ready_irq(self, irq_signal) -> None:
        """Wait for the IRQ line to go high (zero overhead polling)."""
        await RisingEdge(irq_signal)

    # ------------------------------------------------------------------
    # Private
    # ------------------------------------------------------------------
    async def _num_cells(self) -> int:
        v = await self.read_reg(CSR.NUM_CELLS)
        return v
