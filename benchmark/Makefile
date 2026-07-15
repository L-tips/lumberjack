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

ifeq ($(NUM_CELLS),null)
$(error Model '$(MODEL)' not found in $(TESTS_CONFIG))
endif

STRATEGY  := execution-aware
PARTITION := greedy

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

$(MODEL_OUT): $(TESTCASES) | $(BUILD_DIR)
	lumberjack-compiler build $(MODEL_PATH) --output $(MODEL_OUT) --num-cells $(NUM_CELLS) -s $(STRATEGY) -r $(PARTITION)

$(CACHE_OUTS): $(TESTCASES) | $(BUILD_DIR)
	lumberjack-compiler build-cache-data $(MODEL_PATH) --output-dir $(BUILD_DIR) --prefix $(MODEL) --num-cells $(NUM_CELLS) -s $(STRATEGY) -r $(PARTITION)

$(TEST_VECS_OUT): $(TESTCASES) | $(BUILD_DIR)
	lumberjack-compiler build-test-vectors $(MODEL_PATH) --vectors $(TEST_VECTORS) --output $(TEST_VECS_OUT)

compile-model: $(MODEL_OUT)
compile-caches: $(CACHE_OUTS)
compile-vectors: $(TEST_VECS_OUT)

all: compile-model compile-caches compile-vectors

run: all
	uv run pytest benchmark.py -s -v \
		-k test_run_benchmark \
		--model=$(MODEL) \
		--model-out=$(MODEL_OUT) \
		--test-vecs=$(TEST_VECS_OUT) \
		--cache-files=$(subst $(space),$(comma),$(CACHE_OUTS)) \
		--num-cells=$(NUM_CELLS)

clean:
	rm -rf $(BUILD_DIR) sim_build