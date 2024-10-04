#!/bin/bash

set -e
trap 'echo "[ERROR] Error in line $LINENO when executing: $BASH_COMMAND"' ERR

# only run on adsb.im images
if ! [[ -f /opt/adsb/os.adsb.feeder.image ]]; then
    exit 0
fi

function vm_tweaks () {

    if grep </proc/swaps -qs -F -v -e zram -e Filename; then
        echo "$(date -u +"%FT%T.%3NZ") zram-swap.sh: unexpected non zram swap found, not tweaking kernel vm settings"
        return
    fi

    # for more info on the following tweaks, see this kernel reference:
    # https://www.kernel.org/doc/html/latest/admin-guide/sysctl/vm.html

    # for zram swap, most guides reommend the following:
    # swappiness 200, watermark_scale_factor 125, watermark_boost_factor 0
    #
    # swappiness
    # if zram is the only swap, increase swappiness (default swappiness 60)
    # zram guides propose 200 but that seems excessive
    echo 100 > /proc/sys/vm/swappiness

    # watermark_scale_factor
    # This factor controls the aggressiveness of kswapd. It defines the amount
    # of memory left in a node/system before kswapd is woken up and how much
    # memory needs to be free before kswapd goes back to sleep.
    # 60: 0.6 percent free memory (default 10 / 0.1%)
    echo 60 > /proc/sys/vm/watermark_scale_factor

    # watermark_boost_factor
    # this has to do with reclaiming on fragmentation, but with almost no memory available it can lead to kswapd thrashing
    # so it needs to be disabled
    echo 0 > /proc/sys/vm/watermark_boost_factor
    # some more explanation from this post:
    # https://bugs.launchpad.net/ubuntu/+source/linux/+bug/1861359/comments/56
    # > What watermark boosting does is try to preemptively fire up kswapd to
    # > free memory when there hasn't been an allocation failure. It does this by
    # > increasing kswapd's high watermark goal and then firing up kswapd. The
    # > reason why this causes freezes is because, with the increased high
    # > watermark goal, kswapd will steal memory from processes that need it in
    # > order to make forward progress. These processes will, in turn, try to
    # > allocate memory again, which will cause kswapd to steal necessary pages
    # > from those processes again, in a positive feedback loop known as page
    # > thrashing. When page thrashing occurs, your system is essentially
    # > livelocked until the necessary forward progress can be made to stop
    # > processes from trying to continuously allocate memory and trigger kswapd
    # > to steal it back.

    # disable readahead for reading from swap (default is 3 which means 2^3 = 8 pages)
    echo 0 > /proc/sys/vm/page-cluster

    # raise vfs_cache_pressure a bit, default 100
    echo 200 > /proc/sys/vm/vfs_cache_pressure

    # write cache is less important with non-spinning disks
    # reduce the defaults to reduce write cache memory use just in case we're mem limited
    # ratio of available memory
    # dirty_background_ratio: start writing out data as soon as ratio pages are dirty (used for write cache)
    echo 2 > /proc/sys/vm/dirty_background_ratio
    # dirty_bytes_ratio: processes start writing out themselves (block) as soon as ratio pages are dirty
    echo 10 > /proc/sys/vm/dirty_ratio

    # raspbian sets min_free_kbytes at 16384 which wastes a lot of memory
    # the kernel default is a bit small though for weird networking quirks on the raspberry pi and possibly other SBCs
    # thus 8192 should be a good compromise for a stable system without wasting too much memory
    # lower this setting if it's very large and we have 2 GB or less memory
    # increase the setting if it's less than 8192
    min_free_kbytes=$(cat /proc/sys/vm/min_free_kbytes)
    total_mem_kbytes=$(grep -e MemTotal /proc/meminfo | tr -s ' ' | cut -d' ' -f2)
    if (( min_free_kbytes > 8192 )) && (( total_mem_kbytes < 2048 * 1024 )) || (( min_free_kbytes < 8192 )); then
        echo 8192 > /proc/sys/vm/min_free_kbytes
    fi

    # min_free_kbytes kernel defaults:
    # 512MB:     2896k
    # 1024MB:    4096k
    # 2048MB:    5792k
    # 4096MB:    8192k
    # 8192MB:    11584k
    # 16384MB:   16384k
}

NAME=zram0
DEV=/dev/$NAME

if { mount; cat /proc/swaps; } | grep -qs "$DEV"; then
    vm_tweaks
    echo "zram-swap.sh: $DEV is already mounted or used as swap, only applied virtual memory tweaks."
    exit 0
fi

echo "$(date -u +"%FT%T.%3NZ") zram-swap.sh setting up swap on zram"

modprobe zram

# reset the device to ensure we can set the parameters
for i in {1..9}; do
    if echo 1 > "/sys/block/$NAME/reset"; then
        break
    fi
    sleep 1
done

# https://github.com/lz4/lz4?tab=readme-ov-file#benchmarks
# Core i7-9700K single thread
# Compressor            Ratio   Compression Decompression
# LZ4 default (v1.9.0)  2.101   780 MB/s    4970 MB/s
# Zstandard 1.4.0 -1    2.883   515 MB/s    1380 MB/s
#
# on a pi4, lz4 in compression has even higher relative speed over zstd
# use zstd for now even though it's slower
#echo lz4 > "/sys/block/$NAME/comp_algorithm"
echo zstd > "/sys/block/$NAME/comp_algorithm"

# use 1/4 of memory
use=$(( $(grep -e MemTotal /proc/meminfo | tr -s ' ' | cut -d' ' -f2) / 4 ))

# use at least 256M for systems with small memory
min=$(( 256 * 1024 ))

if (( use < min )); then
    size=$min
else
    size=$use
fi

# zram maximum memory usage
echo $(( size ))K > "/sys/block/$NAME/mem_limit"

# disk size
# let's make this 3x the memory limit in case we get good compression
echo $(( 4 * size ))K > "/sys/block/$NAME/disksize"

mkswap "$DEV"
swapon -p 100 "$DEV"

# turn off file based swap
TURNOFF=$(grep </proc/swaps -F -v -e zram -e Filename | cut -d' ' -f1)
if [[ -n $TURNOFF ]]; then
    swapoff $TURNOFF || true
fi

vm_tweaks

echo "$(date -u +"%FT%T.%3NZ") zram-swap.sh setting up swap on zram ... done"
