import cocotb
from cocotb.triggers import RisingEdge
import struct
import numpy as np
import ml_dtypes

def binary_to_hex(bin_str):
    # Convert binary string to hexadecimal
    hex_str = hex(int(str(bin_str), 2))[2:]
    hex_str = hex_str.zfill(8)
    return hex_str.upper()


def float_to_bits(f):
    return struct.unpack(">I", struct.pack(">f", f))[0]

# Convert a native python float into a bitwise representation of the bfloat16 format
def float_to_bf16_bits(f):
    x = np.array(f, dtype = ml_dtypes.bfloat16)
    return int(x.view(np.uint16))


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

"""Chunk data into the correct width and initialize memory. Assumes the data is stored in little-endian format."""
def init_mem_le(mem, hexfile):
    word_bits = _get_num_bits(mem)
    word_bytes = (word_bits + 7) // 8

    byte_list = read_hex(hexfile)
    offset = 0

    for i in range(0, len(byte_list), word_bytes):
        chunk = byte_list[i:i + word_bytes]
        if len(chunk) < word_bytes:
            chunk = chunk + [0] * (word_bytes - len(chunk))

        value = int.from_bytes(bytes(chunk), byteorder="little", signed=False)
        mem[offset].value = value
        offset += 1

def into_chunks_le(data_bytes, width):
    bytes_per_word = (width + 7) // 8
    mem_chunks = []
    for i in range(0, len(data_bytes), bytes_per_word):
        chunk = data_bytes[i:i+bytes_per_word]
        if len(chunk) < width / bytes_per_word:
            chunk = chunk + [0]*(bytes_per_word - len(chunk))
        value = int.from_bytes(bytes(chunk), byteorder="little", signed=False)
        mem_chunks.append(value)

    return mem_chunks

"""Read data from a .hex file into an array of byte-sized ints"""
def read_hex(hexfile):
    mem = []
    with open(hexfile, "r", encoding="UTF-8") as file:
        hexfile = file.read()

    for raw_data in hexfile.splitlines():
        # Strip comments
        str_data = raw_data.split("//")[0].strip()
        # Remove whitespace between byte chunks
        str_data = ''.join(str_data.split())
        if str_data != "":
            if len(str_data) % 2 != 0:
                raise ValueError(f"Invalid hex line length: {str_data}")
            for i in range(0, len(str_data), 2):
                mem.append(int(str_data[i:i + 2], 16))

    return mem

def _get_num_bits(mem):
    return len(mem[0])


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
