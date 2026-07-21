# Benchmark pipeline
# Usage: make run MODEL=iris

TESTS_CONFIG = testcases.yml
SIM_BUILD = sim_build/$(BENCH_NAME)
BUILD_DIR    = $(SIM_BUILD)/build
RESULTS_DIR  = results

.DEFAULT_GOAL := all

comma = ,
space = $(empty) $(empty)

# ---------------------------------------------------------------------------
# Run identity: timestamp + git state + short uuid.
# `?=` so a recursive submake inherits the exported value instead of
# generating a fresh one. `:=` inside so the shell runs exactly once.
# ---------------------------------------------------------------------------
GIT_SHA   := $(shell git rev-parse --short HEAD 2>/dev/null || echo nogit)
GIT_DIRTY := $(shell git diff --quiet 2>/dev/null || echo -dirty)
UUID_FRAG := $(shell uuidgen 2>/dev/null || cat /proc/sys/kernel/random/uuid 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())')
RUN_ID    := $(BENCH_NAME)_$(shell date -u +%Y%m%dT%H%M%SZ)-$(GIT_SHA)$(GIT_DIRTY)-$(shell echo $(UUID_FRAG) | cut -c1-8)
export RUN_ID

# ---------------------------------------------------------------------------
# Parse YAML for the selected model
# ---------------------------------------------------------------------------
ifndef BENCH_NAME
$(error BENCH_NAME is not set. Usage: make run MODEL=iris)
endif

_yq = $(shell yq 'explode(.) | .benches.$(BENCH_NAME).$1' $(TESTS_CONFIG) --yaml-fix-merge-anchor-to-spec)

NUM_CELLS       := $(call _yq,num_cells)
VOTE_FIFO_DEPTH := $(call _yq,vote_fifo_depth)
USE_SUPERSCALAR := $(call _yq,use_superscalar)

MODEL_NAME   := $(call _yq,model_name)
MODEL_PATH   := $(call _yq,model_path)
TEST_VECTORS := $(call _yq,test_vectors)
PLACEMENT_STRATEGY := $(call _yq,placement_strategy)
PARTITION_STRATEGY := $(call _yq,partition_strategy)

NUM_TREEs := $(call _yq,num_trees)
MAX_NODE  := $(call _yq,maxnode)

ifeq ($(NUM_CELLS),null)
$(error Bench '$(BENCH_NAME)' not found in $(TESTS_CONFIG))
endif

# ---------------------------------------------------------------------------
# Derived paths
# ---------------------------------------------------------------------------
MODEL_OUT     := $(shell realpath -m $(BUILD_DIR)/$(BENCH_NAME).ljmodel)
TEST_VECS_OUT := $(shell realpath -m $(BUILD_DIR)/$(BENCH_NAME).ljdata)
CACHE_OUTS    := $(foreach i,$(shell seq 0 $(shell echo $$(($(NUM_CELLS)-1)))),$(shell realpath -m $(BUILD_DIR)/$(BENCH_NAME)_$(i).ljcache))
DUMP_PATH := $(shell realpath -m $(SIM_BUILD)/$(BENCH_NAME).fst)

# One directory per run. RUN_OUT is relative to this makefile; RUN_OUT_INNER is
# the same directory as seen from cocotb, which runs one level deeper.
RUN_OUT       = $(RESULTS_DIR)/$(RUN_ID)
RUN_OUT_INNER = ../$(RUN_OUT)

STATS_OUT     := $(shell realpath -m $(RUN_OUT)/stats_$(BENCH_NAME).yml)
PERF_OUT      := $(shell realpath -m $(RUN_OUT)/perf_$(BENCH_NAME).yml)

# Surfer files
SURFER_TEMPLATE = surfer.template.ron
SURFER_OUT      := $(shell realpath -m $(RUN_OUT)/surfer_$(BENCH_NAME).surf.ron)

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
.PHONY: all run compile-model compile-caches compile-vectors clean clean-results run-id

$(BUILD_DIR):
	mkdir -p $@

$(RUN_OUT):
	mkdir -p $@

$(MODEL_OUT): $(TESTS_CONFIG) $(RUN_OUT) | $(BUILD_DIR)
	lumberjack-compiler build $(MODEL_PATH) \
		--output $(MODEL_OUT) \
		--num-cells $(NUM_CELLS) \
		--placement-strategy $(PLACEMENT_STRATEGY) \
		--partition-strategy $(PARTITION_STRATEGY) \
		--write-results $(STATS_OUT)
	# Add run_id to the generated file
	yq -i '{"run_id": "$(RUN_ID)"} * .' $(STATS_OUT)

$(CACHE_OUTS): $(TESTS_CONFIG) | $(BUILD_DIR)
	lumberjack-compiler build-cache-data $(MODEL_PATH) -a \
		--output-dir $(BUILD_DIR) \
		--prefix $(BENCH_NAME) \
		--num-cells $(NUM_CELLS) \
		--placement-strategy $(PLACEMENT_STRATEGY) \
		--partition-strategy $(PARTITION_STRATEGY)

$(TEST_VECS_OUT): $(TESTS_CONFIG) | $(BUILD_DIR)
	lumberjack-compiler build-test-vectors $(MODEL_PATH) --vectors $(TEST_VECTORS) --output $(TEST_VECS_OUT)

compile-model: $(MODEL_OUT)
compile-caches: $(CACHE_OUTS)
compile-vectors: $(TEST_VECS_OUT)

all: compile-model compile-caches compile-vectors

# Print the id for this invocation (useful for scripting / CI).
run-id:
	@echo $(RUN_ID)

run: all | $(RUN_OUT)
	@echo "RUN_ID=$(RUN_ID)"
	@echo "results -> $(RUN_OUT)/"
	WAVES=1 RUN_ID=$(RUN_ID) uv run pytest benchmark.py -s \
		-k test_run_benchmark \
		--bench-name=$(BENCH_NAME) \
		--model-name=$(MODEL_NAME) \
		--model-out=$(MODEL_OUT) \
		--model-path=$(MODEL_PATH) \
		--placement-strategy=$(PLACEMENT_STRATEGY) \
		--partition-strategy=$(PARTITION_STRATEGY) \
		--test-vecs=$(TEST_VECS_OUT) \
		--cache-files=$(subst $(space),$(comma),$(CACHE_OUTS)) \
		--perf-file=$(PERF_OUT) \
		--run-id=$(RUN_ID) \
		--num-trees=$(NUM_TREEs) \
		--max-node=$(MAX_NODE) \
		--vote-fifo-depth=$(VOTE_FIFO_DEPTH) \
		--use-superscalar=$(USE_SUPERSCALAR)
	sed 's|__DUMP_PATH__|$(DUMP_PATH)|g' $(SURFER_TEMPLATE) > $(SURFER_OUT)
	@printf "\033[32mOpen dump with\033[0m: surfer $$(realpath --relative-to=. $(DUMP_PATH)) -s $$(realpath --relative-to=. $(SURFER_OUT))\n"

clean:
	rm -rf $(BUILD_DIR) sim_build

clean-results:
	rm -rf $(RESULTS_DIR)