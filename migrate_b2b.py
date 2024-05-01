import balena
import os
import json
import logging
import subprocess
import traceback


import balena.exceptions

# Setting up the logger
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)


def migrate_devices(source_balena: balena.Balena,
                    target_balena: balena.Balena,
                    target_org_owner,
                    fleets,
                    config_template_path,
                    output_config_files_folder,
                    device_script):
    try:
        # Load config template
        with open(config_template_path) as template_file:
            template_data = json.load(template_file)
        logging.debug(f"Using config template data: {template_data}")

        for fleet_slug in fleets:
            # Get fleet info from source
            try:
                logging.info(f"Processing fleet {fleet_slug}")
                source_fleet_info = source_balena.models.application.get(fleet_slug)
            except balena.exceptions.ApplicationNotFound as e:
                logging.error(e.message)
                break
            except Exception as e:
                print(e)
                logging.error(str(e))

            app_name = source_fleet_info['app_name']
            logging.debug(f"Source's fleet info {app_name}: {source_fleet_info}")

            # Check if fleet exists in the target
            target_fleet_id = -1
            try:
                target_fleet_info = target_balena.models.application.get_by_owner(app_name=app_name, owner=target_org_owner)
                target_fleet_id = target_fleet_info['id']
                logging.debug(f"Target's fleet {app_name} info: {target_fleet_info}")
                logging.info(f"Found id {target_fleet_id} for fleet {app_name}")
            except balena.exceptions.BalenaException:
                logging.info(f"Fleet {app_name} not found in target.")
                if target_fleet_id == -1:
                    logging.info(f"Creating fleet {source_fleet_info['app_name']} on target")
                    try:
                        device_type = source_fleet_info['device_type']
                        target_fleet_id = target_balena.models.application.create(app_name,
                                                                                device_type)
                    except balena.exceptions.BalenaException:
                        logging.error("Error creating {app_name} of type {device_type}")
                        break

            # Get devices in the source fleet to migrate them
            try:
                devices_in_source = source_balena.models.device.get_all_by_application(fleet_slug)
                logging.debug(f"Devices in source fleet: {devices_in_source}")
            except balena.exceptions.ApplicationNotFound as e:
                logging.error(f"application {fleet_slug} not found in source")
                break
            except balena.exceptions.BalenaException as e:
                print(e)
            except Exception as e:
                logging.error(f"Error creating fleet")
                break

            for device in devices_in_source:
                uuid = device['uuid']
                logging.info(f"Processing device {uuid}")

                # SSH into the device to retrieve config.json
                try:
                    if device['is_online']:
                        ip_address = device['ip_address'].split()[0]
                        command = f"ssh -p 22222 -o LogLevel=ERROR root@{ip_address} 'cat /mnt/boot/config.json' < /dev/null"
                        remote_config = subprocess.check_output(command, shell=True)
                        logging.debug(f"Retreived configuration from {ip_address}: {remote_config}")
                        current_config = json.loads(remote_config)

                        for field in config_fields_to_migrate:
                            logging.debug(f"Key: {field}; old: {current_config[field]}; new: {template_data[field]}")
                            template_data[field] = current_config[field]

                        # Save modified configuration
                        if not os.path.exists(output_config_files_folder):
                            os.makedirs(output_config_files_folder)
                        new_config_file=f"{output_config_files_folder}/config.json.{uuid}"
                        with open(new_config_file, 'w') as c:
                            json.dump(template_data, c)
                        logging.info(f"Config file created: {new_config_file}")

                        # Check if device exists on target. If it already exists, skip
                        try:
                            target_device = target_balena.models.device.get_name(uuid)
                        except balena.exceptions.BalenaException as e:
                            # Register device if not found
                            logging.info(f"Registering device {uuid} to target fleet")
                            try:
                                target_balena.models.device.register(target_fleet_id, uuid)
                            except balena.exceptions.BalenaException as e:
                                logging.debug("Device {uuid} already exists. Skipping")
                                break

                        # Copy modified config to device
                        try:
                            command = f"scp -P 22222 {new_config_file} root@{ip_address}:/tmp/config.json"
                            logging.info(f"Copying: {command}")
                            result = subprocess.check_output(command, shell=True)
                            logging.info(f"Device's config.json {uuid} copied successfully.")
                        except Exception as e:
                            logging.error("Error copying file")
                            traceback.print_exc()
                            break

                        # Send migration script
                        try:
                            command = f"scp -P 22222 {device_script} root@{ip_address}:/tmp/migrate.sh"
                            logging.info(f"Copying: {command}")
                            result = subprocess.check_output(command, shell=True)
                            logging.info(f"Device's config.json {uuid} copied successfully.")
                        except Exception as e:
                            logging.error(f"Error copying script file")
                            traceback.print_exc()
                            break
                        # execute script
                        try:
                            command = f"ssh -p 22222 -o LogLevel=ERROR root@{ip_address} 'cd /tmp; chmod u+x migrate.sh; ./migrate.sh config.json > migrate.log' < /dev/null"
                            logging.info(f"Copying: {command}")
                            result = subprocess.check_output(command, shell=True)
                            logging.info(f"Device's config.json {uuid} copied successfully.")
                        except Exception as e:
                            logging.error(f"Error copying script file")
                            traceback.print_exc()
                            break
                        # wait 5 minutes
                        # check connectivity with newly migrated device
                        # send a batonfile

                    else:
                        logging.info(f"Skipping device {uuid}. Offline.")

                except Exception as e:
                    logging.error(f"Error processing device {uuid}: {str(e)}")
                    traceback.print_exc()



    except Exception as e:
        logging.error(f"Migration failed: {e}")
        traceback.print_exc()









source_endpoint = "balena-cloud.com"
source_api_key = os.getenv("BALENA_CLOUD_KEY")

target_endpoint = "balena-staging.com"
target_api_key = os.getenv("BALENA_STAGING_KEY")

target_org_owner = "g_rafael_morillo"
fleets = ["g_rafael_morillo1/tests"]
config_template_file = "./tests_template.config.json"

output_configs_path = "./configFiles"
config_fields_to_migrate = ["deviceApiKey", "deviceApiKeys","uuid", "deviceId"] # valid for balenaOS 2.58.6
device_script = "../device_migrate.sh"

try:
    logging.info("connecting to target")
    target_balena = balena.Balena({
        "balena_host": target_endpoint,
        "data_directory": "./.balenatarget",
    })
    target_balena.auth.login_with_token(target_api_key)
    logging.info(f"Logged in {target_balena}: {target_balena.auth.is_logged_in()}")


    logging.info("connecting to source")
    source_balena = balena.target_balena = balena.Balena({
        "balena_host": source_endpoint,
        "data_directory": "./.balenasource",
    })
    source_balena.auth.login_with_token(source_api_key)
    logging.info(f"Logged in {source_endpoint}: {source_balena.auth.is_logged_in()}")
except Exception:
    logging(f"Exception: {str(e)}")

migrate_devices(source_balena,
                target_balena,
                target_org_owner,
                fleets,
                config_template_file,
                output_configs_path,
                device_script)
