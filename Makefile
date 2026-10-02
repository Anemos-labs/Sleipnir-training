# Sleipnir-training: generate, admit, scan, catalog.  `make help`
SLEIPNIR ?= $(HOME)/.cache/fx/sleipnir
JOBS ?= 2
CONC ?= 2

.PHONY: help build admit scan catalog dist check all
help:
	@echo "make build     run every generator, write corpus/ shards (JOBS=$(JOBS))"
	@echo "make admit     prove every task sound with 'sleipnir rl tasks check' (CONC=$(CONC))"
	@echo "make scan      decontamination scan against public benchmarks (run 'python3 tools/contam.py fetch' once)"
	@echo "make catalog   write catalog/index.jsonl and catalog/STATS.md"
	@echo "make dist      materialise ready-to-run tasks.jsonl + blobs/ + repos/ in dist/"
	@echo "make check     determinism: build twice and compare"

build:
	python3 tools/build.py --jobs $(JOBS)

check:
	python3 tools/build.py --jobs $(JOBS) --twice

admit:
	python3 tools/admit.py --sleipnir $(SLEIPNIR) --concurrency $(CONC)

scan:
	python3 tools/contam.py scan --write

catalog:
	python3 tools/catalog.py

dist:
	rm -rf dist && python3 tools/admit.py --sleipnir $(SLEIPNIR) --concurrency $(CONC) --no-write --dist dist
	python3 tools/catalog.py && python3 tools/split.py --tasks dist/tasks.jsonl
	@echo "run:  cd dist && sleipnir rl rollout --tasks tasks.jsonl --blobs blobs ..."

all: build admit scan catalog
