# Lumberjack

## A hardware acceleration framework for random forests
The Lumberjack core is a hardware module designed to efficiently evaluate random forest machine learning models. It is implemented in [Veryl](https://veryl-lang.org) and intended for integration into SoCs, FPGAs, or ASICs. The accelerator offloads the computationally intensive task of traversing decision trees and aggregating their predictions, providing fast and deterministic inference for embedded and real-time applications.

# Getting started

## Dependencies

This project is written in [Veryl](https://veryl-lang.org), which is a modern hardware description language that compiles down to SystemVerilog.

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

## WIP: Docker image

Alternatively, you can use the pre-built Docker image that includes the toolchain needed to build/simulate the project (not yet available).

# Design and Architecture

The random forest (RF) evaluator is comprised of three main blocks: the tree evaluator, which evaluates a single tree in the forest, the forest evaluator, which orchestrates the tree evaluator, and the interface block, which presents control and status registers (CSRs) via a standard, memory-mapped interface. It natively supports the Wishbone Pipelined protocol, as described in the [Wishbone B4 specification](https://cdn.opencores.org/downloads/wbspec_b4.pdf).

| ![Node layout](images/lumberjack_arch_v0.1.svg) |
|:--:| 
| *General core architecture* |

**Top-Level Module: `ForestTop`**

### Interface signals
* Clock and reset signals.
* Wishbone bus slave (control port) for accessing control and status registers.
* Wishbone bus master (DMA port) for accessing RAM (forest and feature data).
* Interrupt output for signaling completion or error.

### Submodules
* **CSR Interface (`csr.veryl`):** Handles configuration, status, and control via registers.
* **Forest Engine (`forest.veryl`):** Orchestrates the evaluation of all trees in the forest, and aggregates the results.
* **Tree Predictor (`tree.veryl`):** Evaluates a single decision tree.
* **Floating Point Comparator (`float_leq.veryl`):** Compares feature values to split thresholds using the 32-bit IEEE754 format.
* **(Optional) Bus Adapters (`ibex_bus/`):** Adapts Wishbone to Ibex bus if needed.
* **(Optional) Self Arbiter (`self_arbiter.veryl`):** Manages bus access between control and DMA ports if the system memory interface doesn't
  handle multiple masters internally.

### Operating Principle

* **Initialization:** the host processor configures the accelerator via the CSR interface:
  * Loads the forest structure and feature data into RAM.
  * Sets the number of trees, feature count, and start addresses.
  * Enables the accelerator by setting the ENABLE bit in the control register.

* **Feature Fetch:** upon receiving the ENABLE signal, the accelerator:
  * Reads the feature vector from RAM using DMA.
  * Caches the features for fast access during tree evaluation.

* **Tree Evaluation:** the forest module iterates over each tree in the forest:
  * For each tree, the tree module traverses nodes starting from the root.
  * At each node, the feature value is compared to the split threshold using the FloatLeq comparator.
  * The result determines whether to follow the left or right branch.
  * Traversal continues until a leaf node (prediction) is reached.

* **Voting and Aggregation**
  * Each tree produces a class prediction.
  * The accelerator aggregates votes from all trees into a scratchpad RAM.
  * The class with the highest vote count is selected as the final prediction.

* **Completion and Interrupt:** when all trees have been evaluated:
  * The final prediction and vote counts are written to status registers.
  * The READY signal is asserted.
  * An interrupt is generated to notify the host processor.

* **Host Interaction**
  * The host reads the prediction and status via the CSR interface.
  * The accelerator can be reconfigured or reset for subsequent inferences.

### Key Features
* RAM is accessed via DMA.
* Number of trees, features, and memory addresses are adjustable at compile-time.
* All 32-bit IEEE754 float cases for number comparison are handled, including NaN, ±Inf, and ±0.0.
* Interrupts for completion or error signaling.
* (Optional) Bus arbitrator ensures safe access to shared memory resources when the host doesn't provide one.

### Error Handling
* Illegal forest structure detection: Emits errors if an illegal forest structure is detected.
  In practice, the evaluator checks that each node only points to nodes with a higher index than itself.
* (**TODO**) NaN/Inf Detection: The comparator detects and handles special float values.
* (**TODO**) Bus Errors: Errors on RAM access are flagged in status registers.

### Performance
The integrated cycle counter can be used for debugging or benchmarking.

### Example Workflow
1. Load Forest and Features: Host writes forest and feature data to RAM.
1. Configure Accelerator: Host sets CSRs (number of trees, addresses, etc.).
1. Start Evaluation: Host sets ENABLE bit.
1. Wait for Interrupt: Host waits for completion interrupt.
1. Read Results: Host reads prediction and vote counts from CSRs.

# Integration

## Random Forest memory format

The RF evaluator uses a variation of the memory representation described in \[1\]. The `forest-optimizer` tool ([available on Github](https://github.com/L-tips/embedded-random-forest/)) can be used to convert random forests to the format expected by this core.

* **Forest Header:** Contains metadata (number of trees and feature count).
* **Node Layout:** Each node encodes split feature, threshold, branch pointers, and prediction flags.
* **Feature Vector:** Stored as a contiguous array of 32-bit floats in memory.

| ![Node layout](images/node_layout.svg) |
|:--:| 
| *Layout of a node (bytes)* |

| ![Split flags](images/split_flags.svg) |
|:--:| 
| *Layout of the IDX field (bits)* |

## Integrating Lumberjack to an existing design

An example integration to the [Ibex core](https://github.com/lowRISC/ibex) can be found here: https://github.com/L-tips/ibex-demo-system/tree/lumberjack-peripheral. Note that we offer protocol converters between the native Ibex memory Wishbone pipelined interconnects in the `src/ibex_bus` directory. For integration on simple systems which do not include a multi-master memory bus arbiter, we also offer a self-arbiter module (`src/self_arbiter.veryl`), which can be used to manage bus access between the Control and DMA ports. The self-arbiter always gives priority to the Control port.

The core can be imported as a native Veryl library (preferred), or as a FuseSOC core. If using FuseSOC, an intermediate, manual (for now) build step is necessary to compile the Veryl source into generated SystemVerilog.

## Software integration

We offer an SVD specification of the CSR map, which can be used to automatically generate software bindings. See `lumberjack_peripheral.svd`.

## Register map

| Offset | Name          | Description                                 | Access      | Reset Value  |
|--------|--------------|---------------------------------------------|-------------|--------------|
| 0x0000 | CTRL         | Control and status                          | RW / RO     | 0x0000_0000  |
| 0x0004 | CTRL_SET     | Set individual bits of CTRL                 | RW / RO     | 0x0000_0000  |
| 0x0008 | CTRL_CLR     | Clear individual bits of CTRL               | RW / RO     | 0x0000_0000  |
| 0x000C | NUM_TREES    | Number of trees in forest                   | RW          | 0x0000_0000  |
| 0x0010 | FOREST_START | Address of first node in the forest         | RW          | 0x0000_0000  |
| 0x0014 | NUM_FEATURES | Number of features in forest                | RW          | 0x0000_0000  |
| 0x0018 | FEATURES_START | Address of first feature for prediction   | RW          | 0x0000_0000  |
| 0x001C | PREDICTION   | Predicted class                             | RO          | 0x0000_0000  |
| 0x0020 | VOTES        | Number of votes for predicted class         | RO          | 0x0000_0000  |
| 0x0024 | INTEN_SET    | Set bits of interrupt enable register       | RW          | 0x0000_0000  |
| 0x0028 | INTEN_CLR    | Clear bits of interrupt enable register     | RW          | 0x0000_0000  |
| 0x002C | INTFLAG      | Interrupt flags                             | RW          | 0x0000_0000  |
| 0x0030 | PERF         | Performance statistics                      | RO          | 0x0000_0000  |

## Register Details

### CTRL (0x0000) – Control and status
```
31                  2   1     0
+--------------------+------+----+
|        Reserved    | BUSY | EN |
+--------------------+------+----+
```
- **0 EN (RW):** Accelerator enable  
  - 0: Accelerator disabled  
  - 1: Accelerator enabled  
- **1 BUSY (RO):** Accelerator busy status  
  - 0: Accelerator idle  
  - 1: Accelerator busy  

---

### CTRL_SET (0x0004) – Set bits in CTRL
```
31                  2   1     0
+--------------------+---- -+----+
|        Reserved    | BUSY | EN |
+--------------------+---- -+----+
```
- **0 EN (RW):** Writing 1 sets the Accelerator Enable bit (enables accelerator). Writing 0 has no effect.
- **1 BUSY (RO):** Accelerator busy status (read-only)

---

### CTRL_CLR (0x0008) – Clear bits in CTRL
```
31                  2   1     0
+--------------------+---- -+----+
|        Reserved    | BUSY | EN |
+--------------------+---- -+----+
```
- **0 EN (RW):** Writing 1 clears the Accelerator Enable bit (disables accelerator). Writing 0 has no effect
- **1 BUSY (RO):** Accelerator busy status (read-only)

---

### NUM_TREES (0x000C)
```
31                             0
+--------------------------------+
|              NUM               |
+--------------------------------+
```
- **[31:0] NUM (RW):** Number of trees in forest

---

### FOREST_START (0x0010)
```
31                             0
+--------------------------------+
|             ADDR               |
+--------------------------------+
```
- **[31:0] ADDR (RW):** Address of the first node in the forest

---

### NUM_FEATURES (0x0014)
```
31                             0
+--------------------------------+
|              NUM               |
+--------------------------------+
```
- **[31:0] NUM (RW):** Number of features in the forest

---

### FEATURES_START (0x0018)
```
31                             0
+--------------------------------+
|             ADDR               |
+--------------------------------+
```
- **[31:0] ADDR (RW):** Address of the first feature used for prediction

---

### PREDICTION (0x001C)
```
31                             0
+--------------------------------+
|             CLASS              |
+--------------------------------+
```
- **[31:0] CLASS (RO):** Predicted class

---

### VOTES (0x0020)
```
31                             0
+--------------------------------+
|              NUM               |
+--------------------------------+
```
- **[31:0] NUM (RO):** Votes for the predicted class

---

### INTEN_SET (0x0024)
```
31                 2   1     0
+-------------------+-----+-----+
|     Reserved      | ERR | RDY |
+-------------------+-----+-----+
```
- **0 READY (RW):** Writing 1 sets the Ready Interrupt Enable bit (enables the interrupt). Writing 0 has no effect.
- **1 ERROR (RW):** Writing 1 sets the Error Interrupt Enable bit (enables the interrupt). Writing 0 has no effect.

---

### INTEN_CLR (0x0028)
```
31                 2   1     0
+-------------------+-----+-----+
|     Reserved      | ERR | RDY |
+-------------------+-----+-----+
```
- **0 READY (RW):** Writing 1 clears the Ready Interrupt Enable bit (disables the interrupt). Writing 0 has no effect.
- **1 ERROR (RW):** Writing 1 clears the Error Interrupt Enable bit (disables the interrupt). Writing 0 has no effect.

---

### INTFLAG (0x002C)
```
31                 2   1     0
+-------------------+-----+-----+
|     Reserved      | ERR | RDY |
+-------------------+-----+-----+
```
- **0 READY (RW):** Ready interrupt flag. This flag is set when a classification is completed.
  This flag is cleared when reading the PREDICTION register.
  Writing a zero to this bit has no effect.
  Writing a one to this bit will clear the flag.
- **1 ERROR (RW):** Error interrupt flag. This flag is set when any error is detected.
  Writing a zero to this bit has no effect.
  Writing a one to this bit will clear the flag.

---

### PERF (0x0030)
```
31                             0
+--------------------------------+
|            CYCCNT              |
+--------------------------------+
```
- **[31:0] CYCCNT (RO):** Cycle count for the last prediction.



## Optimization

Note that this project is still a work-in-progress, and is expected to evolve over time. As the project evolves and is optimized further breaking changes may (read: will) occur to the interfaces exposed by the core, the expected forest memory representation, and more.

# References

\[1\] J. Beaurivage, M. A. Ouameur, and F. Domingue, "A Memory Representation of Random Forests Optimized for Resource-Limited Embedded Devices," IEEE Embedded Systems Letters, pp. 1–1, 2025, doi: [10.1109/LES.2025.3574563](https://doi.org/10.1109/LES.2025.3574563).