from dataclasses import dataclass
from cocotb.triggers import RisingEdge
from typing import Optional, Tuple

@dataclass(frozen=True)
class Transaction:
    addr: int
    wdata: int = 0
    we: bool = False
    sel: Optional[int] = None

class WbMaster:
    """
    Pipelined Wishbone master.
    Holds all request signals stable while wb.stall is asserted.
    Returns (ack, err, rdata).
    """

    def __init__(self, data_width, clk, bus):
        self.data_width = data_width
        # Byte lanes
        self.col_width = self.data_width // 8
        self.full_sel = (1 << self.col_width) - 1 # 0xF
        self.clk = clk
        self.bus = bus

    async def transaction(
        self,
        txn: Transaction,
        timeout: int = 200,
    ) -> Tuple[int, int, int]:
        sel = txn.sel
        if txn.sel is None:
            sel = self.full_sel

        self.bus.cyc.value          = 1
        self.bus.stb.value          = 1
        self.bus.addr.value         = txn.addr
        self.bus.write_data.value   = txn.wdata
        self.bus.write_enable.value = txn.we
        self.bus.select.value       = sel

        for _ in range(timeout):
            await RisingEdge(self.clk)
            if not self.bus.stall.value:
                # Request accepted — deassert immediately
                self.bus.cyc.value          = 0
                self.bus.stb.value          = 0
                self.bus.write_enable.value = 0
                self.bus.select.value       = 0
                # ack/err/rdata come from the FF, valid on the next edge
                await RisingEdge(self.clk)
                ack   = int(self.bus.ack.value)
                err   = int(self.bus.err.value)
                rdata = int(self.bus.read_data.value)
                return ack, err, rdata

        raise RuntimeError(f"WB timeout at addr=0x{txn.addr:08x}")

    async def pipelined_transactions(
        self,
        txns: list[Transaction],
        timeout: int = 200,
    ) -> list[tuple[int, int, int]]:
        """
        Issue multiple Wishbone transactions using B4 pipelining.

        Returns:
            [(ack, err, rdata), ...]
        """

        if not txns:
            return []

        responses = []

        issued = 0
        completed = 0

        self.bus.cyc.value = 1

        for _ in range(timeout):

            # Drive next request
            if issued < len(txns):
                txn = txns[issued]

                sel = self.full_sel if txn.sel is None else txn.sel

                self.bus.stb.value          = 1
                self.bus.addr.value         = txn.addr
                self.bus.write_data.value   = txn.wdata
                self.bus.write_enable.value = txn.we
                self.bus.select.value       = sel
            else:
                self.bus.stb.value = 0

            await RisingEdge(self.clk)

            # Request accepted
            if issued < len(txns) and not self.bus.stall.value:
                issued += 1

            # Response received
            if self.bus.ack.value or self.bus.err.value:
                responses.append((
                    int(self.bus.ack.value),
                    int(self.bus.err.value),
                    int(self.bus.read_data.value),
                ))
                completed += 1

            # Done
            if completed == len(txns):
                self.bus.cyc.value          = 0
                self.bus.stb.value          = 0
                self.bus.write_enable.value = 0
                self.bus.select.value       = 0

                return responses

        self.bus.cyc.value          = 0
        self.bus.stb.value          = 0
        self.bus.write_enable.value = 0
        self.bus.select.value       = 0

        raise RuntimeError(
            f"WB timeout: issued={issued}, completed={completed}, "
            f"expected={len(txns)}"
        )