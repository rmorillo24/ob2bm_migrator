import balena
import os


target_endpoint = "balena-staging.com"
target_api_key = os.getenv("BALENA_STAGING_KEY")


login_command = "cd ./{environment}; balena --token {target_api_key}"
ssh_command = "cd ./{environment}; balena --token {target_api_key}"
