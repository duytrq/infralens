.PHONY: build-ApiFunction build-CleanupFunction build-AnalysisFunction

build-ApiFunction:
	uv pip install --python 3.12 --require-hashes --only-binary :all: --no-deps --target "$(ARTIFACTS_DIR)" -r requirements.txt
	cp -R src/infralens_backend "$(ARTIFACTS_DIR)/"

build-CleanupFunction: build-ApiFunction

build-AnalysisFunction: build-ApiFunction
