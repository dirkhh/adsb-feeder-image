# SDRs and Protocols

Within the RTLSDR group there are a wide variety of models. Some are just the basic chip, no biastee (so turning it on gets you nothing). Others (e.g. some nooelec models) always have biastee enabled (again, regardless of software). Some have LNAs or even filtered LNAs integrated (like the well known 'blue' and 'orange' RTLSDR sticks in the metal housing)  those also don't support biastee.

Regardless of what your SDR can do, some of the containers that are used for this projects still may not support all settings - especially biastee support is limited to just a few.

## ADS-B (1090 and 1090_2)
| SDR     | gain          | autogain            | biastee            |
|:-------:|:-------------:|:-------------------:|:------------------:|
| RTLSDR  | 0 - 49.6      |  auto               | :heavy_check_mark: |
| Airspy  | 0 - 21        |  auto               | :heavy_check_mark: |
| AirspyHF| :x:           | :x:                 | :x:                |
| SDRplay | leave empty   | :heavy_check_mark:  | :x:                |

## ADS-B (UAT)
| SDR     | gain          | autogain | biastee            |
|:-------:|:-------------:|:--------:|:------------------:|
| RTLSDR  | 0 - 49.6      |  auto    | :heavy_check_mark: |
| Airspy  | :x:           | :x:      | :x:                |
| AirspyHF| :x:           | :x:      | :x:                |
| SDRplay | :x:           | :x:      | :x:                |

## ACARS (and ACARS_2)
| SDR     | gain          | autogain | biastee |
|:-------:|:-------------:|:--------:|:-------:|
| RTLSDR  | 0 - 49.6      |  -10     | :x:     |
| Airspy  | 0 - 21        | :x:      | :x:     |
| AirspyHF| :x:           | :x:      | :x:     |
| SDRplay | 20 - 59       | -10      | :x:     |

## VDLM2
| SDR     | gain          | autogain   | biastee |
|:-------:|:-------------:|:----------:|:-------:|
| RTLSDR  | 0 - 49.6      | :x:        | :x:     |
| Airspy  | :x:           | :x:        |         |
| AirspyHF| :x:           | :x:        | :x:     |
| SDRplay | 20 - 59       | leave empty| :x:     |

## HFDL
| SDR     | gain          | autogain | biastee |
|:-------:|:-------------:|:--------:|:-------:|
| RTLSDR  | 0 - 49.6      | :x:      | :x:     |
| Airspy  | 0 - 21        | :x:      | :x:     |
| AirspyHF| 0 - 21        | :x:      | :x:     |
| SDRplay | 20 - 59       | :x:      | :x:     |

## AIS
| SDR     | gain          | autogain   | biastee           |
|:-------:|:-------------:|:----------:|:-----------------:|
| RTLSDR  | 0 - 49.6      | auto       | :heavy_check_mark |
| Airspy  | 0 - 21        | :x:        | :x:               |
| AirspyHF| always agc    | leave empty| :x:               |
| SDRplay | 20 - 59       | :x:        | :x:               |

## SONDE
| SDR     | gain          | autogain | biastee            |
|:-------:|:-------------:|:--------:|:------------------:|
| RTLSDR  | 0 - 49.6      |  auto    | :heavy_check_mark: |
| Airspy  | :x:           | :x:      | :x:                |
| AirspyHF| :x:           | :x:      | :x:                |
| SDRplay | :x:           | :x:      | :x:                |
