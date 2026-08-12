# -*- coding: utf-8-unix -*-

check:
	flake8 bin/sloppie
	flake8 bin/sloppie.in
	flake8 conftest.py
	flake8 slop

clean:
	rm -rf build
	rm -rf dist
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	find . -type d -name .pytest_cache -prune -exec rm -rf {} +

test:
	pytest -xs slop

.PHONY: check clean test
