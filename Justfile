alias t := test
alias b := build
alias c := check

wave file:
    surfer {{justfile_directory()}}/target/waveform/{{file}}.vcd >& /dev/null & 

build:
    veryl build --quiet

check:
    veryl check --quiet

fmt:
    veryl fmt --quiet

test TEST *extra_args:
    veryl +nightly test {{justfile_directory()}}/src/tests/test_{{TEST}}.veryl \
        {{justfile_directory()}}/src/*.veryl \
        --wave --quiet {{extra_args}}

test_cargo TEST *extra_args:
    cargo r --manifest-path="$HOME/Desktop/veryl/Cargo.toml" --bin veryl -- \
        test {{justfile_directory()}}/src/tests/test_{{TEST}}.veryl \
        {{justfile_directory()}}/src/*.veryl \
         --wave --quiet {{extra_args}}