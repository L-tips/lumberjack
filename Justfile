alias t := test
alias ta := test-all
alias b := build
alias c := check
alias ba := bench-all

build:
    veryl build --quiet

wave file:
    surfer target/waveform/{{file}}.fst -s {{file}}.surf.ron >& /dev/null & 

check:
    veryl check --quiet

fmt:
    veryl fmt --quiet

[working-directory: 'benchmark/']
bench NAME BENCH_SET="benches":
    just build
    make run BENCH_NAME={{NAME}} BENCH_SET={{BENCH_SET}}

# Run all declared benchmarks in parallel
[working-directory: 'benchmark/']
bench-all BENCH_SET="benches":
    #!/usr/bin/env bash
    set -euo pipefail
    just build
    yq 'explode(.) | .{{BENCH_SET}} | keys | .[]' testcases.yml --yaml-fix-merge-anchor-to-spec | \
        parallel -j$(($(nproc) - 2)) just bench {} {{BENCH_SET}} >/dev/null

[working-directory: 'benchmark/']
clean-bench:
    rm -rf sim_build

[working-directory: 'benchmark/']
clean-bench-results:
    rm -rf results/

[working-directory: 'benchmark/']
wave-bench:
    surfer sim_build/bench.fst -s benchmark.surf.ron >&/dev/null &

test TEST *extra_args:
    uv run veryl test tb/test_{{TEST}}.veryl \
        src/*.veryl \
        src/tree/*.veryl \
        src/forest/*.veryl \
        src/ibex_bus/*.veryl \
        tb/common/*.veryl \
        --wave --quiet {{extra_args}}

test-all *extra_args:
    uv run veryl test --wave --quiet {{extra_args}}
