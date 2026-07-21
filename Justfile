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
bench NAME:
    just build
    make run BENCH_NAME={{NAME}}

[working-directory: 'benchmark/']
bench-all:
    #!/usr/bin/env bash
    set -euo pipefail
    just build
    for bench in $(yq 'explode(.) | .benches | keys | .[]' testcases.yml); do
        echo "Running bench: $bench"
        just bench $bench
    done

[working-directory: 'benchmark/']
clean-bench:
    rm -rf build sim-build

[working-directory: 'benchmark/']
clean-bench-results:
    rm -rf results/

[working-directory: 'benchmark/']
wave-bench:
    surfer sim_build/dump.fst -s benchmark.surf.ron >&/dev/null &

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
