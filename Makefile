PACK ?= ecommerce
PRESET ?= tiny
SEED ?= 42
OUT ?= ./out
generate:
	python -m vynqe_synth generate --pack $(PACK) --preset $(PRESET) --seed $(SEED) --out $(OUT)
validate:
	python -m vynqe_synth validate --pack $(PACK) --out $(OUT)
test:
	python -m pytest -q tests
all: generate validate test
