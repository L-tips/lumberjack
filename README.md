# Lumberjack

## A hardware acceleration framework for random forests

# Getting started

## Dependencies

This project is written in [Veryl](https://veryl-lang.org). It is a modern hardware description language, which compiles down to SystemVerilog.

### Building

To build the project, you will need:

* The [Veryl toolchain](https://veryl-lang.org/install/)

### Simulating

Additionally, to run the simulations and tests, you will need:

* [Verilator](https://verilator.org/guide/latest/install.html)
* [Cocotb](https://docs.cocotb.org/en/stable/install.html)

To view the simulation waveforms, we recommend [surfer](https://gitlab.com/surfer-project/surfer). It is also offered as [a webapp](https://app.surfer-project.org/). [gtkwave](https://github.com/gtkwave/gtkwave) is also a good option.

Finally, we also include a `Justfile` with pre-written commands. You can install [Just](https://github.com/casey/just) to make use of these commands. This is entirely
optional, and is simply included for a better developer experience. In particular, you can run:

```sh
just test forest_top # To run a specific test (check available tests in src/tests)
just test-all # To run all tests
```

Otherwise, to run all tests, use:

```sh
veryl test --wave --quiet
```

The waveform outputs are available in `target/waveform`.

**Note**: We highly recommend using a Linux distribution to build/simulate. Builds and simulations remain untested on other operating systems. In particular,
if using Windows, we recommend using [WSL](https://learn.microsoft.com/en-us/windows/wsl/install). Dependencies should preferably be installed with your
distribution's package manager.

## Docker image

Alternatively, you can use the pre-built Docker image that includes the toolchain needed to build/simulate the project (WIP -- not yet available).

# Design and Architecture

The random forest (RF) evaluator is comprised of three main blocks: the tree evaluator, which evaluates a single tree in the forest, the forest evaluator, which schedules
the tree evaluator, and the interface block, which presents control and status registers (CSRs) via a standard, memory-mapped interface. It natively supports the Wishbone
Pipelined protocol, as described in the [Wishbone B4 specification](https://cdn.opencores.org/downloads/wbspec_b4.pdf).

The core has two memory ports: one slave port, called the Control port, which exposes the CSRs to the system, as well as one master port, called the DMA port, which is
used to fetch the forest's nodes from the system's memory.

# Integration

## Forest model memory format

The RF evaluator uses a variation of the memory representation described in \[1\]. The `forest-optimizer` tool ([available on Github](https://github.com/L-tips/embedded-random-forest/)) can be used to convert random forests to the format expected by this core.

**TODO**: Full forest layout, including header

**TODO**: Header layout

| ![Node layout](images/node_layout.svg) |
|:--:| 
| *Layout of a node (bytes)* |

| ![Split flags](images/split_flags.svg) |
|:--:| 
| *Layout of the IDX field (bits)* |

## Registers

## Optimization

Note that this project is still a work-in-progress, and is expected to evolve over time. Breaking changes may (will) occur to the interfaces exposed by the core, the expected
forest memory representation, and more.

# References

\[1\] J. Beaurivage, M. A. Ouameur, and F. Domingue, "A Memory Representation of Random Forests Optimized for Resource-Limited Embedded Devices," IEEE Embedded Systems Letters, pp. 1–1, 2025, doi: [10.1109/LES.2025.3574563](https://doi.org/10.1109/LES.2025.3574563).