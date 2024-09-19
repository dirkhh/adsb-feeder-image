#!/bin/bash

set -e
trap 'echo "[ERROR] Error in line $LINENO when executing: $BASH_COMMAND"' ERR

# only run on adsb.im images
if ! [[ -f /opt/adsb/os.adsb.feeder.image ]]; then
    exit 0
fi

# probably always good to set unless swap is spinning disk backed
echo 0 > /proc/sys/vm/page-cluster

if [[ -e /dev/zram0 ]]; then
    exit 1
fi

modprobe zram
# Compressor            Ratio   Compression Decompression
# LZ4 default (v1.9.0)  2.101   780 MB/s    4970 MB/s
# Zstandard 1.4.0 -1    2.883   515 MB/s    1380 MB/s
echo zstd > /sys/block/zram0/comp_algorithm

# user max quarter of memory
use=$(( $(grep -e MemTotal /proc/meminfo | tr -s ' ' | cut -d' ' -f2) / 4 ))
# never more than 1G
max=$(( 1 * 1024 * 1024 ))
# always use at least 256M as zram memory limit
min=$(( 256 * 1024 ))

if (( use < min )); then
    size=$min
elif (( use > maxkb )); then
    size=$max
else
    size=$use
fi

# disk size
# let's make this 3x the memory limit in case we get good compression
echo $(( 4 * size ))K > /sys/block/zram0/disksize
# max memory usage
echo $(( size ))K > /sys/block/zram0/mem_limit

mkswap /dev/zram0
swapon -p 100 /dev/zram0

# turn off file based swap
swapoff $(cat /proc/swaps | grep -F -v -e zram -e Filename | cut -d' ' -f1) || true

if ! cat /proc/swaps | grep -qs -F -v -e zram -e Filename; then

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
    # this has to do with reclaiming on fragmentation, swap on zram guides seem to disable this but don't give a reason
    echo 0 > /proc/sys/vm/watermark_boost_factor
fi
