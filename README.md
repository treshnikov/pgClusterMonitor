# Overview
pgClusterMonitor is a service that controls a cluster of PostgreSQL DB with WAL streaming replication. The service considers the following cases:
- Performs auto-failover command for the standby DB node.
- Restores master DB as a standby DB in the case of two or more master DB nodes in the cluster.
- Directs replication of all standby DB nodes to a single master DB node.
- Controls synchronous_standby_names attribute of master DB node depends on standby nodes availability.

# Requirements
- pgClusterMonitor supports PostgreSQL version 12.
- Python 3.6.
- DB user mentioned in connectionstring for the local DB must be superuser to work with `ALTER SYSTEM ...` commands.

# How to use
- It is supposed that an instance of pgClusterMonitor should be deployed on each DB server. The following steps should be performed on each DB server.
- Install PostgreSQL 12 on each server in the cluster and set up WAL streaming replication. You can also use script for deploying PostgreSQL DB cluster from the [docker_postgresql_wal_replication](https://github.com/treshnikov/docker_postgresql_wal_replication) repository. The default configuration in `config.ini` is aimed at the Docker container `p1` from mentioned repository.
- Install Python version 3.6 or higher.
- Run the following command to install packages `pip install flake8 psycopg2 urllib3 coloredlogs pywin32 servicemanager`.
- Define settings in the `config.ini` file (see the chapter below).  
- Navigate to `pg_cluster_monitor` directory and run `python main.py`.
## Windows
- You can also install and run the service as a Windows Service. For this navigate to `pg_cluster_monitor` directory and run `python windows_service.py install --startup=auto` and then start the service `python windows_service.py start`. 
- In case of failure while starting the service check the following file in Python directory `Lib\site-packages\win32\pywintypes38.dll`. 
## Linux
To run the service as a Linux Service follow these steps:
- Create a file for the service: `sudo touch /lib/systemd/system/pg-cluster-monitor.service`.
- Edit `pg-cluster-monitor.service` file like this:
  ```ini
  [Unit]
  Description=PostgreSQL Cluster Monitor Service
  After=multi-user.target

  [Service]
  WorkingDirectory=/pg_cluster_monitor
  User=root
  Type=idle
  ExecStart=/usr/bin/python3 /pg_cluster_monitor/main.py
  Restart=always

  [Install]
  WantedBy=multi-user.target
  ```
where `/pg_cluster_monitor` is the directory with the source code. 
- Then run the following commands:
  ```sh
  sudo systemctl daemon-reload
  sudo systemctl enable pg-cluster-monitor.service
  sudo systemctl start pg-cluster-monitor.service
  ```
- Check the service status with `systemctl status pg-cluster-monitor.service` command.
- If you debug the service on a PostgreSQL cluster deployed on your computer in Docker containers - add to `host`-file aliases for Docker containers (for instance, `127.0.0.1 p1 and 127.0.0.1 p2`) in order to let the service work with the `primary_conninfo` correctly. The service compares `primary_conninfo` and connection string to master DB, so both parameters should point to the same host. For more details see `StandbyDbHandler.checkFollowingMaster()` at `standbyDbHandler.py`.   

# Description of the main algorithm
- Check the PostgreSQL server state. If the server is not running - run and wait for the server.
- For each DB in the cluster gather and log the following information:
    - Host
    - Connection status
    - Timestamp of last successful connection
    - DB time
    - DB size
    - DB role - MASTER or STANDBY
    - Replication position for STANDBY node
    - Synchronous_standby_names attribute
    - Size of pg_wal directory
    - Number of pg_wal directory files
    - Primary_conninfo attribute
    - Primary_slot_name attribute
    - Number of slots
- Log alerts if:
    - There is no standbys.
    - There is no master.
    - There is more than one master.
- If the local node is MASTER:
    - Select synchronous_standby_names parameter and perform "ALTER SYSTEM SET synchronous_standby_names TO '*'" or "...TO ''" depends on standby nodes availability.
    - If there is another master in the cluster
        - Select the master with the biggest DB.
        - If the local DB is not the biggest one - downgrade it after defined timeout and start following a new master. For downgrade first try to use pg_rewind and only then pg_basebackup in case of failure.
- If the local node is STANDBY:
    - Check the local network adapter and continue only if the connection is established.
    - If there is no master in the cluster:
        - Check time without master and consider promotion if defined timeout has exceeded.
            - Do promotion if the current standby is single standby in the cluster.
            - Do promotion if the current standby has the highest replication position than others standby nodes.
            - If there are two or more standby servers with the same replication position - select the first one. If local standby is not the first - skip promotion.
    - If there is only one master in the cluster:
        - Check that the current standby follows the single master.
        - If the standby followed another master - start following the single master.
    - If there is more than one master:
        - Do nothing, wait until there will be exactly one master.

# Config attributes description
```ini
# Connection string set to cluster nodes in format `hostName = connectionString`.
# Important: For the local DB it is important to use hostName or alias from `host` file instead of IP addresses in order to let the service connect to the local DB in case the network adapter is unavailable, disabled, or broken.
[cluster]
p1 = host=localhost port=1111 dbname=test user=postgres password=postgres sslmode=prefer sslcompression=1 krbsrvname=postgres target_session_attrs=any
p2 = host=p2 port=2222 dbname=test user=postgres password=postgres sslmode=prefer sslcompression=1 krbsrvname=postgres target_session_attrs=any

[main]
# Local DB server hostname.
local_node_host_name = p1

# Path to the data directory of the local PostgreSQL server.
pg_data_path = /var/lib/postgresql/data/pgdata

# Command to remove database directories. This command is executed before cmd_pg_basebackup_command.
cmd_create_db_directories = docker exec -t p1 runuser -l postgres -c "cd /var/lib/postgresql/data && mkdir -p db_dir && chown -R postgres:postgres db_dir"

# Command to create DB directories and set its permission. This command is executed before cmd_pg_basebackup_command. In Unix operating systems the DB directories must be owned to the user which runs the PostgreSQL DB service.
cmd_remove_db_directories = docker exec -t p1 runuser -l postgres -c "rm -rf /var/lib/postgresql/data/pgdata/* && rm -rf /var/lib/postgresql/data/db_dir/*"

# Name of the replication slot which is used for WAL streaming replication. 
# You can use `SELECT  * FROM pg_replication_slots` SQL-command to check available slots on the master DB node. 
# Slot should be created on master DB node during deploy WAL replication.
replication_slot_name = __slot

# Cluster nodes polling rate.
cluster_scan_period_sec = 10

# Timeout before failover after the master node is disappeared.
timeout_to_failover_sec = 15

# Timeout before starting downgrade a master DB to standby in case of multiple master DB nodes.
timeout_to_downgrade_master_sec = 35

# Delay for the checking the replication status after pg_rewind command execution and starting of DB.
timeout_to_check_replication_status_after_start_sec = 15

# Command to check the status of network adapters. The command should return a string which contains 'up' or 'connected' in case the network is available. 
cmd_get_network_status_string = docker exec -t p1 bash -c "cat /sys/class/net/eth0/operstate"

# Status when the network  is available
cmd_success_network_status_string = up

# Command to check the status of the PostgreSQL server. The command should return a string with `is running` in case of the PostgreSQL server is running.
cmd_get_db_status_string = docker exec -t p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_ctl status -D /var/lib/postgresql/data/pgdata"

# Status when the database server is running
cmd_success_db_status_string = is running

# Сommand to promote the local standby PostgreSQL DB to master.
# Important: In Unix operating systems the promote command must be invoked by the user who runs the PostgreSQL DB, usually it is `postgres` user. To perform this you can use command like `runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_ctl promote -D /var/lib/postgresql/data/pgdata"`
cmd_promote_standby_to_master = docker exec p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_ctl promote -D /var/lib/postgresql/data/pgdata"

# Command for synchronizing a PostgreSQL cluster with another copy of the same cluster, after the clusters' timelines have diverged.
# This command is used to turn the master DB into standby DB in case of multiple mater DB nodes.
# Dynamic parameters that are replaced at runtime:
#   %%pg_data_path%% - path to the data directory of the local PostgreSQL Server.
#   %%master_connstr%% - connection string to the master node.
cmd_pg_rewind_command = docker exec p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_rewind --target-pgdata=\"%%pg_data_path%%\" --source-server=\"%%master_connstr%%\" && touch %%pg_data_path%%/standby.signal && echo \"primary_conninfo = '%%master_connstr%%'\" >> %%pg_data_path%%/postgresql.auto.conf"

# Command for the creation of a standby node from the master node.
# This command is used to turn the master DB into standby DB in case of multiple mater DB nodes when the execution of cmd_pg_rewind_command has failed.
# Dynamic parameters that are replaced at runtime:
#   %%master_connstr%% - connection string to the master node.
#   %%slot_name%% - name of the replication slot.
cmd_pg_basebackup_command = docker exec p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_basebackup -D %%pg_data_path%% -d \"%%master_connstr%%\" -X stream -c fast -R --slot=%%slot_name%%"

# Command to start local PostgreSQL server.
cmd_start_db = docker exec -t p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_ctl start -o \"-p 1111\" -D /var/lib/postgresql/data/pgdata"

# Command to start local PostgreSQL server.
cmd_stop_db = docker exec -t p1 runuser -l postgres -c "/usr/lib/postgresql/12/bin/pg_ctl stop -D /var/lib/postgresql/data/pgdata"

# Address and port of the webserver which publishes `/status` and `/heartbeat` endpoints.
# To reach the webserver from another computer in the network - use hostname instead of localhost.
webserver_address = localhost
webserver_port = 9889
```
