PREFIX=/usr/local
BIN=git-archive-all

all:
	@echo "usage: make install"
	@echo "       make uninstall"

install:
	install -d -m 0755 $(prefix)/bin
	install -m 0755 $(BIN) $(prefix)/bin

uninstall:
	test -d $(prefix)/bin && \
	cd $(prefix)/bin && \
	rm -f ${BIN}
