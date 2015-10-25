prefix=/usr/local
EXEC_FILES=git-archive-all

all:
	@echo "usage: make install"
	@echo "       make uninstall"

test:
	pep8 --max-line-length=120 git-archive-all

install:
	install -d -m 0755 $(prefix)/bin
	install -m 0755 $(EXEC_FILES) $(prefix)/bin

uninstall:
	test -d $(prefix)/bin && \
	cd $(prefix)/bin && \
	rm -f ${EXEC_FILES}
