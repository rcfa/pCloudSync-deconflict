# Makefile for pCloudSync-deconflict
# Build standalone executables for distribution

PYTHON := python3
PYINSTALLER := pyinstaller
SOURCE := pCloudSync-deconflict.py
APP_NAME := pCloudSync-deconflict
VERSION := 1.0.0

.PHONY: all clean build-macos build-universal install-deps install uninstall

all: build-universal

install-deps:
	@echo "Installing build dependencies..."
	$(PYTHON) -m pip install pyinstaller

build-macos: install-deps
	@echo "Building macOS executable..."
	$(PYINSTALLER) --onefile \
		--name $(APP_NAME) \
		--clean \
		--noconfirm \
		--console \
		--osx-bundle-identifier com.deconflict.pcloudsync \
		$(SOURCE)
	@echo "Build complete! Executable at: dist/$(APP_NAME)"

build-universal: install-deps
	@echo "Building universal macOS binary (Intel + Apple Silicon)..."
	$(PYINSTALLER) --onefile \
		--name $(APP_NAME) \
		--clean \
		--noconfirm \
		--console \
		--target-arch universal2 \
		--osx-bundle-identifier com.deconflict.pcloudsync \
		$(SOURCE)
	@echo "Universal build complete! Executable at: dist/$(APP_NAME)"

test:
	@echo "Running tests on built executable..."
	./dist/$(APP_NAME) --help
	./dist/$(APP_NAME) --dry-run .

clean:
	@echo "Cleaning build artifacts..."
	rm -rf build/ dist/ __pycache__/ *.spec
	find . -name "*.pyc" -delete
	find . -name "*.pyo" -delete

install: build-universal
	@echo "Installing $(APP_NAME) to /usr/local/bin..."
	@if [ ! -d /usr/local/bin ]; then \
		echo "Creating /usr/local/bin directory..."; \
		sudo mkdir -p /usr/local/bin; \
	fi
	@sudo cp dist/$(APP_NAME) /usr/local/bin/
	@sudo chmod 755 /usr/local/bin/$(APP_NAME)
	@echo "Installation complete! $(APP_NAME) is now available in your PATH."

uninstall:
	@echo "Uninstalling $(APP_NAME) from /usr/local/bin..."
	@sudo rm -f /usr/local/bin/$(APP_NAME)
	@echo "Uninstall complete!"

package: build-universal
	@echo "Creating distribution package..."
	mkdir -p dist/pCloudSync-deconflict-$(VERSION)-macos-universal
	cp dist/$(APP_NAME) dist/pCloudSync-deconflict-$(VERSION)-macos-universal/
	cp README.md dist/pCloudSync-deconflict-$(VERSION)-macos-universal/ 2>/dev/null || echo "No README.md found"
	cd dist && tar -czf pCloudSync-deconflict-$(VERSION)-macos-universal.tar.gz pCloudSync-deconflict-$(VERSION)-macos-universal
	@echo "Package created: dist/pCloudSync-deconflict-$(VERSION)-macos-universal.tar.gz"