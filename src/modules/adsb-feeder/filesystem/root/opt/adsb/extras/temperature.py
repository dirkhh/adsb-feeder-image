import json
import logging
import os
import subprocess
import sys
import time
import tempfile

# this module combines a number of different features to
# have a consistent way of getting the temperature:
#
# - DHT22 sensor on either a Raspberry Pi or an Orange Pi Zero 3
# - DHT11 sensor on (most?) Raspberry Pis
# - BME280 sensor on (most?) Raspberry Pis
# - TEMPer style USB sensors on any platform

# for the gpio based sensors (DHT11 and DHT22)
# on Raspberry Pi the pin number passed in is the BCM number,
# so for GPIO4 (aka pin 7 on the 26 or 40 pin header) pass in 4
# -- this means the DHT22 sensor is connected to
#
#  pin 1 - 3.3V
#  pin 7 - GPIO4
#  pin 9 - GND
#
# for Orange Pi Zero 3 the pin number passed in is the PCxx number,
# so for PC9 (aka pin 7 on the 26 pin header) pass in 9

# set the version of the dht native app that this expects:
VERSION = "v0.1.4"


def run_subprocess(command, timeout=180):
    try:
        result = subprocess.run(
            command,
            shell=True,
            capture_output=True,
            check=True,
            timeout=timeout,
        )
    except subprocess.SubprocessError as e:
        # something went wrong
        output = ""
        if e.stdout:
            output += e.stdout.decode()
        if e.stderr:
            output += e.stderr.decode()
        return (False, output)

    output = result.stdout.decode()
    return (True, output)


class BME280_i2c:
    def __init__(self):
        # check that i2c is enabled
        self.success, output = run_subprocess("lsmod | grep i2c_bcm2835 2> /dev/null", timeout=5)
        if not self.success:
            logger.info("i2c is not enabled")
            return
        try:
            import bme280
            import smbus2
        except ImportError:
            self.success, _ = run_subprocess("apt install -y python3-bme280 python3-smbus", timeout=600)
            if not self.success:
                logger.info("Failed to install python3-bme280 and python3-smbus")
                return
            try:
                import bme280
                import smbus2
            except ImportError:
                self.success = False
                logger.info("Failed to import bme280 and smbus2")
                return
        # BME280 sensor address (default address)
        self.address = 0x77

        # Initialize I2C bus
        self.bus = smbus2.SMBus(1)
        self.bme280 = bme280

        # Load calibration parameters
        self.calibration_params = self.bme280.load_calibration_params(self.bus, self.address)

    def get_temperature(self):
        if not self.success:
            return None
        data = self.bme280.sample(self.bus, self.address, self.calibration_params)
        return data.temperature


class USB_temper:
    def __init__(self):
        self.success = True
        try:
            import serial
        except ImportError:
            self.success, _ = run_subprocess("apt install -y python3-serial", timeout=600)
            if not self.success:
                logger.info("Failed to install python3-serial")
                return
        import temper

        self.temper = temper.Temper()
        known_devices = self.temper.list(use_json=True)
        if known_devices is None:
            self.success = False
            logger.info("Did not find supported TEMPer USB devices")

    def get_temperature(self):
        if not self.success:
            return None
        info = self.temper.read()
        if len(info) == 0:
            logger.info("Failed to read temperature from USB sensor")
            return None
        for inf in info:
            if "error" in inf:
                logger.info(f"Failed to read temperature from USB sensor: {inf['error']}")
            else:
                # if there is an external probe - report that one as likely the
                # user connected that in order to get a more accurate reading
                if "external temperature" in inf:
                    return inf["external temperature"]
                if "internal temperature" in inf:
                    return inf["internal temperature"]
        return None


class RPInative:
    def __init__(self, pin):
        self.pin = pin
        self.success = True
        if not os.path.exists(f"/opt/adsb/extras/dht-{VERSION}"):
            # download the file from GitHub
            logging.info(f"Downloading dht-{VERSION}")
            github_release_url = f"https://github.com/dirkhh/DHT-read/releases/download/{VERSION}/dht"
            command = f"curl -L {github_release_url} -o /opt/adsb/extras/dht-{VERSION}"
            success, output = run_subprocess(command)
            if not success:
                logging.error(f"Failed to download dht-{VERSION}: {output}")
                self.success = False
            else:
                logging.info(f"Downloaded dht-{VERSION}")
                os.chmod(f"/opt/adsb/extras/dht-{VERSION}", 0o755)

    def get_temperature(self):
        success, output = run_subprocess(f"timeout 55 /opt/adsb/extras/dht-{VERSION} -t {self.pin} 2>/dev/null", timeout=60)
        if not success:
            return None
        try:
            temperature = float(output.strip())
        except Exception:
            return None
        return temperature


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


def usage(error_text=None):
    if error_text:
        print(f"ERROR: {error_text}")
    print("Usage: temperature.py [pin|bme280|usb-temper]")


if __name__ == "__main__":
    logger = logging.getLogger("temperature-service")
    logging.basicConfig(
        filename="/run/temperature-service.log",
        level=logging.INFO,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    # command line arg - call with PIN number (BCM for RPi, PCxx for OPi Zero 3)
    pin = None
    use_bme280 = False
    use_usb_temper = False
    # loop over the command line arguments
    for arg in sys.argv[1:]:
        if arg == "bme280":
            if use_usb_temper:
                usage("don't specify both bme280 and usb-temper")
                sys.exit(1)
            use_bme280 = True
        elif arg == "usb-temper":
            if use_bme280:
                usage("don't specify both bme280 and usb-temper")
                sys.exit(1)
            use_usb_temper = True
        else:
            if use_bme280 or use_usb_temper:
                usage("don't add a pin number with bme280 or usb-temper")
                sys.exit(1)
            try:
                pin = int(arg)
                break
            except Exception:
                usage("can't parse pin number")
                sys.exit(1)

    if use_bme280:
        logger.info("Setting up i2c communication with BME280")
        sensor = BME280_i2c()
        if sensor.success:
            logger.info("Initialized i2c communication with BME280")
        else:
            logger.error("Failed to initialize i2c communication with BME280")
            sys.exit(1)
    elif use_usb_temper:
        logger.info("Attempting to use USB temperature sensor")
        sensor = USB_temper()
        if sensor.success:
            logger.info("Initialized USB temperature sensor")
        else:
            logger.error("Failed to initialize USB temperature sensor")
            sys.exit(1)
    else:
        logger.info("Setting up communication with DHT11 or DHT22")
        # figure out which board this is
        try:
            with open("/sys/firmware/devicetree/base/model", "r") as model_file:
                model = model_file.read().strip().strip("\0")
        except Exception:
            model = None
        if model == "OrangePi Zero3":
            import OPi.GPIO as gpio
            import opi_dht22

            if pin is None:
                pin = 9
            sensor = OPI(gpio, pin)
            logger.info(f"Running on {model}")
        # for Pi4 and 5 try the native app first, if that doesn't work, try the Python module
        elif model is not None and (model.startswith("Raspberry Pi 5") or model.startswith("Raspberry Pi 4")):
            if pin is None:
                pin = 4
            sensor = RPInative(pin)
            if sensor.success:
                logger.info(f"Running native dht on {model}")
            else:
                import pigpio
                import rpi_dht22

                sensor = RPI(pin)
                logger.info(f"Running legacy Python module on {model}")
        # other Raspberry Pi models just go with the Python code
        elif model is not None and model.startswith("Raspberry Pi"):
            if pin is None:
                pin = 4
            import pigpio
            import rpi_dht22

            sensor = RPI(pin)
            logger.info(f"Running legacy Python module on {model}")
        else:
            logger.error(f"No support for temperature sensors on |{model}|")
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
        if temperature is not None:
            output = {"cpu": ""}
            try:
                with open("/sys/class/thermal/thermal_zone0/temp", "r") as cpu:
                    output["cpu"] = f"{int(cpu.read().strip()) / 1000:.0f}"
            except Exception:
                pass
            output["ext"] = f"{temperature:.0f}"
            output["now"] = f"{int(time.time())}"
            # write to temp file and move in place
            fd, tmp = tempfile.mkstemp(dir="/run/adsb-feeder-ultrafeeder")
            with os.fdopen(fd, "w") as f:
                json.dump(output, f, indent=2)
            os.rename(tmp, "/run/adsb-feeder-ultrafeeder/temperature.json")
            # for the graphs1090 integration we need a sensor style file
            fd, tmp = tempfile.mkstemp(dir="/run/adsb-feeder-ultrafeeder")
            with os.fdopen(fd, "w") as f:
                print(f"{temperature * 1000.0:.0f}", file=f)
            os.rename(tmp, "/run/adsb-feeder-ultrafeeder/ambient-temperature")
            # no point in updating this super often - the temperature sensor has a fair
            # bit of jitter, anyway
            delta = 60
        else:
            # didn't get valid temperature - wait only 5 seconds
            delta = 5
        time.sleep(delta)
