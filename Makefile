.PHONY: all clean test

all: check_ontap_bundle check_ontap

check_ontap_bundle:
	pip install --no-cache-dir --no-compile --target allinone .
	mv allinone/bin/check_ontap allinone/__main__.py
	python -m zipapp  -c -p '/usr/bin/env python3' allinone
	rm -rf allinone
	mv allinone.pyz check_ontap_bundle

check_ontap:
	mkdir build
	cp -av checkontap build/checkontap
	mv build/checkontap/cli.py build/__main__.py
	( cd build/; python -m zipapp -c --output ../check_ontap -p '/usr/bin/env python3' . )
	rm -rf build

dist: pyproject.toml
	python3 -m flit build
	chmod a+r dist/*

.PHONY: clean
clean:
	rm -rf build allinone check_ontap_bundle check_ontap zip check_ontap.zip build check_ontap.egg-info dist

.PHONY: upload-test
upload-test: dist
	python3 -m twine upload --repository testpypi --config-file .pypirc dist/*

.PHONY: upload-prod
upload-prod: dist
	python3 -m twine upload dist/* --config-file .pypirc
