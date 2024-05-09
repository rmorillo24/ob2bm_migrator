# Balena Fleet Migration Scripts

These scripts facilitates the migration of fleets and devices from a source Balena account to a target Balena account, managing configurations and ensuring seamless transition between accounts.

To "guarantee" that the migration process works, it uses a baton file copied to the newly migrated device that, if the device doesn't find it on a given time, it will rollback to the previous server

## Server script

This script will iterate through the fleets you want, and migrate each of the devices



### Use:

1. Configure the following variables

- `balena_cloud_key`: The API key for the source Balena account.
- `balena_staging_key`: The API key for the target Balena account.
- `source_endpoint`: The URL for the source Balena endpoint.
- `target_endpoint`: The URL for the target Balena endpoint.
- `target_org_owner`: The owner organization of the target Balena account.
- `fleets`: A list of fleet slugs (strings) to migrate from the source to the target.
- `config_template_file`: The path to config.json file containing the configuration template for the target fleet.
- `output_configs_path`: The directory where modified configuration files for each device will be stored.
- `config_fields_to_migrate`: A list of configuration fields to copy from the current device configuration to the new one.
- `device_script`: A path to the shell script that facilitates migration on individual devices.

2. Execute

`python migrate_b2b.py`

3. Clean

The script has created two `.balena` folders. You need to delete them if the credentials, or the target or source servers change.


### Process:

High level, the migration process is as follows:

1. **Fleet Processing:** For each fleet in the `fleets` variable:

   - Retrieves fleet information from the source Balena account.
   - Checks if the fleet already exists in the target account, creating it if necessary.
   - Gets the list of devices from the source fleet.

2. **Devices Migration:** For each device in the source fleet:

   - Check if the device is online.
   - Retrieve the `config.json` file by SSH-ing into it.
   - Copy specified configuration fields to a new template and saves it.
   - Register the device in the target fleet if necessary.
   - Copy the new `config.json` file and the migration script to the device.
   - Execute the script on the device.
   - Send the baton file through the new server

## Device's script

The script `device_migrate.sh` is sent to each of the devices and will via run via SSH.

This script may have to be changed depending on the environments you are using or OS verions.

The general process is:

0. ** Backup** the current `config.json` file
1. ** Execute `balena-os join`** 
2. ** Check the baton file** sent by the new server
3. ** Revert to old server** if the baton file is not there in x minutes.

