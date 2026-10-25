#!/bin/sh
# Invoked in a disposable, network-isolated Docker container.
set -eu
mode=${1:-debug}
sh /harness/build.sh "$mode"
if test "$mode" = asan; then
    export CFLAGS='-O1 -g3 -fcommon -fno-omit-frame-pointer -fsanitize=address'
    export LDFLAGS='-fsanitize=address'
    export RUNNER_VARIABLES_ORDER=EGPCS
fi
export ASAN_OPTIONS=detect_leaks=0:abort_on_error=1:allocator_may_return_null=1
sh /harness/build-probe.sh
native_option=
fpm_option=
if test "$mode" = legacy; then
    native_option=--legacy
    fpm_option=--expect-baseline
fi
python3 /harness/native-invariants.py --php /work/install/bin/php \
    --module /work/probe/modules/security_probe.so --output /work/logs/native.json $native_option
python3 /harness/fpm-invariants.py --fpm /work/install/sbin/php-fpm \
    --output /work/logs/fpm.json $fpm_option
if test "$mode" = legacy; then exit 0; fi
if test "$mode" = asan; then
    export USE_ZEND_ALLOC=0 RUNNER_VARIABLES_ORDER=EGPCS
    python3 /harness/fpm-invariants.py --fpm /work/install/sbin/php-fpm \
        --system-allocator --output /work/logs/fpm-system-allocator.json
fi
