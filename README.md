# Lumberjack

## A hardware acceleration framework for random forests

The Lumberjack core is a hardware module designed to efficiently evaluate random forest machine learning models. It is implemented in [Veryl](https://veryl-lang.org) and intended for integration into SoCs, FPGAs, or ASICs. The accelerator offloads the computationally intensive task of traversing decision trees and aggregating their predictions, providing fast and deterministic inference for embedded and real-time applications.

# Getting started

## Dependencies

This project is written in [Veryl](https://veryl-lang.org), which is a modern hardware description language that compiles down to SystemVerilog.

### Building

To build the project, you will need:

- The [Veryl toolchain](https://veryl-lang.org/install/)

### Simulating

Additionally, to run the simulations and tests, you will need:

- [Verilator](https://verilator.org/guide/latest/install.html)
- [Cocotb](https://docs.cocotb.org/en/stable/install.html)

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

You can also run benchmarks with:

```sh
just bench <benchmark-name>
```

Or

```sh
just bench-all
```
