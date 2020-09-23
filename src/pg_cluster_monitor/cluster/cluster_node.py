import logging
import datetime

from cluster.cluster_node_state import DbClusterNodeState
from cluster.cluster_node_role import DbRole
from utils import db


class DbClusterNode:
    def __init__(self, host_name, connection_string):
        self.logger = logging.getLogger("logger")

        self.host_name = host_name
        self.connection_string = connection_string
        self.connected = False
        self.last_successful_connection_time = None

        self.state = DbClusterNodeState()

    @staticmethod
    def replication_position_to_number(replication_position):
        """Converts replication position (such as 0/21B1A540) to number."""
        if not replication_position:
            return 0

        log_id, offset = replication_position.split("/")
        return int(log_id, 16) << 32 | int(offset, 16)

    def __str__(self):
        state_as_str = str(self.state.__dict__).replace('\'', '').replace('{', '')\
            .replace('}', '').replace(',', '').replace(': ', '=')
        return f"host={self.host_name} connected={self.connected} " \
               f"lastSuccessfulConnectionTime={self.last_successful_connection_time} {state_as_str} "

    def __repr__(self):
        return self.__str__()

    def update(self):
        """Retrieves PostgreSQL attributes from the DB."""

        # connected
        test, err = db.try_fetch_one(self.connection_string, "SELECT 42")
        if err:
            self.logger.warning(f"Cannot connect to {self.host_name}")
            self.connected = False
            return
        self.connected = True
        self.last_successful_connection_time = datetime.datetime.now()

        # dbRole
        is_in_recovery, err = db.try_fetch_one(self.connection_string, "SELECT pg_is_in_recovery()")
        if is_in_recovery:
            self.state.db_role = DbRole.STANDBY
        else:
            self.state.db_role = DbRole.MASTER

        # dbTime
        self.state.db_time, err = db.try_fetch_one(self.connection_string, "select to_char(now(), 'YYYY.MM.DD HH:MI:SS')")

        # dbSize
        db_size, err = db.try_fetch_one(self.connection_string, "SELECT SUM(pg_database_size(pg_database.datname)) FROM pg_database")
        self.state.db_size_in_bytes = int(db_size) if db_size is not None else db_size

        # replicationPosition
        self.state.replication_position, err = db.try_fetch_one(self.connection_string, "SELECT pg_last_wal_receive_lsn()")
        self.state.replication_position_as_number = self.replication_position_to_number(self.state.replication_position)

        # synchronousStandbyNames
        self.state.synchronous_standby_names, err = db.try_fetch_one(self.connection_string, "SHOW synchronous_standby_names")

        # pgWalSize
        self.state.pg_wal_size, err = db.try_fetch_one(self.connection_string, "SELECT pg_size_pretty(sum((pg_stat_file("
                                                                       "concat('pg_wal/',fname))).size)) as "
                                                                       "total_size from pg_ls_dir('pg_wal') as t("
                                                                       "fname)")

        # pgWalFilesCount
        self.state.pg_wal_files_count, err = db.try_fetch_one(self.connection_string, "SELECT count(*) FROM pg_ls_waldir()")

        # primaryConnInfo
        self.state.primary_conn_info, err = db.try_fetch_one(self.connection_string, "SHOW primary_conninfo")

        # primarySlotName
        self.state.primary_slot_name, err = db.try_fetch_one(self.connection_string, "SHOW primary_slot_name")

        # numberOfSlots
        self.state.number_of_slots, err = db.try_fetch_one(self.connection_string, "SELECT count(*) from pg_replication_slots")
