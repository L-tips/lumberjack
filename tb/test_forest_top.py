import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, FallingEdge, ClockCycles, Combine

from wb_driver import Transaction, WbMaster

from test_cases import TC_ALIGNED_2CELLS, TC_MISALIGNED_2CELLS

import utils
from utils import read_hex

WB_ADDR_WIDTH = 32
WB_DATA_WIDTH = 32


def debug_mark(dut, value):
    dut.dbg_mark.value = value


async def do_reset(dut, control_bus, cache_buses, cycles: int = 1):
    dut.rst.value = 0

    control_bus.reset()
    for bus in cache_buses:
        bus.reset()

    await ClockCycles(dut.clk, cycles)

    dut.rst.value = 1
    await ClockCycles(dut.clk, cycles)


async def fill_tree_cache(port, mem_file, rng):
    mem_data = read_hex(mem_file)
    bus_width = port.data_width

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

    txns = []

    for word_idx in range(start_word, end_word):
        addr = word_idx * bytes_per_word - rng.start
        txns.append(Transaction(addr=addr, we=True, sel=bwe, wdata=mem_words[word_idx]))

    await port.pipelined(txns)


@cocotb.test()
async def forest_top_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())
    await RisingEdge(dut.clk)

    control_port = WbMaster(dut.clk, dut.control_bus)
    cell_cache_ports = list(
        map(lambda bus: WbMaster(dut.clk, bus), dut.cell_cache_ports)
    )

    test_cases = [TC_ALIGNED_2CELLS, TC_MISALIGNED_2CELLS]

    for tc in test_cases:
        print(f"RUNNING TEST CASE: {tc.hexfile}")

        # Init and reset
        await do_reset(dut, control_port, cell_cache_ports)

        # Write forest to tree evaluator cells
        tasks = []
        for cell_idx, mem_range in enumerate(tc.cache_mem_ranges):
            tasks.append(
                cocotb.start_soon(
                    fill_tree_cache(cell_cache_ports[cell_idx], tc.hexfile, mem_range)
                )
            )
        await Combine(*tasks)

        # Write features
        txns = []
        for word_idx, word in enumerate(utils.pack_16b_to_32b(tc.features)):
            txns.append(Transaction(addr=0x40 + word_idx * 4, wdata=word, we=True))
        await control_port.pipelined(txns)

        txns = [
            # Enable the interrupt
            Transaction(addr=0x24, wdata=0b1, sel=0b1, we=True),
            # enable
            Transaction(addr=0x0, wdata=1, sel=0b1, we=True),
        ]
        await control_port.pipelined(txns)

        await RisingEdge(dut.clk)

        # Now read the status register while the evaluator
        # is working.
        _, _, rdata = await control_port.transaction(Transaction(addr=0x0, sel=0b1111))

        # BUSY and ENABLE should be set
        assert rdata == 0b11

        # Wait for eval to finish
        await FallingEdge(dut.forest_top.busy)
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)

        # Forest should predict class #1 with 2 votes
        winner, votes = tc.winning_vote()
        assert dut.forest_top.prediction.value == winner
        assert dut.forest_top.num_votes.value == votes

        # Interrupt line should be set
        assert dut.interrupt_line.value == 1

        # Clear the interrupt by reading prediction
        _, _, prediction = await control_port.transaction(Transaction(addr=0x1C))

        assert prediction == winner
        assert dut.interrupt_line.value == 0

        # Also read the number of votes
        _, _, num_votes = await control_port.transaction(Transaction(addr=0x20))
        assert num_votes == 2

        await RisingEdge(dut.clk)

        # Restart a second time
        await control_port.transaction(Transaction(addr=0x0, wdata=1, sel=0b1, we=True))

        await FallingEdge(dut.forest_top.busy)
        await RisingEdge(dut.clk)
        await RisingEdge(dut.clk)

        assert dut.interrupt_line.value == 1

        # Clear the interrupt by writing a 1 to INTFLAG
        await control_port.transaction(
            Transaction(addr=0x2C, wdata=0b1, sel=0b1, we=True)
        )

        assert dut.interrupt_line.value == 0

        # Disable the interrupt
        await control_port.transaction(
            Transaction(addr=0x28, wdata=0b1, sel=0b1, we=True)
        )

        # Restart for a 3rd time
        await control_port.transaction(Transaction(addr=0x0, wdata=1, sel=0b1, we=True))

        await FallingEdge(dut.forest_top.busy)
        await RisingEdge(dut.clk)

        # Interrupt should not fire
        assert dut.interrupt_line.value == 0

        # Check that the control/status signals
        # are what we expect, and that the HW doesn't
        # unexpectedly change them from under our noses
        for _ in range(0, 10):
            assert dut.forest_top.busy.value == 0
            assert dut.forest_top.ready.value == 1
            assert dut.forest_top.start_stb.value == 0
