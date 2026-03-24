.PHONY: install test check demo

install:
	python -m pip install -e '.[test]'

test:
	python -m pytest

check:
	./scripts/check.sh

demo:
	python -m injection_lab.cli --system-prompt-file examples/system_prompt.txt --provider mock

