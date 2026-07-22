# perf_monitor.py
import cocotb
from cocotb.triggers import FallingEdge
from dataclasses import dataclass, asdict, field
from pathlib import Path
import numpy as np
from ml_dtypes import bfloat16
from ruamel.yaml import YAML
from ruamel.yaml.comments import CommentedSeq


def _flow_seq(items) -> CommentedSeq:
    seq = CommentedSeq(items)
    seq.fa.set_flow_style()
    return seq


@dataclass
class CellStats:
    index: int
    accelerator_busy: int = 0
    cell_busy: int = 0
    vote_pending: int = 0
    total_vote_commits: int = 0
    superscalar_hits: int = 0
    superscalar_misses: int = 0
    mem_fetches: int = 0
    useful_node_evaluations: int = 0
    total_node_evaluations: int = 0
    idle: int = 0
    stall: int = 0
    fetch_discards: int = 0
    branch_pred_miss: int = 0


@dataclass
class GlobalStats:
    inference_cycles: int = 0
    predictions: int = 0


@dataclass
class SampleStats:
    sample_idx: int
    features: list[int]  # raw bf16 bits as hex strings
    expected_pred: int
    expected_votes: int
    cell_stats: list[CellStats]
    global_stats: GlobalStats

    def to_dict(self) -> dict:
        return {
            "index": self.sample_idx,
            "features": [
                float(bfloat16(np.uint16(f).view(bfloat16))) for f in self.features
            ],
            "expected_pred": self.expected_pred,
            "expected_votes": self.expected_votes,
            "cell_stats": [asdict(c) for c in self.cell_stats],
            "global_stats": asdict(self.global_stats),
        }


@dataclass
class PerfReport:
    metadata: dict
    samples: list[SampleStats] = field(default_factory=list)

    def write(self, path: Path):
        samples = []

        for i, r in enumerate(self.samples):
            d = r.to_dict()
            d["features"] = _flow_seq(d["features"])
            samples.append(d)

        doc = {**self.metadata, "test_samples": samples}

        path.parent.mkdir(parents=True, exist_ok=True)
        yaml = YAML()
        yaml.default_flow_style = False
        with open(path, "w") as f:
            yaml.dump(doc, f)
        cocotb.log.info(f"Perf report written to {path}")


# ---------------------------------------------------------------------------
# Background tasks
# ---------------------------------------------------------------------------


async def _cell_perf_task(
    clk, busy, cell_dut, superscalar_stages, stats: CellStats, stop_event
):
    while not stop_event.is_set():
        await FallingEdge(clk)
        if busy.value:
            stats.accelerator_busy += 1

            if cell_dut.cell_controller.busy_o.value:
                stats.cell_busy += 1

            if cell_dut.cell_controller.vote_ack.value:
                stats.total_vote_commits += 1

            if (
                cell_dut.cell_controller.vote_valid.value
                and not cell_dut.cell_controller.vote_ack.value
            ):
                stats.vote_pending += 1

            if cell_dut.tree.state.value == 0:
                stats.idle += 1
                continue

            if cell_dut.tree.state.value == 3:
                stats.stall += 1
                continue

            stats.mem_fetches += 1

            if cell_dut.tree.discard_prefetch.value:
                stats.fetch_discards += 1
                continue

            if cell_dut.tree.prefetch_miss.value:
                stats.branch_pred_miss += 1
                continue

            if cell_dut.tree.dbg_superscalar_hit.value:
                stats.superscalar_hits += 1
                stats.useful_node_evaluations += superscalar_stages
                stats.total_node_evaluations += superscalar_stages
            else:
                if cell_dut.tree.dbg_superscalar_miss.value:
                    stats.superscalar_misses += 1
                stats.useful_node_evaluations += 1
                stats.total_node_evaluations += superscalar_stages


async def _global_perf_task(clk, dut, stats: GlobalStats, stop_event):
    while not stop_event.is_set():
        await FallingEdge(clk)
        if dut.busy.value == 1:
            stats.inference_cycles += 1
        if dut.evaluator.start_eval.value:
            stats.predictions += 1


class PerfMonitor:
    def __init__(self, clk, dut):
        self.clk = clk
        self.dut = dut
        self.superscalar_stages = 2 if dut.USE_SUPERSCALAR.value else 1
        self._tree_cells = dut.evaluator.inst_tree_cells
        self._num_cells = len(self._tree_cells)
        self._stop_event = cocotb.triggers.Event()
        self._tasks = []
        self._reset_stats()

    def _reset_stats(self):
        self._cell_stats = [CellStats(index=i) for i in range(self._num_cells)]
        self._global_stats = GlobalStats()

    def start(self):
        self._reset_stats()
        self._stop_event.clear()

        for i, cell in enumerate(self._tree_cells):
            self._tasks.append(
                cocotb.start_soon(
                    _cell_perf_task(
                        self.clk,
                        self.dut.evaluator.busy,
                        cell,
                        self.superscalar_stages,
                        self._cell_stats[i],
                        self._stop_event,
                    )
                )
            )

        self._tasks.append(
            cocotb.start_soon(
                _global_perf_task(
                    self.clk, self.dut, self._global_stats, self._stop_event
                )
            )
        )

    async def stop(self, vec, sample_idx: int) -> SampleStats:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

        run = SampleStats(
            sample_idx,
            features=[int(f.view(np.uint16)) for f in vec.features],
            expected_pred=vec.expected_prediction,
            expected_votes=vec.expected_num_votes,
            cell_stats=self._cell_stats,
            global_stats=self._global_stats,
        )

        return run
