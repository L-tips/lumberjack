import cocotb

def binary_to_hex(bin_str):
    # Convert binary string to hexadecimal
    hex_str = hex(int(str(bin_str), 2))[2:]
    hex_str = hex_str.zfill(8)
    return hex_str.upper()

@cocotb.coroutine
async def init_memory(mem, hexfile):
    with open(hexfile, "r", encoding="UTF-8") as file:
        hexfile = file.read()

    offset = 0
    for raw_data in hexfile.splitlines() :
        str_data = raw_data.split("/")[0].strip()
        # Skip empty lines
        if str_data != "":
            data = int(str_data, 16)
            mem[offset].value = data
            offset += 1