# bigip_update

bigip_update is a python script that will update TMOS on BIG-IP devices

## Overview

Not all organizations have tools like BIG-IQ or Ansible in place to assist with automating BIG-IP updates. This script can do the following:

- Verify the configuration before updating
- Create and download a UCS backup
- Upload the TMOS image, if necessary
- Install the TMOS image in a new or inactive volume
- Copy the configuration to the new volume and reboot the device

## Installation

Clone this repository and install the requirements. A local python environment is required. This repo tested on version 3.8.

```
git clone https://github.com/f5-rahm/bigip_update.git
pip install -r requirements.txt
```

## Support
For support, please open a GitHub issue. Note that this is a pet project, not a product.

## Community Code of Conduct
Please refer to the [F5 DevCentral Community Code of Conduct](code_of_conduct.md).


## License
[Apache License 2.0](LICENSE)

## Copyright
Copyright 2014-2021 F5 Networks Inc.


### F5 Networks Contributor License Agreement

Before you start contributing to any project sponsored by F5 Networks, Inc. (F5) on GitHub, you will need to sign a Contributor License Agreement (CLA).

If you are signing as an individual, we recommend that you talk to your employer (if applicable) before signing the CLA since some employment agreements may have restrictions on your contributions to other projects.
Otherwise by submitting a CLA you represent that you are legally entitled to grant the licenses recited therein.

If your employer has rights to intellectual property that you create, such as your contributions, you represent that you have received permission to make contributions on behalf of that employer, that your employer has waived such rights for your contributions, or that your employer has executed a separate CLA with F5.

If you are signing on behalf of a company, you represent that you are legally entitled to grant the license recited therein.
You represent further that each employee of the entity that submits contributions is authorized to submit such contributions on behalf of the entity pursuant to the CLA.



