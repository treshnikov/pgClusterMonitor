from cluster.cluster_node_role import DbRole


class DbClusterNodeState:
    def __init__(self):
        self.db_role = DbRole.UNKNOWN
        self.synchronous_standby_names = ''
        self.db_size_in_bytes = 0
        self.pg_wal_size = 0
        self.pg_wal_files_count = 0
        self.replication_position = None
        self.replication_position_as_number = 0
        self.number_of_slots = 0
        self.primary_slot_name = ''
        self.db_time = None
        self.primary_conn_info = ''
