alias t := test
alias ta := test-all
alias b := build
alias c := check

build:
    veryl build --quiet

wave file:
    surfer target/waveform/{{file}}.fst -s {{file}}.surf.ron >& /dev/null & 

check:
    veryl check --quiet

fmt:
    veryl fmt --quiet

[working-directory: 'benchmark/']
bench:
    just build
    uv run pytest benchmark.py -s

wave-bench:
    surfer benchmark/sim_build/dump.fst -s benchmark/benchmark.surf.ron >&/dev/null &

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
