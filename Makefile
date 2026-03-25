APP_DIR := forgechannels
VENV_PYTHON := $(APP_DIR)/.venv/bin/python
VENV_PIP := $(APP_DIR)/.venv/bin/pip

.PHONY: run dry-run test install

run:
	cd $(APP_DIR) && ./start.sh

dry-run:
	cd $(APP_DIR) && ./start.sh --dry-run

test:
	$(MAKE) install
	cd $(APP_DIR) && .venv/bin/python -m pytest tests/

install:
	cd $(APP_DIR) && test -d .venv || python3 -m venv .venv
	$(VENV_PIP) install -r $(APP_DIR)/requirements.txt
