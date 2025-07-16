alias t := test
alias ta := test-all
alias b := build
alias c := check

wave file:
    surfer {{justfile_directory()}}/target/waveform/{{file}}.fst >& /dev/null & 

build:
    veryl build --quiet

check:
    veryl check --quiet

fmt:
    veryl fmt --quiet

test TEST *extra_args:
    veryl test {{justfile_directory()}}/src/tests/test_{{TEST}}.veryl \
        {{justfile_directory()}}/src/*.veryl \
        --wave --quiet {{extra_args}}

test-all *extra_args:
    veryl test --wave --quiet {{extra_args}}
