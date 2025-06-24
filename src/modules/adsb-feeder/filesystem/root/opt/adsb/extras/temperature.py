import json
import logging
import os
import sys
import time
import tempfile

# so far this only supports the DHT22 sensor on either a
# Raspberry Pi or an Orange Pi Zero 3
#
# for Raspberry Pi the pin number passed in is the BCM number,
# so for GPIO4 (aka pin 7 on the 26 or 40 pin header) pass in 4
# -- this means the DHT22 sensor is connected to
#
#  pin 1 - 3.3V
#  pin 7 - GPIO4
#  pin 9 - GND
#
# for Orange Pi Zero 3 the pin number passed in is the PCxx number,
# so for PC9 (aka pin 7 on the 26 pin header) pass in 9


class RPI:
    def __init__(self, pin):
        self.pi = pigpio.pi()
        self.sensor = rpi_dht22.sensor(self.pi, pin)

    def get_temperature(self):
        self.sensor.trigger()
        time.sleep(0.2)
        if self.sensor.staleness() < 5:
            return self.sensor.temperature()
        return None


class OPI:
    def __init__(self, gpio, pin):
        gpio.setboard(gpio.H616)
        gpio.setmode(gpio.SOC)
        self.pin = gpio.PC + pin
        self.instance = opi_dht22.DHT22(self.pin)
        self.last_temperature = -999

    def get_temperature(self):
        result = self.instance.read()
        if result.is_valid():
            if self.last_temperature - result.temperature < 1 and self.last_temperature - result.temperature > -1:
                self.last_temperature = result.temperature
                return result.temperature
            self.last_temperature = result.temperature
        return None


if __name__ == "__main__":
    # command line arg - call with PIN number (BCM for RPi, PCxx for OPi Zero 3)
    pin = None
    if len(sys.argv) == 2:
        pin = int(sys.argv[1])

    # figure out which board this is
    try:
        with open("/sys/firmware/devicetree/base/model", "r") as model_file:
            model = model_file.read().strip().strip("\0")
    except:
        model = None
    if model == "OrangePi Zero3":
        import OPi.GPIO as gpio
        import opi_dht22

        if pin == None:
            pin = 9
        sensor = OPI(gpio, pin)
    elif model.startswith("Raspberry Pi"):
        import pigpio
        import rpi_dht22

        if pin == None:
            pin = 4
        sensor = RPI(pin)
    else:
        print(f"No support for temperature sensors on |{model}|")
        sys.exit(1)

    # update the temperatures if we get valid data from the temperature sensor
    delta = 5
    while True:
        # no point running this if the target directory doesn't exist, yet
        if not os.path.isdir("/run/adsb-feeder-ultrafeeder"):
            time.sleep(60)
            continue
        temperature = sensor.get_temperature()
        if temperature != None:
            output = {"cpu": ""}
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as cpu:
                    output["cpu"] = f"{int(cpu.read().strip()) / 1000:.0f}"
            except:
                pass
            output["ext"] = f"{temperature:.0f}"
            output["now"] = f"{int(time.time())}"
            # write to temp file and move in place
            fd, tmp = tempfile.mkstemp(dir="/run/adsb-feeder-ultrafeeder")
            with os.fdopen(fd, "w") as f:
                json.dump(output, f, indent=2)
            os.rename(tmp, "/run/adsb-feeder-ultrafeeder/temperature.json")
            # no point in updating this super often - the temperature sensor has a fair
            # bit of jitter, anyway
            delta = 60
        else:
            # didn't get valid temperature - wait only 5 seconds
            delta = 5
        time.sleep(delta)
