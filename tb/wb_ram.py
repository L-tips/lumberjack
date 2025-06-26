import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge

@cocotb.coroutine
async def reset(dut):
    # Reset is high to conform to wishbone spec
    dut.rst.value = 1
    # Asserting RESET does not set the memory to 0, just like in real hardware.
    # We do it manually for testing purposes
    dut.ram.mem.value = [0] * len(dut.ram.mem.value)
    await RisingEdge(dut.clk)

    dut.wb.cyc.value = 0
    dut.wb.stb.value = 0
    dut.wb.select.value = 0
    dut.wb.write_enable.value = 0
    dut.wb.addr.value = 0
    dut.wb.write_data.value = 0

    await RisingEdge(dut.clk)

    dut.rst.value = 0
    await RisingEdge(dut.clk)

    print("reset done !")

def assert_ack(dut):
    assert dut.wb.ack.value == 1
    assert dut.wb.err.value == 0

def assert_read(dut, address, expected):
    assert_ack(dut)
    assert dut.wb.read_data.value == expected, f"Error at address {address}: expected {hex(expected)}, got {hex(dut.wb.read_data.value)}"

def start_read_txn(dut, address, byte_select):
    dut.wb.cyc.value = 1
    dut.wb.stb.value = 1
    dut.wb.write_enable = 0
    dut.wb.select.value = byte_select
    dut.wb.addr.value = address

def start_write_txn(dut, address, data, byte_select):
    dut.wb.cyc.value = 1
    dut.wb.stb.value = 1
    dut.wb.write_enable = 1
    dut.wb.select.value = byte_select
    dut.wb.addr.value = address
    dut.wb.write_data.value = data

def finish_txn(dut):
    dut.wb.cyc.value = 0
    dut.wb.stb.value = 0


@cocotb.test()
async def memory_data_test(dut):
    # INIT MEMORY
    cocotb.start_soon(Clock(dut.clk, 1, units="ns").start())
    await reset(dut)
        
    # Test: Write and read back data
    test_data = [
        (0, 0xDEADBEEF),
        (4, 0xCAFEBABE),
        (8, 0x12345678),
        (12, 0xA5A5A5A5)
    ]


    # ======================
    # BASIC WORD WRITE TEST
    # ======================
    for address, data in test_data:
        start_write_txn(dut, address, data, 0b1111)

        await RisingEdge(dut.clk)

        # Immediately
        # send a read request (pipeline mode)
        finish_txn(dut)
        start_read_txn(dut, address, 0b1111)

        # Verify by reading back
        await RisingEdge(dut.clk)

        # Write request has been acknowledged
        assert_ack(dut)
        # Pipeline in another read request to read back
        # by leaving cyc and stb unchanged

        await RisingEdge(dut.clk)

        assert_read(dut, address, data)

    # ==============
    # WRITE TEST #2
    # ==============
    for i in range(0,40,4):
        address = i
        data = i
        start_write_txn(dut, address, data, 0b1111)

        await RisingEdge(dut.clk)

        # Write request has been acknowledged
        assert_ack(dut)

        # Immediately start read and
        # check that setting write_data doesn't affect RAM state
        finish_txn(dut)
        start_read_txn(dut, address, 0b1111)
        dut.wb.write_data = 0xFAFABEBE

        await RisingEdge(dut.clk)

        # Verify by reading back
        await RisingEdge(dut.clk)
        assert_read(dut, address, data)

        # Read back a second time for fun
        await RisingEdge(dut.clk)
        assert_read(dut, address, data)

    # ==============
    # NO WRITE TEST
    # ==============
    for i in range(0,40,4):
        start_read_txn(dut, i, 0b1111)
        # Check that setting write_data doesn't affect RAM state
        dut.wb.write_data.value = 0xBEBECACA
        await RisingEdge(dut.clk)

        # Verify by reading back
        await RisingEdge(dut.clk)
        assert_read(dut, i, i)

    # ===============
    # BYTE WRITE TEST
    # ===============
    
    for byte_enable in range(16):
        await reset(dut) # we reset memory..
        # generate mask from byte_enable
        mask = 0
        for j in range(4):
            if (byte_enable >> j) & 1:
                mask |= (0xFF << (j * 8))

        print(f"mask: {mask}")

        for address, data in test_data:
            start_write_txn(dut, address, data, byte_enable)

            # write
            await RisingEdge(dut.clk)

            finish_txn(dut)
            # Read all bytes in word for good measure
            start_read_txn(dut, address, 0b1111)


            await RisingEdge(dut.clk)

            # Verify by reading back
            await RisingEdge(dut.clk)

            # Check that we're only touching the concerned bytes
            assert dut.wb.ack.value == 1
            assert dut.wb.err.value == 0
            assert dut.wb.read_data.value & mask == data & mask
            assert dut.wb.read_data.value & ~mask == dut.ram.mem.value[int(address/4)] & ~mask
