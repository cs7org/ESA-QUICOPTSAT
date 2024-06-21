# Measure transmission duration using varying object sizes, implementations/branches, and Internet paths
#
# Connect to computers specified in config.yml and run experiments specified in testcases.json
# Implementations and folders specified below must be available on clients and server
#
# Created by Saeid Jahandar, FAU Erlangen, https://github.com/Saeid-jhn/pyqlog
# Modified by Matthias Hofstaetter, FAU Erlangen
#
# FIXME script is work in progress


import os
import paramiko
import subprocess
from datetime import datetime
from typing import Optional
import time
import yaml
import json
import logging
import argparse

# Configure logging
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s.%(msecs)03d\t%(levelname)s\t%(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S',
                    handlers=[
                        logging.StreamHandler(),  # Console output
                    ])


# File size 1KB = 1/1024 MB
# FILE_SIZE_STR_LIST = ['1KB', '10KB', '100KB', '1MB', '10MB', '1GB'] # EXAMPLE
FILE_SIZE_STR_LIST = ['0KB', '500KB', '1000KB', '1500KB', '2000KB', '2500KB', '3000KB', '3500KB', '4000KB', '4500KB', '5000KB', '5500KB', '6000KB', '6500KB', '7000KB', '7500KB', '8000KB', '8500KB', '9000KB', '9500KB', '10000KB']
NUM_ITR = 1               # Number of iterations
PICOQUIC_DIR = "$HOME/git/private-octopus/picoquic/master"
PICOQUIC_CR_DIR = "$HOME/git/hfstco/picoquic/careful_resume"
PICOQUIC_NJ_DIR = "$HOME/git/hfstco/picoquic/no_jump"
QUICHE_DIR = "$HOME/git/cloudflare/quiche/master"
QUICHE_CR_DIR = "$HOME/git/ana-cc/quiche/resume-final"
QLOG_PATH_IN_VM = "$HOME/testcases/qlog"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('config_path', type=str,
                        help='The file path of the configuration YAML file (for NetEm, sat).')
    parser.add_argument('testcases', type=str, help='The file path of the testcases JSON file.')
    parser.add_argument("--file_size", nargs='*', default=FILE_SIZE_STR_LIST,
                        help="Specify file size(s) as a list of strings (e.g., 10KB, 100MB, 1GB).")
    parser.add_argument('iterations', type=int, default=1, help="Number of iterations.")

    args = parser.parse_args()

    # datetime object containing current date and time
    now = datetime.now()
    dt_string = now.strftime("%Y-%m-%dT%H:%M:%S")

    # create directory to save data frame
    path = f"results/{dt_string}"
    if not os.path.exists(path):
        os.makedirs(path)
    qlog_path_on_host = f"./{path}/qlog"

    # Add FileHandler with this path
    add_file_handler_to_logger(f"{path}/run.log")

    # read testcases from json file
    testcases = read_testcases_from_file(args.testcases)

    endpoints = load_endpoints_config(args.config_path)

    # Create SSH connections
    ssh_connections = {}
    for name, endpoint_info in endpoints.items():
        ssh_client = connect_to_endpoints(
            endpoint_info['hostname'], endpoint_info['user'], endpoint_info.get('port'))
        if ssh_client:
            ssh_connections[name] = ssh_client

    obj_size_str_list = args.file_size

    for obj_size_str in obj_size_str_list:
        # Generate file for tests on server in specified path
        generate_file_on_server(
            ssh_connections["server"], obj_size_str, endpoints['server']['file_path'])

    # Determine queuing disciplines and log it
    get_queuing_disciplines(ssh_connections)

    # Disabled because it only works with origin/master branches
    # Get commit SHA of repositories to see if they are updated
    #get_commit_version(ssh_connections, testcases)

    run_num = 0
    run_tot = len(testcases)*NUM_ITR*len(obj_size_str_list)

    for itr in range(NUM_ITR):
        for obj_size_str in obj_size_str_list:
            for testcase in testcases:
                server = testcase["server"]
                client = testcase["client"]
                cc = testcase["cc"]
                run_num += 1
                server_port = determine_server_port(server, endpoints)
                logging.info(f"Using server port: {server_port} for quic\n")

                logging.info(
                    f"(RUN {run_num}/{run_tot}) Running QUIC server: {server}, client: {client}, congestion control: {cc}, file size: {obj_size_str}, iteration: {itr+1}/{NUM_ITR}")

                # log error if more than one person is using machines
                get_who(ssh_connections)

                # Delete qlog files
                delete_qlog(ssh_connections)

                # Run quic server
                run_quic_server(
                    ssh_connections["server"], server, cc, server_port, endpoints['server']['file_path'])

                # avoid 0rtt for picoquic
                if client == "picoquic":
                    delete_token_picoquic(ssh_connections["client"])

                # Run QUIC client:
                run_quic_client(ssh_connections["client"], client, endpoints["server"]["hostname"], server_port, cc, obj_size_str)

                time.sleep(3)

                # Close QUIC server:
                #close_server(ssh_connections["server"], server)

                time.sleep(3)

                # get qlog from VM
                name = f'{server}_{client}_{cc}.{obj_size_str}.itr{itr}'
                get_qlog(ssh_connections, server, client,
                         'testcases/qlog', qlog_path_on_host, name)

    # Close all SSH connections
    for ssh_client in ssh_connections.values():
        ssh_client.close()
        logging.info(f"SSH connection closed")

def get_who(ssh_connections):
    for vm_name, ssh_client in ssh_connections.items():
        if vm_name in ['server', 'client']:
            ssh_client = ssh_connections[vm_name]
            cmd = "who -q"
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            # Decode stdout
            output = stdout.read().decode('utf-8')

            # Split the output into lines
            lines = output.strip().split('\n')

            if len(lines) > 1:
                # Extract usernames and user count from the output
                # Split the first line by spaces to get individual usernames
                user_names = lines[0].split()
                # Extract the user count string
                user_count_str = lines[1].split('=')[1].strip()

                # Split on '=' and strip whitespace
                user_count_str = lines[1].split('=')[1].strip()
                try:
                    # Convert the count to an integer
                    user_count = int(user_count_str)
                except ValueError:
                    logging.error(
                        f"Failed to parse user count from: '{lines[1]}'")
                    return

                if user_count > 1:
                    # Check if all usernames are the same (by converting the list to a set and checking its length)
                    if len(set(user_names)) != 1:
                        # If there are different usernames, log as an error/warnning
                        if vm_name == 'client':  # client is bottleneck
                            logging.error(
                                f"{vm_name}: More than one user is logged in: {', '.join(user_names)}; Total users: {user_count}")
                        else:
                            logging.warning(
                                f"{vm_name}: More than one user is logged in: {', '.join(user_names)}; Total users: {user_count}")
                    else:
                        # If all usernames are the same, log as info
                        logging.info(
                            f"{vm_name}: Multiple sessions by the same user: {user_names[0]}; Total sessions: {user_count}")
                else:
                    # For a single user, simply log the information
                    logging.info(
                        f"{vm_name}: A user logged in: {user_names[0]}; Total users: {user_count}")

            else:
                logging.info(
                    "Unexpected output format from 'who -q': {output}")


def get_queuing_disciplines(ssh_connections):
    for vm_name, ssh_client in ssh_connections.items():
        if vm_name in ['server', 'client', 'raspberry']:
            ssh_client = ssh_connections[vm_name]
            if vm_name == 'raspberry':
                cmd = "/sbin/tc qdisc show"
            else:
                cmd = "tc qdisc show"
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            # Decode stdout and stderr
            output = stdout.read().decode('utf-8')
            error = stderr.read().decode('utf-8')

            # Log the output or error
            if output:
                logging.info(f"Queuing disciplines for {vm_name}:")
                for line in output.strip().split('\n'):
                    if line:  # Only log non-empty lines
                        logging.info(f"{line}")
            if error:  # If there's something in stderr, it often indicates an error or issue
                logging.error(
                    f"Error getting Queuing Disciplines for {vm_name}:\n{error}")


def add_file_handler_to_logger(log_file_path):
    """Add a FileHandler to the root logger dynamically."""
    file_handler = logging.FileHandler(log_file_path, mode='a')
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d\t%(levelname)s\t%(message)s', '%Y-%m-%d %H:%M:%S')
    file_handler.setFormatter(formatter)
    logging.getLogger().addHandler(file_handler)


def determine_server_port(server, endpoints):
    if "picoquic" in server:
        return endpoints["server"]["picoquic_port"]
    elif "quiche" in server:
        return endpoints["server"]["quiche_port"]
    elif "http2" in server:
        return endpoints["server"]["http2_port"]
    else:
        logging.error(
            f'The server name "{server}" is not included in testcases')
        raise Exception(
            f'The server name "{server}" is not included in testcases')


def read_testcases_from_file(json_path):
    try:
        with open(json_path, "r") as file:
            testcases = json.load(file)
        logging.info("Testcases successfully loaded from JSON file.")
        return testcases
    except FileNotFoundError:
        logging.error(
            "The testcases file could not be found at path: %s", json_path)
        return None
    except json.JSONDecodeError:
        logging.error(
            "The testcases file at path %s is not a valid JSON file.", json_path)
        return None
    except Exception as e:
        logging.exception(
            "An unexpected error occurred while reading the testcases file at path %s: %s", json_path, e)
        return None


def find_file(directory: str, prefix: str, suffix: str) -> Optional[str]:
    for filename in os.listdir(directory):
        if (not prefix or filename.startswith(prefix)) and filename.endswith(suffix):
            return filename
    return None


def get_qlog(ssh_connections, server, client, remote_subdir, dst_directory, new_name):
    # Check if the local directory exists; create it if it doesn't
    if not os.path.exists(dst_directory):
        os.makedirs(dst_directory)
        logging.info(f"Created directory {dst_directory}")

    for vm_name, ssh_client in ssh_connections.items():
        if vm_name in ['server', 'client']:
            logging.info(f"Running command on {vm_name} machine:")

            # Determine the remote directory path
            stdin, stdout, stderr = ssh_client.exec_command('echo $HOME')
            home_dir = stdout.read().decode('utf-8').strip()
            remote_directory = os.path.join(home_dir, remote_subdir)
            logging.info(f"Remote directory: {remote_directory}")

            try:
                # Open an SFTP session on the existing SSH connection
                sftp = ssh_client.open_sftp()
                qlog_files = []
                log_files = []
                plog_files = []  # Performance log file for picoquic
                # Wait for the qlog files to be created


                # Now, also add any txt files that might be present, without waiting for them
                remote_files = sftp.listdir(remote_directory)

                # Copy the file(s) from the remote VM to the local machine with the new name
                for file_name in remote_files:
                    remote_file_path = os.path.join(remote_directory, file_name)

                    if file_name.endswith('.txt'):
                        extension = 'server.log' if vm_name == 'server' else 'client.log'
                    elif file_name.endswith('.sqlog'):
                        extension = 'server.sqlog' if vm_name == 'server' else 'client.sqlog'
                    elif file_name.endswith('.qlog'):
                        extension = 'server.qlog' if vm_name == 'server' else 'client.qlog'
                    elif file_name.endswith('.key'):
                        extension = 'server.key' if vm_name == 'server' else 'client.key'
                    elif file_name.endswith('.csv'):
                        extension = 'server.csv' if vm_name == 'server' else 'client.csv'

                    local_file_path = os.path.join(dst_directory, f"{new_name}.{extension}")
                    sftp.get(remote_file_path, local_file_path)
                    logging.info(
                        f"Successfully copied {remote_file_path} to {local_file_path} in {vm_name}")

                # Close the SFTP session
                sftp.close()

            except Exception as e:
                logging.exception(f"Failed to copy file from {vm_name}: {e}")


def delete_token_picoquic(ssh_client):
    cmd = f"cd {PICOQUIC_DIR} && rm -f demo_ticket_store.bin && rm -f demo_token_store.bin"
    stdin, stdout, stderr = ssh_client.exec_command(cmd)

    # Checking for command execution errors (optional but recommended)
    error_output = stderr.read().decode().strip()
    if error_output:
        logging.error(f"Error deleting token files: {error_output}")
    else:
        logging.info("Picoquic token files deleted successfully.")

    logging.debug(f"Executed command: {cmd}")


def close_server(ssh_client, server):
    if "picoquic" in server:
        cmd = "pkill -15 -u $(whoami) picoquicdemo"
    elif "quiche" in server:
        cmd = "pkill -15 -u $(whoami) quiche-server"
    elif "http2" in server:
        cmd = "sudo docker stop http3-nginx"

    if cmd:  # Ensure cmd is not empty
        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        # Wait for the command to complete
        exit_status = stdout.channel.recv_exit_status()

        if exit_status == 0:
            logging.info(
                f"{server} server terminated successfully.")
        else:
            logging.error(
                f"Command '{cmd}' failed with exit status {exit_status}")
    else:
        logging.warning(
            f"Unsupported server type '{server}'. Command not executed.")


def run_iperf_client(ssh_client, host, port):
    cmd = f"iperf -c {host} -p {port}"


def run_quic_client(ssh_client, client, server_ip, server_port, cc, file_size_str):
    # Convert file size to bytes
    if client == "picoquic":
        base_cmd = f"cd {PICOQUIC_DIR} && ./picoquicdemo -D -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -n test {server_ip} {server_port} /{file_size_str}.txt"
    elif client == "picoquic-ref":
        base_cmd = f"cd {PICOQUIC_NJ_DIR} && ./picoquicdemo -D -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -n test {server_ip} {server_port} /{file_size_str}.txt"
    elif client == "picoquic-cr":
        base_cmd = f"cd {PICOQUIC_CR_DIR} && ./picoquicdemo -D -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -n test {server_ip} {server_port} /{file_size_str}.txt"
    elif client == "quiche":
        base_cmd = f"cd {QUICHE_DIR} && export QLOGDIR={QLOG_PATH_IN_VM} && RUST_LOG=trace ./target/release/quiche-client --wire-version 1 --cc-algorithm {cc} --no-verify https://{server_ip}:{server_port}/{file_size_str}.txt &> {QLOG_PATH_IN_VM}/log.txt"
    elif client == "quiche-cr":
        base_cmd = f"cd {QUICHE_CR_DIR} && export QLOGDIR={QLOG_PATH_IN_VM} && RUST_LOG=trace ./target/release/quiche-client --wire-version 1 --cc-algorithm {cc} --no-verify https://{server_ip}:{server_port}/{file_size_str}.txt &> {QLOG_PATH_IN_VM}/log.txt"
    elif client == "http2":
        base_cmd = f"wget {server_ip}:{server_port}/{file_size_str}.txt &> {QLOG_PATH_IN_VM}/log.txt"

    # Construct the full command (removed SSLKEYLOGFILE for simplification)
    cmd = base_cmd

    logging.info("CMD-client: %s", cmd)

    if cmd:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        exit_status = stdout.channel.recv_exit_status()
        logging.info("Client returned successfully")
        logging.info(f"CMD-client:\t{cmd}")
    else:
        logging.error(
            "Client start error.")


def run_quic_server(ssh_client, server_name, cc, server_port, file_path):
    cmd = ""
    # Run server
    if server_name == "picoquic":
        base_cmd = f"cd {PICOQUIC_DIR} && ./picoquicdemo -1 -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -p {server_port} -w {file_path}"
    elif server_name == "picoquic-ref":
        base_cmd = f"cd {PICOQUIC_NJ_DIR} && ./picoquicdemo -1 -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -p {server_port} -w {file_path}"
    elif server_name == "picoquic-cr":
        base_cmd = f"cd {PICOQUIC_CR_DIR} && ./picoquicdemo -1  -J -Y 3750000 -Z 600000 -l {QLOG_PATH_IN_VM}/log.txt -F {QLOG_PATH_IN_VM}/log.csv -G {cc} -q {QLOG_PATH_IN_VM} -p {server_port} -w {file_path}"
    elif server_name == "quiche":
        base_cmd = f"cd {QUICHE_DIR} && export QLOGDIR={QLOG_PATH_IN_VM} && RUST_LOG=trace ./target/release/quiche-server --no-retry --cc-algorithm {cc}  --cert apps/src/bin/cert.crt --key apps/src/bin/cert.key --root {file_path} --listen 0.0.0.0:{server_port} &> {QLOG_PATH_IN_VM}/log.txt"
    elif server_name == "quiche-cr":
        base_cmd = f"cd {QUICHE_CR_DIR} && export QLOGDIR={QLOG_PATH_IN_VM} && RUST_LOG=trace ./target/release/quiche-server --no-retry --cc-algorithm {cc}  --cert apps/src/bin/cert.crt --key apps/src/bin/cert.key --root {file_path} --listen 0.0.0.0:{server_port} &> {QLOG_PATH_IN_VM}/log.txt"
    elif server_name == "http2":
        base_cmd = f"docker start http3-nginx"

    # Construct the full command (removed SSLKEYLOGFILE for simplification)
    cmd = base_cmd

    if cmd:
        stdin, stdout, stderr = ssh_client.exec_command(cmd)
        logging.info("Server is running successfully")
        logging.info(f"CMD-server:\t{cmd}")
    else:
        logging.error(
            "Server name is not correct. Please check the server_name argument.")


def delete_qlog(ssh_connections):
    # Define the list of file extensions to remove
    file_extensions = ["qlog", "sqlog", "log", "txt", "key", "csv"]

    # Create a pattern to match all specified file extensions
    extensions_pattern = " -o ".join(
        [f"-name '*.{ext}'" for ext in file_extensions])

    # Define the command to remove files with the specified extensions
    cmd = f'find {QLOG_PATH_IN_VM} -type f \\( {extensions_pattern} \\) -delete'

    for vm_name, ssh_client in ssh_connections.items():
        if vm_name in ['server', 'client']:
            logging.info(
                f"Running command on {vm_name} machine to delete qlog/log files.")
            ssh_client = ssh_connections[vm_name]
            stdin, stdout, stderr = ssh_client.exec_command(cmd)

            exit_status = stdout.channel.recv_exit_status()
            if exit_status == 0:
                logging.info(
                    f"qlog/log files successfully deleted in {vm_name}.")
            else:
                error_msg = stderr.read().decode().strip()
                logging.error(
                    f"Failed to delete qlog/log files in {vm_name}. Error: {error_msg}")


def convert_size_to_bytes(size_str):
    """Convert size string to bytes, handling KB, MB, and GB."""
    if 'KB' in size_str:
        return int(size_str.replace('KB', '')) * 1024
    elif 'MB' in size_str:
        return int(size_str.replace('MB', '')) * 1024 * 1024
    elif 'GB' in size_str:
        return int(size_str.replace('GB', '')) * 1024 * 1024 * 1024
    else:
        raise ValueError("Unsupported size unit")


# Function to generate file on server
def generate_file_on_server(ssh_client, file_size_str, base_path):
    # Determine file size in bytes and create a filename based on the size string
    file_size_bytes = convert_size_to_bytes(file_size_str)
    file_name = f"{file_size_str}.txt"

    # Construct the complete file path
    file_path = f"{base_path}/{file_name}"

    try:
        # Execute the 'dd' command to generate the file
        cmd = f"mkdir -p $(dirname {file_path}) && dd if=/dev/zero of={file_path} bs={file_size_bytes} count=1"
        stdin, stdout, stderr = ssh_client.exec_command(cmd)

        logging.info(
            f"File {file_name} generated successfully at {file_path} on server")

    except Exception as e:
        logging.exception(
            f"Exception occurred while generating file on server: {e}")


def connect_to_endpoints(server_ip, username, port=None):
    # Create an SSH client and set the missing host key policy
    ssh_client = paramiko.SSHClient()
    ssh_client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

    # Use the default SSH port if no port is provided
    port = int(port) if port else 22

    try:
        ssh_client.connect(server_ip, username=username, port=port)
        logging.info(
            f"Connected successfully to {username}@{server_ip}:{port}")
        return ssh_client
    except paramiko.ssh_exception.PasswordRequiredException as e:
        logging.error("A passphrase is required to unlock the private key.")
    except paramiko.ssh_exception.AuthenticationException as e:
        logging.error(
            "Authentication failed, please check your credentials: %s", str(e))
    except paramiko.ssh_exception.SSHException as e:
        logging.error(
            "Error connecting to server, SSH session not established: %s", str(e))
    except Exception as e:
        logging.error("Unexpected error connecting to server: %s", str(e))
    return None


def load_endpoints_config(yaml_file):
    try:
        with open(yaml_file, 'r') as file:
            config = yaml.safe_load(file)
        endpoints = config.get('endpoints', {})
        logging.info(
            f"Endpoint configurations are loaded successfully from {yaml_file}.")
        return endpoints
    except Exception as e:
        logging.error(
            f"Failed to load endpoint configurations from {yaml_file}: {e}")
        return {}


if __name__ == "__main__":
    logging.info("Scripts started.")
    main()
