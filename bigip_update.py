###################################################################################
# bigip_update.py
#
# author: jason rahm
#
# usage: bigip_update.py [-h] [-a] [-u] [-r] inventory user password
#
# positional arguments:
#   inventory     inventory file (host IP/FQDN,image path)
#   user          BIG-IP username
#   password      BIG-IP password
#
# optional arguments:
#   -h, --help    show this help message and exit
#   -a, --all     install tmos on all devices in inventory, not just standby devices
#   -u, --update  copy config to new tmos installation
#   -r, --reboot  reboot

# Example Inventory File Contents
# ltm3.test.local,/Users/citizenelah/Downloads/BIGIP-15.1.2.1-0.0.10.iso
# ltm13.test.local,/Users/citizenelah/Downloads/BIGIP-13.1.3.6-0.0.4.iso
###################################################################################

from bigrest.bigip import BIGIP
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from logging import getLogger, INFO, StreamHandler
from pathlib import Path
from time import sleep

import argparse
import sys


def build_parser():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="install tmos on all devices in inventory, not just standby devices",
    )
    parser.add_argument(
        "-u",
        "--update",
        action="store_true",
        help="copy config to new tmos installation"
    )
    parser.add_argument(
        "-r",
        "--reboot",
        action="store_true",
        help="reboot"
    )
    parser.add_argument("inventory", help="inventory file (host IP/FQDN,image path)")
    parser.add_argument("user", help="BIG-IP username")
    parser.add_argument("password", help="BIG-IP password")
    return parser.parse_args()


def instantiate_bigip(host, user, password):
    try:
        obj = BIGIP(host, user, password)
    except Exception as e:
        print(f"Failed to connect to {host} due to {type(e).__name__}:\n")
        print(f"{e}")
        sys.exit()
    return obj


def get_logger():
    logger = getLogger(__name__)
    logger.addHandler(StreamHandler())
    logger.setLevel(INFO)
    return logger


def is_standby(obj):
    status = obj.load("/mgmt/tm/sys/failover")
    if "standby" in status.properties.get('apiRawValues').get('apiAnonymous'):
        return "standby"
    else:
        return "active"


def get_time(format_type=None):
    if format_type == "file_name":
        return datetime.now().strftime("%Y%m%dT%H%M%S")
    else:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def get_active_volume(obj):
    # Get all volumes
    volumes = obj.load("/mgmt/tm/sys/software/volume")
    for volume in volumes:
        if volume.properties.get("active"):
            vol = volume.properties.get("name")
            break
    return vol


def get_available_volume(obj, host):
    # Get all volumes
    volumes = obj.load("/mgmt/tm/sys/software/volume")
    available_volumes = []
    for volume in volumes:
        if volume.properties.get("active") is None:
            available_volumes.append(volume.properties.get("name"))
        else:
            active_volume = volume.properties.get("name")
    if len(available_volumes) == 0:
        vol = list(active_volume)
        new_volume = f"{active_volume[:4]}{int(vol[4]) + 1}"
        volume_status = "new"
    else:
        # This arbitrarily selects the last available as the new volume and will overwrite whatever is there
        new_volume = available_volumes[-1]
        volume_status = "existing"
    LOGGER.info(
        f"{get_time()} - active volume on {host}: {active_volume}, new volume: {new_volume}"
    )
    return new_volume, volume_status


def install_image_status(obj, image, volume):
    if obj.exist(f"/mgmt/tm/sys/software/volume/{volume}"):
        volume_details = obj.load(f"/mgmt/tm/sys/software/volume/{volume}")
        if (
                volume_details.properties.get("version") == image.split("-")[1]
                and volume_details.properties.get("status") == "complete"
        ):
            LOGGER.info(
                f"{get_time()} - {image} installation complete and system is ready for config copy and reboot"
            )
            return True
        else:
            LOGGER.info(
                f'{get_time()} - {image} installation status: {volume_details.properties.get("status")}'
            )
            return False
    else:
        return False


def install_image(obj, image, host):
    vol, status = get_available_volume(obj, host)
    if status == "new":
        options = {"create-volume": True}
        data = {
            "command": "install",
            "name": f"{image}.iso",
            "volume": vol,
            "options": [options],
        }
        LOGGER.info(f"{get_time()} - creating {vol} on {host}")
    else:
        data = {"command": "install", "name": f"{image}.iso", "volume": vol}
    LOGGER.info(f"{get_time()} - beginning {image} install on {vol}")
    obj.command("/mgmt/tm/sys/software/image", data)

    # No iControl async task for image installation, need to emulate
    while True:
        if install_image_status(obj, image, vol) is True:
            break
        else:
            sleep(60)
    return vol


def download_ucs(obj, host):
    LOGGER.info(f"{get_time()} - Starting UCS creation for {host}")
    ucs_name = f'{host}-{get_time(format_type="file_name")}'
    data = {"command": "save", "name": ucs_name}
    ucs_create = obj.task_start("/mgmt/tm/task/sys/ucs", data)
    obj.task_wait(ucs_create)
    if obj.task_completed(ucs_create) and obj.task_result(ucs_create) == "":
        LOGGER.info(f"{get_time()} - UCS created for {host}")
        obj.download("/mgmt/shared/file-transfer/ucs-downloads/", f"{ucs_name}.ucs")
        if Path(f"{ucs_name}.ucs").exists():
            LOGGER.info(f"{get_time()} - UCS downloaded for {host}")
            return True
        else:
            LOGGER.info(f"{get_time()} - UCS download failed for {host}")
            return False
    else:
        LOGGER.info(f"{get_time()} - UCS creation failed for {host}")
        return False


def upload_tmos(obj, host, image_name, image_iso):
    # Check to see if the image is alread there
    if obj.exist(f"/mgmt/tm/sys/software/image/{image_name}.iso"):
        LOGGER.info(
            f"{get_time()} - {image_name} already validated as present on {host}"
        )
        return True
    else:
        # Upload image to the BIG-IP
        LOGGER.info(f"{get_time()} - Starting {image_name} upload to {host}")
        obj.upload("/mgmt/cm/autodeploy/software-image-uploads", image_iso)
        LOGGER.info(f"{get_time()} - {image_name} upload complete to {host}")
        sleep(30)
        if obj.exist(f"/mgmt/tm/sys/software/image/{image_name}.iso"):
            LOGGER.info(f"{get_time()} - {image_name} validated as present on {host}")
            return True
        else:
            LOGGER.info(
                f"{get_time()} - {image_name} not validated as present on {host}"
            )
            return False


def verify_config(obj, host):
    LOGGER.info(f"{get_time()} - Verifying config for {host}")
    options = {"verify": True}
    data = {"command": "load", "options": [options]}
    config_verify = obj.task_start("/mgmt/tm/task/sys/config", data)
    obj.task_wait(config_verify)
    if obj.task_completed(config_verify) and obj.task_result(config_verify) == "":
        LOGGER.info(f"{get_time()} - Config verified for {host}")
        return True
    else:
        LOGGER.info(f"{get_time()} - Config verification failed for {host}")
        return False


def copy_config_and_reboot(obj, active_vol, new_vol, reboot, host):
    LOGGER.info(f"{get_time()} - Copying config from {active_vol} to {new_vol} on {host} and rebooting")
    if reboot:
        data = {"command": "run", "utilCmdArgs": f"-c \"cpcfg --source={active_vol} --reboot {new_vol}\""}
    else:
        data = {"command": "run", "utilCmdArgs": f"-c \"cpcfg --source={active_vol} {new_vol}\""}
    obj.command('/mgmt/tm/util/bash', data)


def update_device(device):
    host, image_iso = device.split(",")
    image_name = Path(image_iso).stem
    LOGGER.info(f"{get_time()} - Begin process for {host}")

    # Instatiate BIG-IP
    b = instantiate_bigip(host, DEVICE_USER, DEVICE_PASSWORD)

    # Check if device is standby if -a not specified
    if DEVICE_ALL is True:
        ha_status = "ignore"
    else:
        ha_status = is_standby(b)

    if ha_status == "ignore" or ha_status == "standby":
        #
        # TODO - Check license
        #

        LOGGER.info(f"{get_time()} - {host} HA status is {ha_status}, proceeding")
        # Verify Configuration Loads, Move On if So
        if verify_config(b, host):
            # Create and Download UCS
            if download_ucs(b, host):
                # Upload TMOS Image
                if upload_tmos(b, host, image_name, image_iso):
                    LOGGER.info(
                        f"{get_time()} - {image_name} is ready for install on {host}"
                    )

                    # Install image in new slot
                    new_vol = install_image(b, image_name, host)

                    # Update devices but on Standby only
                    if DEVICE_UPDATE:
                        active_vol = get_active_volume(b)
                        if DEVICE_REBOOT is False:
                            boot_status = False
                            LOGGER.info(f"{get_time()} - copying config to {new_vol} on {host} but not rebooting")
                            copy_config_and_reboot(b, active_vol, new_vol, boot_status, host)
                        elif DEVICE_REBOOT is True and ha_status == 'standby':
                            boot_status = True
                            LOGGER.info(f"{get_time()} - copying config to {new_vol} on {host} and rebooting")
                            copy_config_and_reboot(b, active_vol, new_vol, boot_status, host)
                        else:
                            LOGGER.info(f"{get_time()} - device is active, skipping config install/reboot on {host}")
                    else:
                        LOGGER.info(f"{get_time()} - copying config skipped on {host}")
                else:
                    LOGGER.info(
                        f"{get_time()} - {image_name} is not ready for install on {host}"
                    )
            else:
                LOGGER.info(f"{get_time()} - UCS creation/download failed for {host}")
        else:
            LOGGER.info(f"{get_time()} - Config verification failed for {host}")
    else:
        LOGGER.info(
            f"{get_time()} - {host} is active. Halting...use the -a flag to install anyway"
        )


def device_mgr(devices):
    with ThreadPoolExecutor(max_workers=len(devices)) as executor:
        return executor.map(update_device, devices)


if __name__ == "__main__":
    args = build_parser()
    DEVICE_ALL = args.all
    DEVICE_UPDATE = args.update
    DEVICE_REBOOT = args.reboot
    DEVICE_USER = args.user
    DEVICE_PASSWORD = args.password
    LOGGER = get_logger()

    with open(args.inventory) as f:
        bigip_inventory = f.read().splitlines()

    # Check to see if the BIG-IP is the Standby
    # Upload TMOS Images
    LOGGER.info("\n\n\t---Script Start---\n\n")
    device_mgr(bigip_inventory)
    LOGGER.info("\n\n\t---Script Complete---\n\n")
