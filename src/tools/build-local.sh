#!/bin/bash
#
# build a specific image locally; this doesn't try to parse the YAML, so it needs
# to be manually kept in sync with build-images.yml

set -e

while [ $# -gt 0 ]; do
    case "$1" in
        --name)
            name="$2"
            shift
            ;;
    esac
    shift
done
if [ "$name" = "lepotato" ] ; then
    base_arch="arm64"
    variant="armbian"
    url="https://test.adsb.im/downloads/Armbian-unofficial_23.11.0-trunk_Lepotato_bookworm_current_6.1.63_minimal.img.xz"
    magic_path="image-armbian/le-potato.img.xz"
elif [ "$name" = "lepotato-raspbian" ] ; then
    base_arch=arm64
    variant=default
    url=https://test.adsb.im/downloads/raspbian-bookworm-lepotato.img.xz
    magic_path="image/le-potato-raspbian.img.xz"
elif [ "$name" = "odroidc4" ] ; then
        base_arch=arm64
        variant=armbian
        url=https://test.adsb.im/downloads/Armbian_community_24.8.0-trunk.314_Odroidc4_bookworm_current_6.6.36_minimal.img.xz
        magic_path="image-armbian/odroidc4.img.xz"
elif [ "$name" = "odroidxu4" ] ; then
        base_arch=armv7l
        variant=armbian
        url=https://test.adsb.im/downloads/Armbian_24.5.3_Odroidxu4_bookworm_current_6.6.36_minimal.img.xz
        magic_path="image-armbian/odroidxu4.img.xz"
elif [ "$name" = "nanopi-neo3-dietpi" ] ; then
        variant=dietpi-fat-2
        base_arch=arm64
        dietpi_machine=56
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_NanoPiNEO3-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_NanoPiNEO3-ARMv8-Bookworm.img.xz"
elif [ "$name" = "orangepi-3LTS-dietpi" ] ; then
        variant=dietpi-fat-2
        base_arch=arm64
        dietpi_machine=89
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_OrangePi3LTS-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_OrangePi3LTS-ARMv8-Bookworm.img.xz"
elif [ "$name" = "orangepi-5-dietpi" ] ; then
        variant=dietpi-fat-2
        base_arch=arm64
        dietpi_machine=82
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_OrangePi5Plus-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_OrangePi5Plus-ARMv8-Bookworm.img.xz"
elif [ "$name" = "orangepi-zero3-dietpi" ] ; then
        variant=dietpi-fat-2
        base_arch=arm64
        dietpi_machine=83
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_OrangePiZero3-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_OrangePiZero3-ARMv8-Bookworm.img.xz"
elif [ "$name" = "raspberrypi64-pi-2-3-4-5" ] ; then
        base_arch=arm64
        variant=default
        url=https://downloads.raspberrypi.com/raspios_lite_arm64/images/raspios_lite_arm64-2024-07-04/2024-07-04-raspios-bookworm-arm64-lite.img.xz
        magic_path="image/2024-07-04-raspios-bookworm-arm64-lite.img.xz"
elif [ "$name" = "raspberrypi64-dietpi-pi-2-3-4" ] ; then
        base_arch=arm64
        variant=dietpi-fat-1
        dietpi_machine=4
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_RPi234-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_RPi-ARMv8-Bookworm.img.xz"
elif [ "$name" = "raspberrypi64-dietpi-pi-5" ] ; then
        base_arch=arm64
        variant=dietpi-fat-1
        dietpi_machine=5
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_RPi5-ARMv8-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_RPi5-ARMv8-Bookworm.img.xz"
elif [ "$name" = "x86-64-native" ] ; then
        variant=dietpi-root-only
        base_arch=x86_64
        dietpi_machine=21
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_NativePC-BIOS-x86_64-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_NativePC-BIOS-x86_64-Bookworm.img.xz"
elif [ "$name" = "x86-64-vm" ] ; then
        variant=dietpi-root-only
        base_arch=x86_64
        dietpi_machine=20
        url=https://github.com/dirkhh/DietPi/releases/download/latest/DietPi_VM-x86_64-Bookworm.img.xz
        magic_path="image-dietpi/DietPi_VM-x86_64-Bookworm.img.xz"
else
        echo "Unknown build: $name"
        exit 1
fi

MAGIC_DIR=$(dirname "${magic_path}")
mkdir -p "${MAGIC_DIR}"
[ -f "${magic_path}" ] || wget -qO "${magic_path}" "$url"
# make sure this file shows up as the newest image
touch "${magic_path}"

# figure out the name
is_release="test"
if git describe --exact-match 2>/dev/null ; then tag=$(git describe --exact-match) ; else tag=$(git rev-parse HEAD) ; fi
if [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+$ ]] ; then is_release="release" ; fi
if [[ "$tag" =~ ^v[0-9]+\.[0-9]+\.[0-9]+-beta ]] ; then is_release="beta" ; fi
tag=$(echo "$tag" | sed -r 's/^(.{8}).{32}$/g-\1/')

echo "export BASE_ARCH=${base_arch}" >> config
feeder_image_name="adsb-im-${name}-${tag}.img"
. ./.secrets
echo "export BASE_USER_PASSWORD=${secrets_USER_PASSWORD}" >> config
echo "export ROOT_PWD=${secrets_ROOT_PASSWORD}" >> config
echo "export SSH_PUB_KEY='${secrets_SSH_KEY}'" >> config
echo "export FEEDER_IMAGE_NAME=${feeder_image_name}" >> config

# sudo GH_REF_TYPE=${{ github.ref_type }} GH_TRGT_REF=${{ github.ref_name }} bash -x ./build_dist "${variant}"
sudo bash -x ./build_dist "${variant}"

# prepare for release upload
mkdir -p uploads
CURRENT_IMAGE_NAME="$(basename $magic_path)"
echo "${CURRENT_IMAGE_NAME}"
if [ "${variant}" = "default" ]; then
        WORKSPACE="workspace"
elif [[ "${variant}" = *"dietpi"* ]] ; then
        WORKSPACE="image-dietpi"
else
        WORKSPACE="workspace-${variant}"
fi
ls -l "$WORKSPACE"
BUILT_IMAGE="$(find $WORKSPACE -name "*.img" | head -n 1)"
sudo mv -v "${BUILT_IMAGE}" uploads/"${feeder_image_name}"
if [[ ${name} == *x86-64-vm* ]] ; then
        for img in $(find $WORKSPACE -name "DietPi_*.xz") ; do
        base_name=$(basename "$img")
        nodiet=${base_name#DietPi_}
        nobookworm=${nodiet/-Bookworm/}
        noarch=${nobookworm/-X86_64/}
        final_name="adsb-im-x86-64-vm-${{ steps.tag.outputs.tag }}-${noarch}"
        sudo mv -v "$img" uploads/"${final_name}"
        done
fi
if [[ ${magic_path} == *NativePC* ]] ; then
        BUILT_ISO="$(find $WORKSPACE -name "*.iso" | head -n 1)"
        sudo mv -v "${BUILT_ISO}" uploads/"${IMAGE%.img}.iso"
fi

