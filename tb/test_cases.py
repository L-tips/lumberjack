from collections import Counter
from dataclasses import dataclass
from typing import Sequence


def get_winner(predictions: Counter):
    """Get highest voted class, along with its number of votes (smallest key wins ties)"""
    winner = max(predictions.keys(), key=lambda k: (predictions[k], -k))
    votes = predictions[winner]
    return (winner, votes)


@dataclass(frozen=True)
class TestCase:
    hexfile: str
    cache_mem_ranges: Sequence[range]
    features: Sequence[int]
    # num_trees: int
    # expect_error: bool = False
    # expected_prediction: Optional[int] = None
    expected_votes: Counter
    max_cycles: int = 200

    def __post_init__(self):
        object.__setattr__(self, "num_trees", sum(self.expected_votes.values()))
        winner, votes = get_winner(self.expected_votes)
        object.__setattr__(self, "expected_prediction", winner)
        object.__setattr__(self, "expected_votes", votes)

    def winning_vote(self):
        get_winner(self.expected_votes)


TC_ALIGNED_1CELL = TestCase(
    hexfile="forest_1c_2t_6n_aligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    cache_mem_ranges=[range(0x10, 0x60)],
    expected_votes=Counter({1: 2, 2: 1}),
)

TC_MISALIGNED_1CELL = TestCase(
    hexfile="forest_1c_2t_6n_misaligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    cache_mem_ranges=[range(0x10, 0x60)],
    # expected_prediction=1,
    expected_votes=Counter({1: 2}),
    # num_trees=2,
)

TC_ALIGNED_2CELLS = TestCase(
    hexfile="forest_2c_2t_6n_aligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    cache_mem_ranges=[range(0x10, 0x30), range(0x30, 0x50)],
    # expected_prediction=1,
    expected_votes=Counter({1: 2}),
    # num_trees=2,
)

TC_2CELLS_ASYMMETRICAL = TestCase(
    hexfile="forest_1c_2t_6n_aligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    cache_mem_ranges=[range(0x10, 0x50), range(0x50, 0xE0)],
    # expected_prediction=1,
    expected_votes=Counter({1: 2}),
    # num_trees=2,
)

TC_MISALIGNED_2CELLS = TestCase(
    hexfile="forest_2c_2t_6n_misaligned.hex",
    features=[0x4110, 0x4130, 0x4110],
    cache_mem_ranges=[range(0x10, 0x40), range(0x40, 0x60)],
    # expected_prediction=1,
    expected_votes=Counter({1: 2}),
    # num_trees=2,
)
