#!/bin/bash

qemu-system-x86_64 \
    -display none \
    -kernel ./tmp/vmlinuz \
    -m 1G -smp 2 \
    -usb -device usb-mouse -device usb-kbd \
    -device usb-net,netdev=net0 -netdev user,id=net0,hostfwd=tcp::10022-:22,hostfwd=tcp::15000-:5000,hostfwd=tcp::10080-:80,hostfwd=tcp::18080-:8080 \
    -append "root=0x0803 console=ttyS0,38400" \
    -serial file:/tmp/qemu_console.log \
    -hda "$1"
