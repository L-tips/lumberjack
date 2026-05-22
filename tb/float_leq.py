import cocotb
from cocotb.triggers import Timer
import random
import numpy as np
import ml_dtypes

from utils import float_to_bf16_bits

SPECIAL_VALUES = np.array(
    [
        float('nan'),       # NaN
        float('inf'),       # Positive Infinity
        float('-inf'),      # Negative Infinity
        0.0,                # Positive Zero
        -0.0,               # Negative Zero
        1.1754944e-38,      # Smallest positive normal number 0x0080
        -1.1754944e-38,     # Smallest negative normal number 0x8080
        1.0,
        -1.0,
        3.3895314e+38,      # Largest positive normal number 0x7f7f
        -3.3895314e+38,     # Largest negative normal number 0xff7f
        9.1835496e-41,     # Smallest positive subnormal number 0x0001
        -9.1835496e-41,    # Smallest negative subnormal number 0x8001
    ],
    dtype = ml_dtypes.bfloat16
)

@cocotb.test()
async def test_sorting(dut):
    await Timer(1, unit="ns")
    
    # Generate random pairs of floats across the full range of f32
    float_pairs = [(random.uniform(-3.3895314e38, 3.3895314e38), random.uniform(-3.3895314e38, 3.3895314e38)) for _ in range(99_990)]

    # Convert to a (99990, 2) bfloat16 array, then view as tuples
    bf16_array = np.array(float_pairs, dtype=ml_dtypes.bfloat16)

    # As a list of tuples
    float_pairs = [tuple(row) for row in bf16_array]

    # Add special IEEE 754 values to the test set
    for (i, special_a) in enumerate(SPECIAL_VALUES):
        for special_b in SPECIAL_VALUES:
            random_pair = float_pairs[i]

            # Check the special values against eachother
            float_pairs.append((special_a, special_b))
            # Also check the special values against "normal" floats
            float_pairs.append((special_a, random_pair[0]))
            float_pairs.append((special_b, random_pair[1]))

    for pair in float_pairs:
        float_a_bits = float_to_bf16_bits(pair[0])
        float_b_bits = float_to_bf16_bits(pair[1])

        dut.a.value = float_a_bits
        dut.b.value = float_b_bits

        await Timer(1, unit="ns")

        expected_result = pair[0] <= pair[1]
        assert dut.leq.value == expected_result, f"Mismatch: {pair[0]} <= {pair[1]} (expected {expected_result}, got {dut.leq.value})"
