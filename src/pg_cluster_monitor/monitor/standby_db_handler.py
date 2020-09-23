import logging
import datetime
from utils import shell
from utils import db
from cluster.cluster_node_role import DbRole


class StandbyDbHandler:
    """Contains handlers for a standby node."""

    def __init__(self, local_node_host_name, get_network_status_string_command, timeout_to_failover_sec,
                 promote_command, replication_slot_name, success_network_status_string):
        self.logger = logging.getLogger("logger")
        self.local_node_host_name = local_node_host_name
        self.get_network_status_string_command = get_network_status_string_command
        self.timeout_to_failover_sec = timeout_to_failover_sec
        self.promote_command = promote_command
        self.replication_slot_name = replication_slot_name
        self.success_network_status_string = success_network_status_string

    def check_network_connection(self):
        """Execute cmd_get_network_status_string command from config.ini and returns True if the result contains success_network_status_string from config.ini."""
        self.logger.debug("Check network connection.")
        check_network_connection_result = shell.execute_cmd(self.get_network_status_string_command)

        # check 'connected' string for Windows `netsh interface ipv4 show interfaces` command
        # check 'up' for Linux 'cat /sys/class/net/eth0/operstate' command
        if self.success_network_status_string in check_network_connection_result:
            self.logger.debug("Local network connection is available.")
            return True

        return False

    def do_failover(self, connection_string_to_local_db_node):
        """Execute promote command for performing DB failover."""
        self.logger.critical(f"Execute PROMOTE command for node {self.local_node_host_name}")
        shell.execute_cmd(self.promote_command)

        self.logger.warning(f"Execute CHECKPOINT command for node {self.local_node_host_name}")
        db.execute(connection_string_to_local_db_node, "CHECKPOINT;")

        db.alter_postgre_sql_config(connection_string_to_local_db_node, 'synchronous_standby_names', '')
        db.execute(connection_string_to_local_db_node, f"SELECT * FROM pg_create_physical_replication_slot('{self.replication_slot_name}')")
        db.execute(connection_string_to_local_db_node, "SELECT pg_reload_conf();")

    def does_the_local_standby_node_have_the_highest_replication_position(self, cluster):
        """Returns true if the local standby DB has the highest replication position against other standby nodes."""

        max_replication_position_as_number = 0
        max_replication_position_as_string = None
        index_of_standby_node_with_max_replication_position = None
        local_node_index_in_cluster = None
        idx = 0
        for nodeName, attrs in cluster.nodes.items():
            if nodeName == self.local_node_host_name:
                local_node_index_in_cluster = idx

            node = cluster.nodes[nodeName]
            if node.state.db_role == DbRole.STANDBY and node.connected \
                    and node.state.replication_position_as_number > max_replication_position_as_number:
                max_replication_position_as_number = node.state.replication_position_as_number
                max_replication_position_as_string = node.state.replication_position
                index_of_standby_node_with_max_replication_position = idx

            idx = idx + 1

        res = index_of_standby_node_with_max_replication_position == local_node_index_in_cluster

        if not res:
            self.logger.critical(f"Promote command won\'t be performed because the cluster has a standby DB node with "
                                 f"replication position {max_replication_position_as_string} "
                                 f"({max_replication_position_as_number}) which is greater than the local DB "
                                 f"replication position {cluster.nodes[self.local_node_host_name].state.replication_position} "
                                 f"({cluster.nodes[self.local_node_host_name].state.replication_position_as_number})")
        else:
            self.logger.critical(f"Promote command will be performed because the local standby DB has the highest "
                                 f"replication position {cluster.nodes[self.local_node_host_name].state.replication_position} "
                                 f"({cluster.nodes[self.local_node_host_name].state.replication_position_as_number}) "
                                 f"against other standby nodes.")

        return res

    def consider_failover(self, cluster):
        """Check time without master and consider a promotion."""
        if cluster.no_masterdb_in_cluster_event_start_time is None:
            return

        time_delta_sec = (datetime.datetime.now() - cluster.no_masterdb_in_cluster_event_start_time).total_seconds()
        self.logger.warning(f"Consider failover because there is no master DB in the cluster for {time_delta_sec} sec.")

        if time_delta_sec < self.timeout_to_failover_sec:
            return

        if not self.does_the_local_standby_node_have_the_highest_replication_position(cluster):
            return

        self.logger.critical(f"Perform FAILOVER because there is no master DB in the cluster for {time_delta_sec} "
                             f"which is more than defined maximum timeout {self.timeout_to_failover_sec} sec.")
        self.do_failover(cluster.nodes[self.local_node_host_name].connection_string)

    def check_following_master(self, cluster):
        """Check that the current standby follows the single master."""
        self.logger.debug("Check that primary_conninfo refers to master DB.")
        local_db_node = cluster.nodes[self.local_node_host_name]
        master_db_node = cluster.nodes[cluster.connected_master_nodes_names[0]]

        local_node_connection_string_attributes = shell.parse_postgre_sql_connection_string(local_db_node.state.primary_conn_info)
        master_db_node_connection_string_attributes = shell.parse_postgre_sql_connection_string(master_db_node.connection_string)

        if local_node_connection_string_attributes['host'] == master_db_node_connection_string_attributes['host'] and \
           local_node_connection_string_attributes['user'] == master_db_node_connection_string_attributes['user'] and \
           local_node_connection_string_attributes['password'] == master_db_node_connection_string_attributes['password']:
            self.logger.debug("Attribute primary_conninfo refers to the relevant master DB node.")
            return

        self.logger.critical(f"Detects that the local standby DB is following a wrong master DB. \
            The current master connection string '{master_db_node.connection_string}' is different to the current \
            value of primary_conninfo '{local_db_node.state.primary_conn_info}'")

        db.alter_postgre_sql_config(local_db_node.connection_string, 'primary_conninfo', master_db_node.connection_string)

    def handle_cluster_state(self, cluster):
        """Considers the current state of the cluster and perform actions for the current standby DB node."""

        # check the local network adapter and continue only if the connection is established.
        if not self.check_network_connection():
            self.logger.warning("Network connection is not available.")
            return

        # no master DB in the cluster
        if len(cluster.connected_master_nodes_names) == 0:
            # consider failover decision
            self.consider_failover(cluster)

        # exactly one master DB in the cluster
        if len(cluster.connected_master_nodes_names) == 1:
            # check that the local standby DB node is following a given master DB node
            self.check_following_master(cluster)

        # many master DB nodes in the cluster
        if len(cluster.connected_master_nodes_names) > 1:
            # do nothing and wait until there will be exactly one master
            pass
