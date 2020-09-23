import logging
import datetime
import time
from utils import db
from utils import shell
from cluster.cluster_node_role import DbRole


class MasterDbHandler:
    """Contains handlers for a master node."""

    SUCCESS_REPLICATION_STATUS = "streaming"
    REPLICATION_SLOT_NAME_ATTR = "%slot_name%"
    PD_DATA_PATH_ATTR = "%pg_data_path%"
    PRIMARY_CONN_STR_ATTR = "%master_connstr%"

    def __init__(self, local_node_host_name, start_db_command, stop_db_command,
                 pg_rewind_command, pg_basebackup_command, pg_data_path, replication_slot_name,
                 create_db_directories_command, remove_db_directories_command, timeout_to_downgrade_master_sec,
                 timeout_to_check_replication_status_after_start_sec):
        self.logger = logging.getLogger("logger")
        self.local_node_host_name = local_node_host_name
        self.start_db_command = start_db_command
        self.stop_db_command = stop_db_command
        self.pg_rewind_command = pg_rewind_command
        self.pg_basebackup_command = pg_basebackup_command
        self.replication_slot_name = replication_slot_name
        self.pg_data_path = pg_data_path
        self.create_db_directories_command = create_db_directories_command
        self.remove_db_directories_command = remove_db_directories_command
        self.timeout_to_downgrade_master_sec = timeout_to_downgrade_master_sec
        self.timeout_to_check_replication_status_after_start_sec = timeout_to_check_replication_status_after_start_sec

    def update_synchronous_standby_names(self, cluster):
        """Check synchronous_standby_names depends on standby servers availability."""
        conn_str = cluster.nodes[self.local_node_host_name].connection_string
        current_synchronous_standby_names = cluster.nodes[self.local_node_host_name].state.synchronous_standby_names

        if len(cluster.connected_standby_nodes_names) == 0 and not current_synchronous_standby_names == '':
            self.logger.warning(f"Set synchronous_standby_names to '' for {self.local_node_host_name} because "
                                f"there is no standby servers in the cluster.")
            db.alter_postgre_sql_config(conn_str, 'synchronous_standby_names', '')

        if len(cluster.connected_standby_nodes_names) >= 1 and not current_synchronous_standby_names == '*':
            self.logger.warning(f"Set synchronous_standby_names to '*' for {self.local_node_host_name} "
                                f"because standby server has appeared.")
            db.alter_postgre_sql_config(conn_str, 'synchronous_standby_names', '*')

    def downgrade_local_master_db_to_standby(self, cluster, primary_connection_string):
        """Executes sync command. If after executing rewind command replication does not work
        then executes pg_basebackup command"""

        self.logger.critical("Trying to downgrade the local master DB to standby using pg_rewind.")

        shell.execute_cmd(self.stop_db_command)
        shell.execute_cmd(self.pg_rewind_command.replace(self.PD_DATA_PATH_ATTR, self.pg_data_path).replace(self.PRIMARY_CONN_STR_ATTR, primary_connection_string))
        shell.execute_cmd(self.start_db_command)

        self.logger.debug(f"Waiting for the replication starting for {self.timeout_to_check_replication_status_after_start_sec} sec.")
        time.sleep(self.timeout_to_check_replication_status_after_start_sec)
        self.logger.info("Checking the replication status.")

        # check replication status
        status, err = db.try_fetch_one(cluster.nodes[self.local_node_host_name].connection_string, "SELECT status FROM pg_stat_wal_receiver")

        if err or status is None or status != self.SUCCESS_REPLICATION_STATUS:
            self.logger.critical(f"Downgrade the local master DB to standby using pg_rewind has failed. Streaming status = {status}. Trying to downgrade using pg_basebackup.")
            shell.execute_cmd(self.stop_db_command)
            shell.execute_cmd(self.remove_db_directories_command)
            shell.execute_cmd(self.create_db_directories_command)
            shell.execute_cmd(self.pg_basebackup_command.replace(self.PD_DATA_PATH_ATTR, self.pg_data_path).replace(self.PRIMARY_CONN_STR_ATTR, primary_connection_string).replace(self.REPLICATION_SLOT_NAME_ATTR, self.replication_slot_name))
            shell.execute_cmd(self.start_db_command)
            self.logger.critical("Downgrade the local master DB to standby using pg_basebackup has completed.")
            return

        self.logger.critical("Downgrade the local master DB to standby using pg_rewind has completed successfully.")

    def try_get_master_node_with_the_biggest_db(self, cluster):
        """Tries get DB node with the biggest DB size.
           If DB node has found then returns node otherwise returns None"""

        # todo: checking the size of the database may not be enough,
        # consider checking other possible replication attributes or DB parameters to find out if the DB has the priority

        max_db_size = 0
        master_node_with_max_db_size = None

        for nodeName, attrs in cluster.nodes.items():
            node = cluster.nodes[nodeName]

            if node.state.db_role != DbRole.MASTER or not node.connected:
                continue

            if node.state.db_size_in_bytes is not None and node.state.db_size_in_bytes > max_db_size:
                max_db_size = node.state.db_size_in_bytes
                master_node_with_max_db_size = node

        return master_node_with_max_db_size

    def consider_decision_to_downgrade_master_to_standby(self, cluster):
        """Analyzes the priority of the current master against others and consider a decision to restore the local DB
        from another master DB node as a standby DB node."""

        if cluster.several_masterdb_in_cluster_event_start_time is None:
            return

        time_delta_sec = (datetime.datetime.now() - cluster.several_masterdb_in_cluster_event_start_time).total_seconds()

        self.logger.warning(f"Consider downgrade because there are several masters DB in the cluster for {time_delta_sec} sec.")

        if time_delta_sec < self.timeout_to_downgrade_master_sec:
            self.logger.warn(f"Downgrade won't be considered because there are several masters DB in the cluster for {time_delta_sec} sec, but timeout to downgrade is {self.timeout_to_downgrade_master_sec} sec.")
            return

        master_node_with_the_biggest_db = self.try_get_master_node_with_the_biggest_db(cluster)

        if master_node_with_the_biggest_db is None:
            self.logger.critical("Downgrade to standby won't be performed on this node. Master node with the biggest DB size has not found.")
            return

        local_node = cluster.nodes[self.local_node_host_name]

        self.logger.warn(f"Name of the master node with the biggest DB size = {master_node_with_the_biggest_db.host_name}. "
                         f"DB size of the master node with the biggest DB size = {master_node_with_the_biggest_db.state.db_size_in_bytes}")
        self.logger.warn(f"Name of the local node = {self.local_node_host_name}. "
                         f"DB size of the local node = {local_node.state.db_size_in_bytes}")

        if master_node_with_the_biggest_db.state.db_size_in_bytes == local_node.state.db_size_in_bytes:
            self.logger.critical("Local master DB won't be downgraded to standby DB because It has the biggest DB size of all master DB.")
            return

        self.downgrade_local_master_db_to_standby(cluster, master_node_with_the_biggest_db.connection_string)

    def handle_cluster_state(self, cluster):
        """Considers the current state of the cluster and perform actions for the current master DB node."""

        self.update_synchronous_standby_names(cluster)

        # two or more masters detected
        if len(cluster.connected_master_nodes_names) > 1:
            self.consider_decision_to_downgrade_master_to_standby(cluster)
