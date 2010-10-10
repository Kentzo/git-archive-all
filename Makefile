PREFIX ?= /usr/local
BIN = git-archive-all

install:
	@echo "... installing to $(PREFIX)/bin"
	cp -f $(BIN) $(PREFIX)/bin

uninstall:
	rm -f $(PREFIX)/bin/$(BIN)

.PHONY: install uninstall