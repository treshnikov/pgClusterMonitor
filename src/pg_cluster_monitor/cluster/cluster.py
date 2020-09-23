import logging
import datetime

from cluster.cluster_node import DbClusterNode
from cluster.cluster_node_role import DbRole


class DbCluster:
    """Contains information about cluster nodes."""

    def __init__(self, connection_strings_to_cluster_nodes):
        self.nodes = {}
        self.connected_master_nodes_names = []
        self.connected_standby_nodes_names = []
        self.no_masterdb_in_cluster_event_start_time = None
        self.several_masterdb_in_cluster_event_start_time = None

        self.logger = logging.getLogger("logger")

        for node_host_name, connection_string in connection_strings_to_cluster_nodes:
            self.nodes[node_host_name] = DbClusterNode(node_host_name, connection_string)

        self.update()

    def update(self):
        """Retrieves information about cluster nodes."""
        self.connected_master_nodes_names = []
        self.connected_standby_nodes_names = []

        for node, attrs in self.nodes.items():
            self.nodes[node].update()
            self.logger.debug(f"Update information for node {node}: {attrs}")

            if self.nodes[node].connected:
                if self.nodes[node].state.db_role == DbRole.MASTER:
                    self.connected_master_nodes_names.append(node)

                if self.nodes[node].state.db_role == DbRole.STANDBY:
                    self.connected_standby_nodes_names.append(node)

        if len(self.connected_master_nodes_names) > 1:
            if self.several_masterdb_in_cluster_event_start_time is None:
                self.several_masterdb_in_cluster_event_start_time = datetime.datetime.now()
            self.no_masterdb_in_cluster_event_start_time = None
            self.logger.warning(f"Detected {len(self.connected_master_nodes_names)} master DB nodes.")

        if len(self.connected_master_nodes_names) == 1:
            self.no_masterdb_in_cluster_event_start_time = None
            self.several_masterdb_in_cluster_event_start_time = None

        if len(self.connected_master_nodes_names) == 0:
            if self.no_masterdb_in_cluster_event_start_time is None:
                self.no_masterdb_in_cluster_event_start_time = datetime.datetime.now()
            self.several_masterdb_in_cluster_event_start_time = None
            self.logger.warning("Detected no master DB node in the cluster.")

        if len(self.connected_standby_nodes_names) == 0:
            self.logger.warning("Detected no standby DB nodes in the cluster.")
