#!/bin/bash
#
# Setup TFTP/iSCSI boot for Raspberry Pi test image
#
# Usage: setup-tftp-iscsi.sh <image_file> [ssh_public_key]
#
# Arguments:
#   image_file      - Path to the Raspberry Pi image file (.img)
#   ssh_public_key  - Optional: Path to SSH public key to install in /root/.ssh/authorized_keys
#                     for passwordless access. If using test-feeder-image.py with --ssh-key,
#                     the public key is assumed to be at <private_key_path>.pub
#
set -e  # Exit on any error

# Configuration
IMAGE_FILE="$1"
WORKING_IMAGE_FILE="$2"
SSH_PUBLIC_KEY="$3"  # Optional: SSH public key to install for passwordless access
MOUNT_BOOT="/mnt/rpi-prep-root/boot/firmware"
MOUNT_ROOT="/mnt/rpi-prep-root"
TFTP_DEST="/srv/tftp"
CMDLINE="console=serial0,115200 console=tty1 ip=dhcp ISCSI_INITIATOR=iqn.2025-10.im.adsb.testrpi:rpi4 ISCSI_TARGET_NAME=iqn.2025-10.im.adsb:adsbim-test.root ISCSI_TARGET_IP=192.168.66.109 ISCSI_TARGET_PORT=3260 root=/dev/sda2 rw rootwait elevator=deadline cgroup_enable=cpuset cgroup_enable=memory cgroup_memory=1 systemd.getty_auto=0"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}=== Raspberry Pi Network Boot Image Preparation ===${NC}"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run as root${NC}"
    exit 1
fi

# Check if image exists
if [ ! -f "$IMAGE_FILE" ]; then
    echo -e "${RED}Error: Image file $IMAGE_FILE not found${NC}"
    exit 1
fi

if [ "$WORKING_IMAGE_FILE" = "" ]; then
    echo -e "${RED}Error: Working image file not provided${NC}"
    exit 1
fi

# Check and expand root partition if needed
echo -e "${YELLOW}Checking root partition size...${NC}"
MIN_SIZE_MB=8200

# Get current size of partition 2 in MB
CURRENT_SIZE_MB=$(sfdisk --json $IMAGE_FILE | jq -r '.partitiontable.partitions[1].size / 2048 | floor')

echo "Current partition 2 size: ${CURRENT_SIZE_MB} MB"
echo "Minimum required size: ${MIN_SIZE_MB} MB"

PARTITION_EXPANDED=false

if [ "$CURRENT_SIZE_MB" -lt "$MIN_SIZE_MB" ]; then
    echo "Partition too small, expanding..."

    # Calculate how much to add to the image
    SIZE_DIFF_MB=$((MIN_SIZE_MB - CURRENT_SIZE_MB))
    echo "Adding ${SIZE_DIFF_MB} MB to image..."

    # Expand the image file
    sudo truncate -s +${SIZE_DIFF_MB}M $IMAGE_FILE

    # Setup loop device
    LOOP_DEV=$(sudo losetup -fP --show $IMAGE_FILE)
    echo "Loop device: $LOOP_DEV"

    # Resize partition 2 to use all available space
    echo "Resizing partition..."
    sudo parted $LOOP_DEV resizepart 2 100%
    sudo partprobe $LOOP_DEV

    # Resize the filesystem and always fix the filesystem
    echo "Checking filesystem..."
    sudo e2fsck -y -f ${LOOP_DEV}p2

    # Resize the filesystem
    echo "Resizing filesystem..."
    sudo resize2fs ${LOOP_DEV}p2

    # Clean up
    sudo losetup -d $LOOP_DEV

    # Verify new size
    NEW_SIZE_MB=$(sudo sfdisk --json $IMAGE_FILE | jq -r '.partitiontable.partitions[1].size / 2048 | floor')
    echo "New partition 2 size: ${NEW_SIZE_MB} MB"
    echo "Partition expanded successfully!"
    PARTITION_EXPANDED=true
else
    echo "Partition size is sufficient."

    # Still need to check if filesystem matches partition size
    LOOP_DEV=$(sudo losetup -fP --show $IMAGE_FILE)
    echo "Loop device: $LOOP_DEV (checking filesystem)"

    # Get filesystem size
    FS_SIZE_BLOCKS=$(sudo tune2fs -l ${LOOP_DEV}p2 | grep "Block count:" | awk '{print $3}')
    FS_BLOCK_SIZE=$(sudo tune2fs -l ${LOOP_DEV}p2 | grep "Block size:" | awk '{print $3}')
    FS_SIZE_MB=$((FS_SIZE_BLOCKS * FS_BLOCK_SIZE / 1024 / 1024))

    # Get partition size in MB
    PART_SIZE_MB=$(sfdisk --json $IMAGE_FILE | jq -r '.partitiontable.partitions[1].size / 2048 | floor')

    echo "Filesystem size: ${FS_SIZE_MB} MB"
    echo "Partition size: ${PART_SIZE_MB} MB"

    # Allow 1% difference for block alignment
    SIZE_DIFF=$((PART_SIZE_MB - FS_SIZE_MB))
    SIZE_DIFF_PCT=$((SIZE_DIFF * 100 / PART_SIZE_MB))

    if [ $SIZE_DIFF_PCT -gt 1 ]; then
        echo "Filesystem size doesn't match partition size, resizing filesystem..."
        sudo e2fsck -y -f ${LOOP_DEV}p2
        sudo resize2fs ${LOOP_DEV}p2
        echo "Filesystem resized to match partition"
        PARTITION_EXPANDED=true
    else
        echo "Filesystem size matches partition size"
    fi

    sudo losetup -d $LOOP_DEV
fi

# Cleanup function
cleanup() {
    echo -e "${YELLOW}Cleaning up...${NC}"

    # Unmount bind mounts if they exist
    umount "$MOUNT_ROOT/proc" 2>/dev/null || true
    umount "$MOUNT_ROOT/sys" 2>/dev/null || true
    umount "$MOUNT_ROOT/dev/pts" 2>/dev/null || true
    umount "$MOUNT_ROOT/dev" 2>/dev/null || true

    # Unmount partitions
    umount "$MOUNT_BOOT" 2>/dev/null || true
    umount "$MOUNT_ROOT" 2>/dev/null || true

    # Remove loop device
    if [ -n "$LOOP_DEV" ]; then
        losetup -d "$LOOP_DEV" 2>/dev/null || true
    fi

    # Remove mount points
    rmdir "$MOUNT_BOOT" 2>/dev/null || true
    rmdir "$MOUNT_ROOT" 2>/dev/null || true

    echo -e "${GREEN}Cleanup complete${NC}"
}

# Set trap to cleanup on exit
trap cleanup EXIT

# Create mount points
echo -e "${YELLOW}Creating mount points...${NC}"
mkdir -p "$MOUNT_BOOT"
mkdir -p "$MOUNT_ROOT"

# Setup loop device
echo -e "${YELLOW}Setting up loop device...${NC}"
LOOP_DEV=$(losetup -fP --show "$IMAGE_FILE")
echo -e "${GREEN}Loop device: $LOOP_DEV${NC}"

# Wait a moment for partition devices to appear
sleep 2

# Mount partitions
echo -e "${YELLOW}Mounting partitions...${NC}"
mount "${LOOP_DEV}p2" "$MOUNT_ROOT"
mount "${LOOP_DEV}p1" "$MOUNT_BOOT"
echo -e "${GREEN}Partitions mounted${NC}"

# Bind mount /boot/firmware if it's a separate directory
if [ -d "$MOUNT_ROOT/boot/firmware" ] && [ "$(ls -A $MOUNT_ROOT/boot/firmware)" ]; then
    echo -e "${YELLOW}Note: /boot/firmware exists in root partition${NC}"
else
    echo -e "${YELLOW}Bind mounting boot partition to /boot/firmware...${NC}"
    mkdir -p "$MOUNT_ROOT/boot/firmware"
    mount --bind "$MOUNT_BOOT" "$MOUNT_ROOT/boot/firmware"
fi

# Setup chroot environment
echo -e "${YELLOW}Setting up chroot environment...${NC}"
mount -t proc /proc "$MOUNT_ROOT/proc"
mount -t sysfs /sys "$MOUNT_ROOT/sys"
mount -o bind /dev "$MOUNT_ROOT/dev"
mount -o bind /dev/pts "$MOUNT_ROOT/dev/pts"

# Copy DNS resolution
cp /etc/resolv.conf "$MOUNT_ROOT/etc/resolv.conf"

# Check if image has already been configured for iSCSI boot
NEEDS_ISCSI_SETUP=true
NEEDS_INITRAMFS_REBUILD=false

if [ -f "$MOUNT_ROOT/etc/initramfs-tools/scripts/local-top/iscsi" ]; then
    echo -e "${YELLOW}Checking if iSCSI boot is already configured...${NC}"

    # Check if the iSCSI script exists and looks correct
    if grep -q "iscsistart" "$MOUNT_ROOT/etc/initramfs-tools/scripts/local-top/iscsi" 2>/dev/null; then
        echo -e "${GREEN}iSCSI boot script already exists${NC}"

        # Check if initramfs exists
        if [ -f "$MOUNT_BOOT/initramfs.img" ]; then
            echo -e "${GREEN}Initramfs already exists - skipping iSCSI setup${NC}"
            NEEDS_ISCSI_SETUP=false
        else
            echo -e "${YELLOW}Initramfs missing - will rebuild${NC}"
            NEEDS_INITRAMFS_REBUILD=true
        fi
    else
        echo -e "${YELLOW}iSCSI script exists but looks incomplete - will reconfigure${NC}"
    fi
else
    echo -e "${YELLOW}iSCSI boot not configured - will set up${NC}"
fi

if [ "$NEEDS_ISCSI_SETUP" = "true" ]; then
    # Create initramfs configuration files
    echo -e "${YELLOW}Creating initramfs configuration files...${NC}"
elif [ "$NEEDS_INITRAMFS_REBUILD" = "true" ]; then
    echo -e "${YELLOW}Will rebuild initramfs only...${NC}"
else
    echo -e "${GREEN}Skipping iSCSI setup - already configured${NC}"
fi

# Only create configuration files if needed
if [ "$NEEDS_ISCSI_SETUP" = "true" ]; then

# Create modules file
cat > "$MOUNT_ROOT/etc/initramfs-tools/modules" << 'EOF'
# iSCSI modules
iscsi_tcp
libiscsi
libiscsi_tcp
scsi_transport_iscsi

# Docker modules
overlay
xt_nat
xt_conntrack
br_netfilter
nf_nat
EOF

# Create iSCSI hook
cat > "$MOUNT_ROOT/etc/initramfs-tools/hooks/iscsi" << 'EOF'
#!/bin/sh
PREREQ=""
prereqs()
{
    echo "$PREREQ"
}

case $1 in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /usr/share/initramfs-tools/hook-functions

copy_exec /sbin/iscsid /sbin
copy_exec /sbin/iscsistart /sbin
copy_exec /usr/bin/iscsiadm /sbin

# Copy libraries
for lib in $(ldd /sbin/iscsid 2>/dev/null | awk '{print $3}' | grep "^/"); do
    copy_exec "$lib"
done
EOF

chmod +x "$MOUNT_ROOT/etc/initramfs-tools/hooks/iscsi"

# Create iSCSI boot script
cat > "$MOUNT_ROOT/etc/initramfs-tools/scripts/local-top/iscsi" << 'EOF'
#!/bin/sh
PREREQ="udev"
prereqs()
{
    echo "$PREREQ"
}

case $1 in
prereqs)
    prereqs
    exit 0
    ;;
esac

. /scripts/functions

# Parse kernel command line
for x in $(cat /proc/cmdline); do
    case $x in
    ISCSI_TARGET_IP=*)
        ISCSI_TARGET_IP="${x#ISCSI_TARGET_IP=}"
        ;;
    ISCSI_TARGET_NAME=*)
        ISCSI_TARGET_NAME="${x#ISCSI_TARGET_NAME=}"
        ;;
    ISCSI_INITIATOR=*)
        ISCSI_INITIATOR="${x#ISCSI_INITIATOR=}"
        ;;
    ISCSI_TARGET_PORT=*)
        ISCSI_TARGET_PORT="${x#ISCSI_TARGET_PORT=}"
        ;;
    esac
done

# Set defaults
ISCSI_TARGET_PORT="${ISCSI_TARGET_PORT:-3260}"

if [ -n "$ISCSI_TARGET_IP" ] && [ -n "$ISCSI_TARGET_NAME" ]; then
    log_begin_msg "Connecting to iSCSI target"

    # Set initiator name (create directory first)
    if [ -n "$ISCSI_INITIATOR" ]; then
        mkdir -p /etc/iscsi
        echo "InitiatorName=$ISCSI_INITIATOR" > /etc/iscsi/initiatorname.iscsi
    fi

    # Start iSCSI connection
    /sbin/iscsistart -i "$ISCSI_INITIATOR" \
                     -t "$ISCSI_TARGET_NAME" \
                     -g 1 \
                     -a "$ISCSI_TARGET_IP" \
                     -p "$ISCSI_TARGET_PORT"

    # Wait for device
    sleep 3

    log_end_msg
fi
EOF

chmod +x "$MOUNT_ROOT/etc/initramfs-tools/scripts/local-top/iscsi"

echo -e "${GREEN}Configuration files created${NC}"

fi  # End of NEEDS_ISCSI_SETUP

# Install packages and build initramfs if needed
if [ "$NEEDS_ISCSI_SETUP" = "true" ] || [ "$NEEDS_INITRAMFS_REBUILD" = "true" ]; then
    # Chroot and build initramfs
    echo -e "${YELLOW}Building initramfs in chroot...${NC}"
else
    echo -e "${GREEN}Skipping initramfs build - already configured${NC}"
fi

# Find the kernel version (needed for initramfs and summary)
KERNEL_VERSION=$(ls "$MOUNT_ROOT/lib/modules" | grep -E '^[0-9]+\.[0-9]+' | sort -V | tail -n1)

if [ -z "$KERNEL_VERSION" ]; then
    echo -e "${RED}Error: Could not find kernel version in /lib/modules${NC}"
    exit 1
fi

echo -e "${GREEN}Using kernel version: $KERNEL_VERSION${NC}"

if [ "$NEEDS_ISCSI_SETUP" = "true" ] || [ "$NEEDS_INITRAMFS_REBUILD" = "true" ]; then


# Install required packages if not present
chroot "$MOUNT_ROOT" /bin/bash << 'CHROOT_EOF'
set -e
export DEBIAN_FRONTEND=noninteractive

# Disable automatic initramfs updates during package installation
export INITRAMFS_TOOLS_KERNEL_HOOK=no

# Check if packages are installed
dpkg -l | grep -q initramfs-tools || { apt-get update && apt-get install -y --no-install-recommends initramfs-tools; }
dpkg -l | grep -q busybox || { apt-get update && apt-get install -y --no-install-recommends busybox; }
dpkg -l | grep -q open-iscsi || { apt-get update && apt-get install -y --no-install-recommends open-iscsi; }


# Check if iSCSI tools exist
if [ ! -f /sbin/iscsid ] || [ ! -f /sbin/iscsistart ]; then
    echo "ERROR: iSCSI tools not found. Please ensure open-iscsi is installed in the image."
    exit 1
else
    echo "iSCSI tools found"
fi

echo "Package check complete"
CHROOT_EOF

# Now generate initramfs manually (outside the package installation)
echo -e "${YELLOW}Generating initramfs...${NC}"
chroot "$MOUNT_ROOT" /bin/bash << CHROOT_EOF2
set -e
echo "Generating initramfs for kernel $KERNEL_VERSION..."
mkinitramfs -o /boot/firmware/initramfs.img $KERNEL_VERSION
echo "Initramfs created successfully"
ls -lh /boot/firmware/initramfs.img
CHROOT_EOF2

echo -e "${GREEN}Initramfs built successfully${NC}"

fi  # End of initramfs building

# Install SSH public key if provided
if [ -n "$SSH_PUBLIC_KEY" ]; then
    if [ -f "$SSH_PUBLIC_KEY" ]; then
        echo -e "${YELLOW}Installing SSH public key for passwordless access...${NC}"

        # Create .ssh directory in root's home
        mkdir -p "$MOUNT_ROOT/root/.ssh"
        chmod 700 "$MOUNT_ROOT/root/.ssh"

        # Copy the public key to authorized_keys
        cp "$SSH_PUBLIC_KEY" "$MOUNT_ROOT/root/.ssh/authorized_keys"
        chmod 600 "$MOUNT_ROOT/root/.ssh/authorized_keys"

        echo -e "${GREEN}SSH public key installed to /root/.ssh/authorized_keys${NC}"
        echo -e "Key: ${YELLOW}$(head -n1 "$SSH_PUBLIC_KEY" | cut -c1-50)...${NC}"
    else
        echo -e "${YELLOW}Warning: SSH public key file not found at $SSH_PUBLIC_KEY${NC}"
        echo -e "${YELLOW}Skipping SSH key installation${NC}"
    fi
else
    echo -e "${YELLOW}No SSH public key provided - skipping SSH key installation${NC}"
fi

# Prepare TFTP destination
echo -e "${YELLOW}Preparing TFTP destination...${NC}"
mkdir -p "$TFTP_DEST"

# Copy boot files
echo -e "${YELLOW}Copying boot files to $TFTP_DEST...${NC}"

# Copy as root (can read from mounted filesystem), then chown to tftp:tftp
cp "$MOUNT_BOOT/kernel8.img" "$TFTP_DEST/"
cp "$MOUNT_BOOT/initramfs.img" "$TFTP_DEST/"
# Copy firmware files
cp $MOUNT_BOOT/*.elf "$TFTP_DEST/"
cp $MOUNT_BOOT/fixup*.dat "$TFTP_DEST/"

# Copy device tree
cp "$MOUNT_BOOT/bcm2711-rpi-4-b.dtb" "$TFTP_DEST/"

# Copy overlays directory
if [ -d "$MOUNT_BOOT/overlays" ]; then
    cp -r "$MOUNT_BOOT/overlays" "$TFTP_DEST/"
fi

# Copy or create config.txt
if [ -f "$MOUNT_BOOT/config.txt" ]; then
    echo "Copying config.txt from $MOUNT_BOOT to $TFTP_DEST"
    cp "$MOUNT_BOOT/config.txt" "$TFTP_DEST/"
    # Ensure initramfs line is present
    if ! grep -q "^initramfs" "$TFTP_DEST/config.txt"; then
        echo "Adding initramfs line to config.txt"
        echo "initramfs initramfs.img followkernel" >> "$TFTP_DEST/config.txt"
    fi
    if ! grep -q "^dtoverlay=disable-bt" "$TFTP_DEST/config.txt"; then
        echo "Adding dtoverlay=disable-bt to config.txt"
        echo "dtoverlay=disable-bt" >> "$TFTP_DEST/config.txt"
    fi
else
    # Create minimal config.txt
    echo "Creating minimal config.txt"
    cat > "$TFTP_DEST/config.txt" << 'EOF'
arm_64bit=1
kernel=kernel8.img
initramfs initramfs.img followkernel
enable_uart=1
dtoverlay=disable-bt
EOF
fi

if [ -f "$MOUNT_BOOT/dietpi.txt" ]; then
    echo "Copying dietpi.txt from $MOUNT_BOOT to $TFTP_DEST"
    cp "$MOUNT_BOOT/dietpi.txt" "$TFTP_DEST/"
    sed -i "s/CONFIG_SERIAL_CONSOLE_ENABLE=0/CONFIG_SERIAL_CONSOLE_ENABLE=1/" "$TFTP_DEST/dietpi.txt"
    if ! grep -q "^CONFIG_SERIAL_CONSOLE_ENABLED" "$TFTP_DEST/dietpi.txt"; then
        echo "CONFIG_SERIAL_CONSOLE_ENABLED=1" >> "$TFTP_DEST/dietpi.txt"
    fi
fi

# Create or update cmdline.txt
if [ -f "$TFTP_DEST/cmdline.txt" ]; then
    EXISTING_CMDLINE=$(cat "$TFTP_DEST/cmdline.txt")
    if [ "$EXISTING_CMDLINE" = "$CMDLINE" ]; then
        echo -e "${GREEN}cmdline.txt already has correct content${NC}"
    else
        echo -e "${YELLOW}Updating cmdline.txt${NC}"
        echo "$CMDLINE" > "$TFTP_DEST/cmdline.txt"
    fi
else
    echo -e "${YELLOW}Creating cmdline.txt${NC}"
    echo "$CMDLINE" > "$TFTP_DEST/cmdline.txt"
fi

# Set proper permissions for TFTP server (change ownership to tftp:tftp)
chown -R tftp:tftp "$TFTP_DEST"
# Set files to 644, but keep directories at 755
find "$TFTP_DEST" -type f -exec chmod 644 {} \;
find "$TFTP_DEST" -type d -exec chmod 755 {} \;

echo -e "${GREEN}Boot files copied successfully${NC}"

# Configure iSCSI target (tgt)
echo -e "${YELLOW}Configuring iSCSI target...${NC}"

# Get absolute path for IMAGE_FILE
IMAGE_FILE_ABS=$(realpath "$IMAGE_FILE")

# Copy clean but prepared image file to working image file (i.e., the iSCSI directory)
cp "$IMAGE_FILE_ABS" "$WORKING_IMAGE_FILE"
echo -e "${GREEN}Working image file copied successfully to $WORKING_IMAGE_FILE${NC}"


# Create tgt configuration
TGT_CONF="/etc/tgt/conf.d/adsb.conf"

# Create configuration content
cat > "$TGT_CONF" << EOF
# ADS-B Feeder Image iSCSI Target Configuration
# This configuration provides the boot image via iSCSI for network boot testing
#
# Image: $IMAGE_FILE_ABS
# Generated: $(date)

<target iqn.2025-10.im.adsb:adsbim-test.root>
    # Backing storage - the actual image file
    backing-store $IMAGE_FILE_ABS

    # Allow access from the test Pi
    initiator-address 192.168.77.0/24

    # Enable write-through caching for consistency
    write-cache off
</target>
EOF

echo -e "${GREEN}iSCSI target configuration created: $TGT_CONF${NC}"
echo -e "Target: ${YELLOW}iqn.2025-10.im.adsb:adsbim-test.root${NC}"
echo -e "Backing store: ${YELLOW}$IMAGE_FILE_ABS${NC}"

# Restart tgt service to pick up new configuration
echo -e "${YELLOW}Restarting tgt service...${NC}"
systemctl restart tgt

# Wait for tgt to start
sleep 2

# Verify target is active
if tgtadm --mode target --op show 2>/dev/null | grep -q "iqn.2025-10.im.adsb:adsbim-test.root"; then
    echo -e "${GREEN}iSCSI target is active and ready${NC}"
else
    echo -e "${RED}Warning: iSCSI target may not be active${NC}"
    echo -e "${YELLOW}Check with: tgtadm --mode target --op show${NC}"
fi
# Summary
echo -e "${GREEN}=== Summary ===${NC}"
echo -e "Image: ${YELLOW}$IMAGE_FILE_ABS${NC}"
if [ -n "$KERNEL_VERSION" ]; then
    echo -e "Kernel: ${YELLOW}$KERNEL_VERSION${NC}"
fi
echo -e "TFTP destination: ${YELLOW}$TFTP_DEST${NC}"
echo -e "iSCSI target: ${YELLOW}iqn.2025-10.im.adsb:adsbim-test.root${NC}"
echo -e "Partition expanded: ${YELLOW}$PARTITION_EXPANDED${NC}"
echo -e "iSCSI setup performed: ${YELLOW}$NEEDS_ISCSI_SETUP${NC}"
echo -e ""
echo -e "${GREEN}Files in $TFTP_DEST:${NC}"
ls -lh "$TFTP_DEST"

echo -e ""
echo -e "${GREEN}=== Done! ===${NC}"
echo -e "Image ready for network boot testing"
echo -e "TFTP server: ${YELLOW}$TFTP_DEST${NC}"
echo -e "iSCSI target: ${YELLOW}iqn.2025-10.im.adsb:adsbim-test.root${NC}"

# Cleanup will happen automatically via trap
