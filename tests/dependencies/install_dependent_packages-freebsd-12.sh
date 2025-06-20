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

# This script provides the packages needed to run the unit tests in a "baseline" FreeBSD 12 environment.  (See the similarly named script in ${top_srcdir}/dependencies/ for meaning of "baseline".)
# Note that this script will insist on the path to Bash being /bin/bash.

set -x
set -e

sudo pkg install --yes \
  bash \
  gmake \
  openjdk11-jre \
  py37-virtualenv \
  wget

if [ ! -x /bin/bash ]; then
  cd /bin
    test -x /usr/local/bin/bash
    sudo ln -s \
      /usr/local/bin/bash \
      bash
  cd -
fi
test -x /bin/bash
