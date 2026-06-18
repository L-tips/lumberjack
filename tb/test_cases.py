from dataclasses import dataclass
from typing import Optional, Sequence

@dataclass(frozen=True)
class TestCase:
    hexfile: str
    cache_mem_ranges: Sequence[range]
    features: Sequence[int]
    num_trees: int
    expect_error: bool = False
    expected_prediction: Optional[int] = None
    expected_votes: Optional[int] = None
    max_cycles: int = 200

    def __post_init__(self):
        if not self.expect_error:
            if self.expected_prediction is None or self.expected_votes is None:
                raise ValueError(
                    "Non-error test cases must provide expected_prediction and expected_votes."
                )

TC_ALIGNED_1CELL = TestCase(
    hexfile="forest_2t_6n_aligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x70)],
    expected_prediction=1,
    expected_votes=2,
)

TC_MISALIGNED_1CELL = TestCase(
    hexfile="forest_2t_6n_misaligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x50)],
    expected_prediction=1,
    expected_votes=2,
)

TC_ALIGNED_2CELLS = TestCase(
    hexfile="forest_2t_6n_aligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x40), range(0x40, 0x70)],
    expected_prediction=1,
    expected_votes=2,
)

TC_MISALIGNED_2CELLS = TestCase(
    hexfile="forest_2t_6n_misaligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x30), range(0x30, 0x50)],
    expected_prediction=1,
    expected_votes=2,
)

TC_CIRCULAR_2CELLS = TestCase(
    hexfile="forest_2t_6n_circular.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x30), range(0x30, 0x70)],
    expect_error=True,
)

TC_CIRCULAR_1CELL = TestCase(
    hexfile="forest_2t_6n_circular.hex",
    features=[0x4110, 0x4130, 0x4110],
    num_trees=2,
    cache_mem_ranges=[range(0x10, 0x70)],
    expect_error=True,
)