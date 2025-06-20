#!/bin/sh

# Portions of this file contributed by NIST are governed by the
# following statement:
#
# This software was developed at the National Institute of Standards
# and Technology by employees of the Federal Government in the course
# of their official duties. Pursuant to Title 17 Section 105 of the
# United States Code, this software is not subject to copyright
# protection within the United States. NIST assumes no responsibility
# whatsoever for its use by other parties, and makes no guarantees,
# expressed or implied, about its quality, reliability, or any other
# characteristic.
#
# We would appreciate acknowledgement if the software is used.

# This script lists dependencies for running this repository's code base in a "baseline" FreeBSD 12 environment, where only these configurations were made after the first boot of a new system:
# * Installing 'pkg'.
# * Using 'pkg' to install packages 'git', 'sudo', and 'vim'.
#   - Note that 'vim' pulls in the package for Python 3.
# To run the tests, see the similar script ${top_srcdir}/tests/dependencies/install_dependent_packages-freebsd-12.sh.

set -x
set -e

sudo pkg install --yes \
  libxslt
