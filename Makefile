prefix=/usr/local
SOURCE_FILE=git_archive_all.py
TARGET_DIR=$(prefix)/bin
TARGET_FILE=$(TARGET_DIR)/git-archive-all

all:
	@echo "usage: make install"
	@echo "       make uninstall"
	@echo "       test"

test:
	python setup.py test

install:
	install -d -m 0755 $(TARGET_DIR)
	install -m 0755 $(SOURCE_FILE) $(TARGET_FILE)

uninstall:
	test -d $(TARGET_DIR) && \
	rm -f $(TARGET_FILE)
