import time
import logging
from cluster.cluster import DbCluster
from monitor.master_db_handler import MasterDbHandler
from monitor.standby_db_handler import StandbyDbHandler
from cluster.cluster_node_role import DbRole
from monitor.webserver import WebServer
from utils import shell
from threading import Lock


class DbClusterMonitor:
    """Class monitors DB nodes of the cluster, performs auto-failover command,
    handles the cases when a standby DB is down and when the cluster has two master DB."""

    def __init__(self, config):
        self.logger = logging.getLogger("logger")
        self.logger.info(f"DbClusterMonitor started with config {config._sections}")
        main_config_section = config["main"]
        self.local_node_host_name = main_config_section["local_node_host_name"]
        self.db_cluster = DbCluster(config.items("cluster"))
        self.cluster_scan_period_sec = main_config_section.getint("cluster_scan_period_sec")
        self.get_network_status_string_command = main_config_section["cmd_get_network_status_string"]
        self.success_network_status_string = main_config_section["cmd_success_network_status_string"]
        self.timeout_to_failover_sec = main_config_section.getint("timeout_to_failover_sec")
        self.timeout_to_downgrade_master_sec = main_config_section.getint("timeout_to_downgrade_master_sec")
        self.promote_command = main_config_section["cmd_promote_standby_to_master"]
        self.get_db_status_string_command = main_config_section["cmd_get_db_status_string"]
        self.success_db_status_string = main_config_section["cmd_success_db_status_string"]
        self.start_db_command = main_config_section["cmd_start_db"]
        self.stop_db_command = main_config_section["cmd_stop_db"]
        self.isRunning = None
        self.replication_slot_name = main_config_section["replication_slot_name"]
        self.pg_rewind_command = main_config_section["cmd_pg_rewind_command"]
        self.pg_basebackup_command = main_config_section["cmd_pg_basebackup_command"]
        self.pg_data_path = main_config_section["pg_data_path"]
        self.create_db_directories_command = main_config_section["cmd_create_db_directories"]
        self.remove_db_directories_command = main_config_section["cmd_remove_db_directories"]
        self.get_cluster_state_lock = Lock()
        self.webserver = WebServer(self.get_cluster_state, main_config_section["webserver_address"], int(main_config_section["webserver_port"]))
        self.timeout_to_check_replication_status_after_start_sec = main_config_section.getint("timeout_to_check_replication_status_after_start_sec")

    def check_local_postgre_sql_server_status(self):
        """If the local PostgreSQL server is not running - try to run and wait for the server. If the server is still
        not available - return False. """
        self.logger.debug("Check that the local server of PostgreSQL is running.")
        cmd_result = shell.execute_cmd(self.get_db_status_string_command)

        if self.success_db_status_string not in cmd_result:
            self.logger.critical("Local PostgreSQL server is not running, trying to start it.")
            shell.execute_cmd(self.start_db_command)
            return False

        self.logger.debug("Local PostgreSQL server is running.")

        return True

    def get_cluster_state(self):
        """Returns the state of the cluster as json, threadsafe."""
        with self.get_cluster_state_lock:
            return self.db_cluster.nodes

    def analyze_cluster(self):
        """Main procedure which performs cluster monitoring."""

        # check local PostgreSQL server state
        if not self.check_local_postgre_sql_server_status():
            return

        # gather information from cluster nodes
        self.db_cluster.update()
        if not (self.local_node_host_name in self.db_cluster.nodes):
            self.logger.error(f"Local DB with host name {self.local_node_host_name} is not in the cluster.")
            return

        # check connection to the local DB
        node_info = self.db_cluster.nodes[self.local_node_host_name]
        if not node_info.connected:
            self.logger.warning(f"There is no connection with {node_info.host_name}. Keep waiting for the connection.")
            return

        # consider cluster state
        db = None
        if node_info.state.db_role == DbRole.MASTER:
            db = MasterDbHandler(self.local_node_host_name, self.start_db_command, self.stop_db_command,
                                 self.pg_rewind_command, self.pg_basebackup_command, self.pg_data_path, self.replication_slot_name,
                                 self.create_db_directories_command, self.remove_db_directories_command, self.timeout_to_downgrade_master_sec,
                                 self.timeout_to_check_replication_status_after_start_sec)

        if node_info.state.db_role == DbRole.STANDBY:
            db = StandbyDbHandler(self.local_node_host_name, self.get_network_status_string_command,
                                  self.timeout_to_failover_sec, self.promote_command, self.replication_slot_name,
                                  self.success_network_status_string)

        if db:
            db.handle_cluster_state(self.db_cluster)

    def stop(self):
        """Stop service."""
        self.webserver.stop()
        self.logger.info("Service has received a stop command.")
        self.isRunning = False

    def start(self):
        """Start service and run the main monitoring cycle of the DB cluster."""
        self.logger.info("Service is starting.")
        self.isRunning = True
        self.webserver.start()
        while self.isRunning:
            try:
                self.analyze_cluster()
            except Exception as ex:
                self.logger.exception(f"Main cycle: {ex}")
            time.sleep(self.cluster_scan_period_sec)
        self.logger.info("The service main cycle has been finished.")
