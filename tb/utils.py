import cocotb
from cocotb.triggers import RisingEdge
import struct


def binary_to_hex(bin_str):
    # Convert binary string to hexadecimal
    hex_str = hex(int(str(bin_str), 2))[2:]
    hex_str = hex_str.zfill(8)
    return hex_str.upper()


def float_to_bits(f):
    return struct.unpack(">I", struct.pack(">f", f))[0]


def float_to_hex(f):
    as_bytes = float_to_bits(f)
    # Convert the integer to a zero-padded 8-character hex string
    return f"0x{as_bytes:08x}"


async def init_memory(mem, hexfile):
    with open(hexfile, "r", encoding="UTF-8") as file:
        hexfile = file.read()

    offset = 0
    for raw_data in hexfile.splitlines():
        str_data = raw_data.split("/")[0].strip()
        # Skip empty lines
        if str_data != "":
            data = int(str_data, 16)
            mem[offset].value = data
            offset += 1


async def wait_with_timeout(clk, signal, value, max_cycles):
    count = 0
    while signal.value != value:
        count += 1
        if count > max_cycles:
            raise TimeoutError
        await RisingEdge(clk)

    return count


async def n_cycles(clk, n):
    for _ in range(n):
        await RisingEdge(clk)
