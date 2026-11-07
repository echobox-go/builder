PY      ?= python3
PROFILE ?= niklas
# Base profile for `make render`: a real archiso profile on eb-build, or a
# test fixture (default) anywhere else.
FIXTURE  = $(shell $(PY) -c "import yaml;print({'arch':'releng','cachyos':'cachyos'}[yaml.safe_load(open('profiles/users/$(PROFILE)/profile.yaml'))['base']])")
BASE_DIR ?= build/fixture-$(FIXTURE)
# The ebox repo, cloned next to this one.
EBOX_DIR ?= ../ebox

SHELL_SCRIPTS = build-iso.sh infra/proxmox/create-guests.sh infra/build/setup-build-vm.sh

.PHONY: test validate pytest shellcheck render clean
test: validate pytest shellcheck

validate:
	$(PY) render.py validate profiles/users/*/profile.yaml

pytest:
	$(PY) -m pytest -q

shellcheck:
	shellcheck -x $(SHELL_SCRIPTS)

build/fixture-%:
	$(PY) tests/fixtures.py $* $@

render: $(if $(filter build/fixture-%,$(BASE_DIR)),$(BASE_DIR))
	$(PY) render.py render profiles/users/$(PROFILE)/profile.yaml \
		--base-dir $(BASE_DIR) --ebox-dir $(EBOX_DIR) --out build/$(PROFILE)/profile --force

clean:
	rm -rf build .pytest_cache
