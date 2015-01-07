all: suid-python

suid-python: suid-python.c
	gcc -o $@ $<

install:
	install -o root -g root -m 4755 suid-python $(DESTDIR)/usr/bin/suid-python
	install -o root -g root -m 0644 suid-python.1 $(DESTDIR)/usr/share/man/man1/suid-python.1
	install -o root -g root -m 0644 suid-example.py $(DESTDIR)/usr/share/doc/suid-python/examples/suid-example.py

uninstall:
	rm -f $(DESTDIR)/suid-python $(DESTDIR)/usr/share/man/man1/suid-python.1

clean:
	rm -f suid-python
	fakeroot debian/rules clean

package:
	dpkg-buildpackage -us -uc -rfakeroot
