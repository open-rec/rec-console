PYTHON ?= python

.PHONY: format lint install-hooks

format:
	$(PYTHON) -m isort rec_console
	$(PYTHON) -m autopep8 --in-place --recursive rec_console

lint:
	$(PYTHON) -m isort --check-only --diff rec_console
	$(PYTHON) -m autopep8 --diff --exit-code --recursive rec_console
	$(PYTHON) -m pycodestyle rec_console

install-hooks:
	$(PYTHON) -m pre_commit install --install-hooks
