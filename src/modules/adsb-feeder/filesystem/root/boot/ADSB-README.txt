In order to configure wifi on this image, please make the
following changes to two files in this directory:

dietpi.txt:
AUTO_SETUP_NET_WIFI_ENABLED=1
AUTO_SETUP_NET_WIFI_COUNTRY_CODE= your correct two letter country code (e.g. US for the USA or DE for Germany).

dietpi-wifi.txt:
aWIFI_SSID[0]=     your SSID
aWIFI_KEY[0]=      the WPA key of your WiFi network.

More documentation can be found at https://adsb.im/faq and https://adsb.im/using
