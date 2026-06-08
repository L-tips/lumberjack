import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

import utils
from utils import n_cycles, read_hex


async def reset(dut):
    await RisingEdge(dut.clk)

    # Init and reset
    dut.rst.value = 0

    dut.start.value = 0
    dut.tree_header_addr.value = 0

    await RisingEdge(dut.clk)
    # Release reset
    dut.rst.value = 1

    await RisingEdge(dut.clk)

async def init_memory(dut, mem_file):
    mem_data = read_hex(mem_file)
    mem_data = utils.into_chunks_le(mem_data, 64)

    dut.ram_port.enable.value = True
    dut.ram_port.byte_write_enable.value = 0xff

    for addr, data in enumerate(mem_data):
        dut.ram_port.address.value = addr
        dut.ram_port.write_data.value = data
        await RisingEdge(dut.clk)

    dut.ram_port.enable.value = False
    dut.ram_port.write_data.value = 0
    dut.ram_port.byte_write_enable.value = 0

@cocotb.test()
async def tree_test(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    test_cases = ["single_tree_2n_aligned.hex", "single_tree_2n_misaligned.hex"]
    for file in test_cases:
        await reset(dut)
        # Start by writing the data into the tree cache
        # through the external RAM port
        await init_memory(dut, file)

        # Always return 11.0_f32 as the feature
        dut.feature_buses[0].data.value = 0x4130

        # ...and start tree prediction
        dut.start.value = 1
        dut.tree_header_addr.value = 0

        await RisingEdge(dut.clk)

        dut.start.value = 0
        assert dut.tree.busy.value == 1
        # State = read_header
        print(dut.tree.state.value)
        # assert dut.tree.state.value == 1

        # Test that we can't write data to the RAM while it's busy
        dut.ram_port.byte_write_enable.value = 0xff

        # Takes 2 cycles to fetch header + evaluate the full node
        await n_cycles(dut.clk, 2)

        # Writes should not be enabled
        assert dut.tree.tree_cache_bus_demuxed.byte_write_enable.value == 0

        # We're taking the right branch, which is
        # a node pointer
        assert dut.tree.next_read_addr.value == 0x3

        # Which means we're going to be evaluating
        # another node
        assert dut.tree.next_ready.value == 0
        assert dut.tree.next_busy.value == 1

        # Now we're fetching the next node
        await RisingEdge(dut.clk)

        assert dut.tree.state.value == 2

        # Writes should still not be enabled until no longer busy
        assert dut.tree.tree_cache_bus_demuxed.byte_write_enable.value == 0
        # Even though the RAM port is trying to write
        assert dut.ram_port.byte_write_enable.value == 0xff

        # Make sure we don't overwrite the RAM when busy goes low
        dut.ram_port.byte_write_enable.value = 0

        # Again, takes a total of 1 cycle to fetch + evaluate
        # the node
        await n_cycles(dut.clk, 1)

        # Result should now be available
        assert dut.ready.value == 1
        assert dut.busy.value == 0
        assert dut.tree.state.value == 0
        # According to the tree and the input
        # feature, predicted class should
        # be 2
        assert dut.prediction.value == 2

        # Now let's try to take another branch.
        # Always return 6.0_f32 as the input feature
        dut.feature_buses[0].data.value = 0x40C0
        dut.start.value = 1

        await RisingEdge(dut.clk)

        dut.start.value = 0

        # The first node is directly a prediction.
        # Entire prediction sequence should complete
        # in a total of 3 cycles after START has been
        # set.
        await n_cycles(dut.clk, 3)

        assert dut.ready.value == 1
        assert dut.busy.value == 0
        # Predicted class should be 0
        assert dut.prediction.value == 0

        # Intentionally don't reset start to 0.
        # Prediction should never show ready.
        dut.start.value = 1
        await n_cycles(dut.clk, 7)

        # Even though the state is idle,
        assert dut.tree.state.value == 0
        # the status still isn't ready
        assert dut.ready.value == 0
        assert dut.busy.value == 1

        await n_cycles(dut.clk, 2)


@cocotb.test()
async def rejects_circular_trees(dut):
    # Start a 10 ns clock
    cocotb.start_soon(Clock(dut.clk, 10, unit="ns").start())

    await reset(dut)
    await init_memory(dut, "forest_1t_2n_circular.hex")

    # Always return 9.0_f32 as the feature
    dut.feature_buses[0].data.value = 0x4110
    dut.tree_header_addr.value = 0x01

    # ...and start tree prediction
    dut.start.value = 1

    await RisingEdge(dut.clk)

    dut.start.value = 0
    assert dut.tree.busy.value == 1

    # Takes 2 cycle to fetch header+evaluate the full node
    await n_cycles(dut.clk, 2)

    assert dut.tree.state.value == 2

    # Now we're fetching + evaluating the next node
    await RisingEdge(dut.clk)

    assert dut.tree.state.value == 2

    # Again, takes a total of 1 cycle to evaluate
    # the node
    await n_cycles(dut.clk, 1)

    # Result should now be available
    assert dut.ready.value == 0
    assert dut.busy.value == 0
    assert dut.error.value == 1

    await n_cycles(dut.clk, 1)

    # State won't change until next START
    assert dut.ready.value == 0
    assert dut.busy.value == 0
    assert dut.error.value == 1
