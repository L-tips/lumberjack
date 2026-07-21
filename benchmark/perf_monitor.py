import cocotb
from cocotb.triggers import FallingEdge
from dataclasses import dataclass, asdict
from pathlib import Path
import yaml


@dataclass
class CellStats:
    cell_idx: int
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
class PerfStats:
    cells: list[CellStats]
    globals: GlobalStats

    def report(self, path: Path | None = None, extra_data: dict | None = None):
        perf_data = {
            "cells": [asdict(c) for c in self.cells],
            "global": asdict(self.globals),
        }

        if extra_data:
            d = extra_data
            d.update(perf_data)
        else:
            d = extra_data

        # Log to cocotb
        for c in self.cells:
            cocotb.log.info(f"[Cell {c.cell_idx}] {asdict(c)}")
        cocotb.log.info(f"[Global] {asdict(self.globals)}")

        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w") as f:
                yaml.dump(d, f, default_flow_style=False, sort_keys=False)
            cocotb.log.info(f"Perf report written to {path}")


async def _cell_perf_task(
    clk, busy, cell_dut, superscalar_stages, stats: CellStats, stop_event
):
    """
    Counts cycles in a cell when the parent evaluator shows busy.
    Stops when stop_event is triggered.
    """
    while not stop_event.is_set():
        # Sample on falling edge to get the correctly registered values
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

            # State::idle
            if cell_dut.tree.state.value == 0:
                stats.idle += 1
                continue

            # State::hold_prediction
            if cell_dut.tree.state.value == 3:
                stats.stall += 1
                continue

            # Any non-idle or hold cycle is a new mem fetch
            stats.mem_fetches += 1

            if cell_dut.tree.discard_prefetch.value:
                stats.fetch_discards += 1

            if cell_dut.tree.prefetch_miss.value:
                stats.branch_pred_miss += 1

            if cell_dut.tree.dbg_superscalar_hit.value:
                stats.superscalar_hits += 1
                stats.useful_node_evaluations += superscalar_stages
                stats.total_node_evaluations += superscalar_stages
            elif cell_dut.tree.dbg_superscalar_miss.value:
                stats.superscalar_misses += 1
                stats.useful_node_evaluations += 1
                stats.total_node_evaluations += superscalar_stages


async def _global_perf_task(clk, dut, stats: GlobalStats, stop_event):
    """
    Counts cycles from the moment it starts until IRQ goes high.
    """
    while not stop_event.is_set():
        # Sample on falling edge to get the correctly registered values
        await FallingEdge(clk)
        if dut.busy.value == 1:
            stats.inference_cycles += 1
        if dut.evaluator.start_eval.value:
            stats.predictions += 1


class PerfMonitor:
    """
    Usage:
        monitor = PerfMonitor(dut.clk, busy_signals, dut.irq, num_cells=N)
        monitor.start()
        # ... run inference ...
        stats = await monitor.stop()
        stats.report()
    """

    def __init__(self, clk, dut):
        """
        clk          : clock signal
        dut          : forest top module
        """
        self.clk = clk
        self.dut = dut
        superscalar = dut.USE_SUPERSCALAR.value

        if superscalar:
            self.superscalar_stages = 2
        else:
            self.superscalar_stages = 1

        self._stop_event = cocotb.triggers.Event()
        self._tasks = []

        self._tree_cells = self.dut.evaluator.inst_tree_cells
        self._cell_stats = [CellStats(cell_idx=i) for i in range(len(self._tree_cells))]
        self._global_stats = GlobalStats()

    def start(self):
        """Launch all background monitor coroutines."""
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

    async def stop(
        self, report_path: Path | None = None, extra_data: dict | None = None
    ) -> PerfStats:
        self._stop_event.set()
        for t in self._tasks:
            t.cancel()
        self._tasks.clear()

        stats = PerfStats(cells=self._cell_stats, globals=self._global_stats)
        stats.report(path=report_path, extra_data=extra_data)
        return stats
