import cocotb
from cocotb.triggers import Timer
import random

from utils import float_to_bits

SPECIAL_VALUES = [
    float('nan'),       # NaN
    float('inf'),       # Positive Infinity
    float('-inf'),      # Negative Infinity
    0.0,                # Positive Zero
    -0.0,               # Negative Zero
    1.0,                # Smallest positive normal number
    -1.0,               # Smallest negative normal number
    3.4028235e38,       # Largest positive normal number
    -3.4028235e38,      # Largest negative normal number
    1.17549435e-38,     # Smallest positive subnormal number
    -1.17549435e-38,    # Smallest negative subnormal number
]

# Test that an unknown instruction reverts to default
@cocotb.test()
async def test_sorting(dut):
    await Timer(1, unit="ns")
    
    # Generate random pairs of floats across the full range of f32
    random_pairs = [(random.uniform(-3.4028235e38, 3.4028235e38), random.uniform(-3.4028235e38, 3.4028235e38)) for _ in range(990)]

    # Add special IEEE 754 values to the test set
    for (i, special_a) in enumerate(SPECIAL_VALUES):
        for special_b in SPECIAL_VALUES:
            random_pair = random_pairs[i]

            # Check the special values against eachother
            random_pairs.append((special_a, special_b))
            # Also check the special values against "normal" floats
            random_pairs.append((special_a, random_pair[0]))
            random_pairs.append((special_b, random_pair[1]))

    for pair in random_pairs:
        float_a_bits = float_to_bits(pair[0])
        float_b_bits = float_to_bits(pair[1])

        dut.a.value = float_a_bits
        dut.b.value = float_b_bits

        await Timer(1, unit="ns")

        expected_result = pair[0] <= pair[1]
        assert dut.leq.value == expected_result, f"Mismatch: {pair[0]} <= {pair[1]} (expected {expected_result}, got {dut.leq.value})"
