# Welcome to ADSB.im on GitHub!

This project aims to simplify the process of setting up an ADS-B feeder, making it accessible to a wider audience.

You can contribute by helping to improve the project's documentation and user guides, ensuring that they are clear and easy to understand for users of all technical backgrounds.
Contributions of code and ideas are always welcome.
In addition, you can assist with testing the project and providing feedback on any bugs or issues that may arise.

By contributing to ADSB.im, you can help make this hobby more accessible to a wider audience, and encourage more people to get involved in the world of ADS-B tracking.

For simple changes, simply submit a PR. For more complex changes, please first create an issue where you outline your ideas and discuss the direction with the maintainer(s).

The main branch is where releases happen and it should always move in a 'fast-forward' style. The dev branch is mostly for testing things with the GitHub Actions pipeline and will see the occasional force-push.

Pull requests should usually be opened against the `beta` branch as I try to test things before they go into `main` and only move main forward as a `fast-forward` merge of `beta`.

## Testing changes

After having done your changes on your local codebase, you can test these against your own ADSB feeder. The prerequisite is to have a `root` SSH access to this instance and it must be available under the hostname `adsb-feeder.local` in your local network. However, if it's not, you can edit the first line in the [Makefile](Makefile) to: 

```Makefile
HOST ?= your-feeder-hostname-or-ip
```

The root working directory of this repository contains a `Makefile` with different commands that interacts with the instance, i.e. copies files, restarts services, respectively. This allows for immediate testing the impact of the changes made.

* `$ make sync-and-update` will generally update "everything" including Docker definition changes or container versions
* `$ make sync-and-update-nocontainer` is aimed for changes to the feeder homepage, web server etc. It skips the container part and is therefore quicker to execute.
