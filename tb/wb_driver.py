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

    def __init__(self, clk, bus):
        self.bus = bus
        self.data_width = len(self.bus.write_data)
        # Byte lanes
        self.col_width = self.data_width // 8
        self.full_sel = (1 << self.col_width) - 1  # 0xF
        self.clk = clk

    def reset(self):
        self.bus.cyc.value = 0
        self.bus.stb.value = 0
        self.bus.write_enable.value = 0
        self.bus.select.value = 0
        self.bus.addr.value = 0
        self.bus.write_data.value = 0

    async def transaction(
        self,
        txn: Transaction,
        timeout: int | None = 200,
    ) -> Tuple[int, int, int]:
        sel = txn.sel if txn.sel is not None else self.full_sel

        self.bus.cyc.value = 1
        self.bus.stb.value = 1
        self.bus.addr.value = txn.addr
        self.bus.write_data.value = txn.wdata
        self.bus.write_enable.value = txn.we
        self.bus.select.value = sel

        cycles = 0
        while timeout is None or cycles < timeout:
            await RisingEdge(self.clk)
            cycles += 1
            if not self.bus.stall.value:
                self.bus.cyc.value = 0
                self.bus.stb.value = 0
                self.bus.write_enable.value = 0
                self.bus.select.value = 0
                await RisingEdge(self.clk)
                return (
                    int(self.bus.ack.value),
                    int(self.bus.err.value),
                    int(self.bus.read_data.value),
                )

        raise RuntimeError(f"WB timeout at addr=0x{txn.addr:08x}")

    async def pipelined(
        self,
        txns: list[Transaction],
        timeout: int | None = 200,
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

        cycles = 0
        while timeout is None or cycles < timeout:
            # Drive next request
            if issued < len(txns):
                txn = txns[issued]

                sel = self.full_sel if txn.sel is None else txn.sel

                self.bus.stb.value = 1
                self.bus.addr.value = txn.addr
                self.bus.write_data.value = txn.wdata
                self.bus.write_enable.value = txn.we
                self.bus.select.value = sel
            else:
                self.bus.stb.value = 0
                self.bus.write_data.value = 0
                self.bus.write_enable.value = 0
                self.bus.select.value = 0

            await RisingEdge(self.clk)
            cycles += 1

            # Request accepted
            if issued < len(txns) and not self.bus.stall.value:
                issued += 1

            # Response received
            if self.bus.ack.value or self.bus.err.value:
                responses.append(
                    (
                        int(self.bus.ack.value),
                        int(self.bus.err.value),
                        int(self.bus.read_data.value),
                    )
                )
                completed += 1

            # Done
            if completed == len(txns):
                self.bus.cyc.value = 0
                self.bus.stb.value = 0
                self.bus.write_enable.value = 0
                self.bus.select.value = 0

                return responses

        self.bus.cyc.value = 0
        self.bus.stb.value = 0
        self.bus.write_enable.value = 0
        self.bus.select.value = 0

        raise RuntimeError(
            f"WB timeout: issued={issued}, completed={completed}, expected={len(txns)}"
        )
