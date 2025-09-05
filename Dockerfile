FROM rust:1.89-alpine

RUN apk add --no-cache build-base verilator python3 python3-dev py3-pip
RUN cargo install verylup
RUN verylup setup
RUN pip install --break-system-packages cocotb