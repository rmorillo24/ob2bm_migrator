import balena
import os
import json
import logging
import subprocess
import traceback
import time

import balena.exceptions

# Setting up the logger
logging.basicConfig(format="%(asctime)s - %(levelname)s - %(message)s", level=logging.INFO)

def load_config_template(path):
    try:
        with open(path) as template_file:
            template_data = json.load(template_file)
        logging.debug(f"Loaded config template data: {template_data}")
        return template_data
    except Exception as e:
        logging.error(f"Failed to load config template: {e}")
        raise Exception("Error loading config.json template file")



def create_target_fleet(source_fleet_info, target_balena, target_org_owner):
    app_name = source_fleet_info['app_name']
    device_type = source_fleet_info['device_type']
    try:
        fleet_id = target_balena.models.application.create(app_name, device_type)
        logging.info(f"Created fleet {app_name} on target with ID {fleet_id}")
        return fleet_id
    except balena.exceptions.BalenaException as e:
        logging.error(f"Error creating fleet {app_name} of type {device_type}: {e}")
        raise Exception("Error creating fleet {app_name} of type {device_type}: {e}")



def process_devices(source_balena, target_balena, target_fleet_id, fleet_slug, template_data, output_config_folder, device_script):
    try:
        logging.info("Processing devices...")
        devices_in_source = source_balena.models.device.get_all_by_application(fleet_slug)
        logging.info(f"Devices found in source: {len(devices_in_source)}")
        for device in devices_in_source:
            process_device(device = device,
                            target_balena = target_balena,
                            target_fleet_id = target_fleet_id,
                            template_data = template_data,
                            output_folder = output_config_folder,
                            script_path = device_script)
    except Exception as e:
        logging.error(f"Failed to process devices: {e}")


def process_device(device, target_balena, target_fleet_id, template_data, output_folder, script_path):
    uuid = device['uuid']
    logging.info(f"Processing device {uuid}")
    if not device['is_online']:
        logging.info(f"Skipping device {uuid}. Offline.")
        return

    try:
        current_config = retrieve_device_config(device)
        new_device = register_device_if_missing(target_balena, target_fleet_id, uuid)
        config_file_path = generate_config_file(uuid = uuid,
                                                current_config = current_config,
                                                api_key =  new_device['api_key'],
                                                device_id = new_device['id'],
                                                target_fleet_id = target_fleet_id,
                                                template_data = template_data,
                                                output_folder = output_folder)
        deploy_configuration_and_scripts(uuid = uuid,
                                         device = device,
                                         config_file_path = config_file_path,
                                         script_path = script_path)
        migrate_device(uuid, device)
    except Exception as e:
        logging.error(f"Error processing device {uuid}: {e}")



def retrieve_device_config(device):
    ip_address = device['ip_address'].split()[0]
    logging.info(f"Retreiving configuration from IP: {ip_address}")
    command = f"ssh -p 22222 -o LogLevel=ERROR root@{ip_address} 'cat /mnt/boot/config.json' < /dev/null"
    remote_config = subprocess.check_output(command, shell=True)
    return json.loads(remote_config)



def register_device_if_missing(target_balena, target_fleet_id, uuid):
    try:
        logging.info("Registering device in target.")
        target_device = target_balena.models.device.get(uuid)
        logging.info(f"Device {uuid} already registered in target.")
        raise Exception(f"Device {uuid} already exists in target")
    except balena.exceptions.BalenaException:
        logging.info(f"Registering device {uuid} to target fleet.")
        reg_info = target_balena.models.device.register(target_fleet_id, uuid)
        return reg_info



def generate_config_file(uuid, current_config, api_key, device_id, target_fleet_id, template_data, output_folder):
    for field in config_fields_to_migrate:
        logging.debug(f"Key: {field}; old: {current_config[field]}; new: {template_data[field]}")
        template_data[field] = current_config[field]
    template_data['deviceApiKey'] = api_key
    key_to_modify = next(iter(template_data['deviceApiKeys']))
    template_data['deviceApiKeys'][key_to_modify] = api_key
    template_data['applicationId'] = target_fleet_id
    template_data['id'] = device_id
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    new_config_file = f"{output_folder}/config.json.{uuid}"
    with open(new_config_file, 'w') as file:
        json.dump(template_data, file)
    logging.info(f"Config file created: {new_config_file}")
    return new_config_file



def deploy_configuration_and_scripts(uuid, device, config_file_path, script_path):
    ip_address = device['ip_address'].split()[0]
    logging.info(f"Copying new config file to {ip_address}")
    scp_config = f"scp -P 22222 {config_file_path} root@{ip_address}:/tmp/config.json"
    scp_script = f"scp -P 22222 {script_path} root@{ip_address}:/tmp/migrate.sh"
    subprocess.check_output(scp_config, shell=True)
    subprocess.check_output(scp_script, shell=True)
    logging.info(f"Configuration and migration script deployed to device {uuid}.")
    return ip_address



def migrate_device(uuid, device):
    ip_address = device['ip_address'].split()[0]
    logging.info(f"Executing migration script on {uuid} in {ip_address}")
    execute_migration_script(ip_address)
    logging.info("Waiting for device to become active in target")
    
    is_online = False
    ip_address = None
    max_attempts = 7
    for attempt in range(max_attempts):
        is_online = device['is_online']
        if is_online:
            logging.info("Device is online. Gettin target's information")
            new_device = target_balena.models.device.get(uuid)
            try:
                ip_address = new_device['ip_address'].split()[0]
            except Exception as e:
                logging.info(f"Attempt {attempt + 1}: Device without IP ADDRESS. Checking again in one minute.")
                time.sleep(60)
                continue
            command = f"ssh -p 22222 -o LogLevel=ERROR root@{ip_address} 'touch /tmp/baton'"
            logging.info("touching baton file in {uuid}")
            result = subprocess.check_output(command, shell=True)
            logging.info(f"Device's baton {uuid} touched successfully.")
            break
        else:
            logging.info(f"Attempt {attempt + 1}: Device still offline. Checking again in one minute.")
            time.sleep(60)
    else:
        if not is_online:
            logging.error("Device is still offline after 7 attempts.")
        elif not ip_address:
            logging.error("Device did no send IP address. Baton file not sent.")
        raise Exception(f"Device {uuid} FAILED migration. Script could still be executing in the device")
        



def execute_migration_script(ip_address):
    logging.info("Executing migration script in device...")
    command = f"ssh -p 22222 -o LogLevel=ERROR root@{ip_address} 'cd /tmp; chmod u+x migrate.sh; nohup ./migrate.sh config.json > migrate.log 2>&1 < /dev/null & disown'"
    subprocess.check_output(command, shell=True)
    logging.info("Migration script executed.")



def migrate_devices(source_balena: balena.Balena, target_balena: balena.Balena, target_org_owner, fleets, config_template_path, output_config_folder, device_script):
    try:
        logging.info("Starting...")
        template_data = load_config_template(config_template_path)
        for fleet_slug in fleets:
            try:
                source_fleet_info = source_balena.models.application.get(fleet_slug)
            except balena.exceptions.BalenaException as e:
                raise Exception(f"Error getting info of fleet {fleet_slug} from source: {e}")
            logging.debug(f"Information from source fleet: {source_fleet_info}")
            try:
                app_name=source_fleet_info['app_name']
                target_fleet_info = target_balena.models.application.get_by_owner(app_name, owner=target_org_owner)
            except balena.exceptions.BalenaException as e:
                raise Exception(f"Error getting info of fleet {app_name} owned by {target_org_owner} from target: {e}")
            process_devices(source_balena, target_balena, target_fleet_info['id'], fleet_slug, template_data, output_config_folder, device_script)
    except Exception as e:
        logging.error(f"Migration failed: {e}")
        traceback.print_exc()


######
# Configuration
source_endpoint = "balena-cloud.com"
source_api_key = os.getenv("BALENA_CLOUD_KEY")
fleets = ["g_rafael_morillo1/tests"]

target_endpoint = "balena-staging.com"
target_api_key = os.getenv("BALENA_STAGING_KEY")
target_org_owner = "rmorillo"
config_template_file = "./tests_template.config.json"

output_configs_path = "./configFiles"
config_fields_to_migrate = ["uuid"] # valid for balenaOS 2.58.6
device_script = "../device_migrate.sh"

######
# Connections
logging.info(f"Connecting to source {source_endpoint}")
source_balena = balena.Balena({
    "balena_host": source_endpoint,
    "data_directory": "./.balenasource",
})
source_balena.auth.login_with_token(os.getenv("BALENA_CLOUD_KEY"))
logging.info(f"Logged in {source_endpoint}: {source_balena.auth.is_logged_in()}")

logging.info(f"Connecting to target {target_endpoint}")
target_balena = balena.Balena({
    "balena_host": target_endpoint,
    "data_directory": "./.balenatarget",
})
target_balena.auth.login_with_token(os.getenv("BALENA_STAGING_KEY"))
logging.info(f"Logged in {target_balena}: {target_balena.auth.is_logged_in()}")

######
# Go!
migrate_devices(
    source_balena,
    target_balena,
    target_org_owner,
    fleets,
    config_template_file,
    output_configs_path,
    device_script
)
