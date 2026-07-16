# Benchmark pipeline
# Usage: make run MODEL=iris
TESTS_CONFIG = testcases.yml
BUILD_DIR    = build

.DEFAULT_GOAL := all

comma = ,
space = $(empty) $(empty)

# ---------------------------------------------------------------------------
# Parse YAML for the selected model
# ---------------------------------------------------------------------------
ifndef MODEL
$(error MODEL is not set. Usage: make run MODEL=iris)
endif

_yq = $(shell yq '.models.$(MODEL).$1' $(TESTS_CONFIG))

NUM_CELLS    := $(call _yq,num_cells)
MODEL_PATH   := $(call _yq,model_path)
TEST_VECTORS := $(call _yq,test_vectors)
PLACEMENT_STRATEGY := $(call _yq,placement_strategy)
PARTITION_STRATEGY := $(call _yq,partition_strategy)

ifeq ($(NUM_CELLS),null)
$(error Model '$(MODEL)' not found in $(TESTS_CONFIG))
endif

# ---------------------------------------------------------------------------
# Derived paths
# ---------------------------------------------------------------------------
MODEL_OUT     = $(BUILD_DIR)/$(MODEL).ljmodel
TEST_VECS_OUT = $(BUILD_DIR)/$(MODEL).ljdata
CACHE_OUTS    = $(foreach i,$(shell seq 0 $(shell echo $$(($(NUM_CELLS)-1)))),$(BUILD_DIR)/$(MODEL)_$(i).ljcache)

# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------
.PHONY: all run compile-model compile-caches compile-vectors clean

$(BUILD_DIR):
	mkdir -p $@

$(MODEL_OUT): $(TESTS_CONFIG) | $(BUILD_DIR)
	lumberjack-compiler build $(MODEL_PATH) \
		--output $(MODEL_OUT) \
		--num-cells $(NUM_CELLS) \
		--placement-strategy $(PLACEMENT_STRATEGY) \
		--partition-strategy $(PARTITION_STRATEGY)

$(CACHE_OUTS): $(TESTS_CONFIG) | $(BUILD_DIR)
	lumberjack-compiler build-cache-data $(MODEL_PATH) -a \
		--output-dir $(BUILD_DIR) \
		--prefix $(MODEL) \
		--num-cells $(NUM_CELLS) \
		--placement-strategy $(PLACEMENT_STRATEGY) \
		--partition-strategy $(PARTITION_STRATEGY)

$(TEST_VECS_OUT): $(TESTS_CONFIG) | $(BUILD_DIR)
	lumberjack-compiler build-test-vectors $(MODEL_PATH) --vectors $(TEST_VECTORS) --output $(TEST_VECS_OUT)

compile-model: $(MODEL_OUT)
compile-caches: $(CACHE_OUTS)
compile-vectors: $(TEST_VECS_OUT)

all: compile-model compile-caches compile-vectors

run: all
	WAVES=1 uv run pytest benchmark.py -s \
		-k test_run_benchmark \
		--model=$(MODEL) \
		--model-out=$(MODEL_OUT) \
		--model-path=$(MODEL_PATH) \
		--placement-strategy=$(PLACEMENT_STRATEGY) \
		--partition-strategy=$(PARTITION_STRATEGY) \
		--test-vecs=$(TEST_VECS_OUT) \
		--cache-files=$(subst $(space),$(comma),$(CACHE_OUTS)) \
		--perf-file=../perf_$(MODEL).yml

clean:
	rm -rf $(BUILD_DIR) sim_build