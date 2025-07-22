alias t := test
alias ta := test-all
alias b := build
alias c := check

build:
    veryl build --quiet

wave file:
    surfer {{justfile_directory()}}/target/waveform/{{file}}.fst -s {{justfile_directory()}}/{{file}}.surf.ron >& /dev/null & 

check:
    veryl check --quiet

fmt:
    veryl fmt --quiet

test TEST *extra_args:
    veryl test {{justfile_directory()}}/src/tests/test_{{TEST}}.veryl \
        {{justfile_directory()}}/src/*.veryl \
        {{justfile_directory()}}/src/ibex_bus/*.veryl \
        --wave --quiet {{extra_args}}

test-all *extra_args:
    veryl test --wave --quiet {{extra_args}}
