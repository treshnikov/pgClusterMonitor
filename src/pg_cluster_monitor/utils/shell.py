import logging
import logging.handlers
import subprocess
import os
import sys
import time
import json
from urllib.parse import urlparse, parse_qs
import configparser

def execute_cmd(cmd):
    """Executes and logs external command, returns the result of execution."""
    logger = logging.getLogger("logger")
    logger.debug(f"Execution cmd: {cmd}")
    output = subprocess.getoutput(cmd)
    logger.debug(f"Result: {output}")
    return output


def parse_postgre_sql_connection_string(connection_string):
    """Parse PostgreSQL connection string for the given format - string or url."""
    if isinstance(connection_string, dict):
        return connection_string.copy()
    if connection_string.startswith("postgres://") or connection_string.startswith("postgresql://"):
        return parse_postgre_sql_connection_string_as_url(connection_string)
    return parse_postgre_sql_connection_string_as_string(connection_string)


def parse_postgre_sql_connection_string_as_url(url):
    """Parse a PostgreSQL connection string as URL to a dictionary in accordance
    with http://www.postgresql.org/docs/current/static/libpq-connect.html#LIBPQ-CONNSTRING"""
    schemaless_url = url.split(":", 1)[1]
    p = urlparse(schemaless_url)
    fields = {}
    if p.host_name:
        fields["host"] = p.host_name
    if p.port:
        fields["port"] = str(p.port)
    if p.username:
        fields["user"] = p.username
    if p.password is not None:
        fields["password"] = p.password
    if p.path and p.path != "/":
        fields["dbname"] = p.path[1:]
    for k, v in parse_qs(p.query).items():
        fields[k] = v[-1]
    return fields


def parse_postgre_sql_connection_string_as_string(connection_string):
    """Parse a PostgreSQL connection string to a dictionary in accordance with
    http://www.postgresql.org/docs/current/static/libpq-connect.html#LIBPQ-CONNSTRING"""
    fields = {}
    while True:
        connection_string = connection_string.strip()
        if not connection_string:
            break
        if "=" not in connection_string:
            raise ValueError("Expect key=value format in connection string fragment {!r}".format(connection_string))
        key, rem = connection_string.split("=", 1)
        if rem.startswith("'"):
            as_is, value = False, ""
            for i in range(1, len(rem)):
                if as_is:
                    value += rem[i]
                    as_is = False
                elif rem[i] == "'":
                    break
                elif rem[i] == "\\":
                    as_is = True
                else:
                    value += rem[i]
            else:
                raise ValueError("Invalid connection string fragment {!r}".format(rem))
            connection_string = rem[i + 1:]
        else:
            res = rem.split(None, 1)
            if len(res) > 1:
                value, connection_string = res
            else:
                value, connection_string = rem, ""
        fields[key] = value
    return fields


def get_app_directory():
    """Determine if application is a script file or exe."""
    if getattr(sys, 'frozen', False):
        application_path = os.path.dirname(sys.executable)
    elif __file__:
        application_path = os.path.dirname(__file__) + '/../'

    return application_path


def load_config_ini():
    """Read settings from config.ini."""
    res = False
    config = configparser.ConfigParser()
    try:
        application_path = get_app_directory()
        config_name = 'config.ini'
        config_ini_file_path = os.path.join(application_path, config_name)
        print(f"Path to config file = {config_ini_file_path}")
        config.read(config_ini_file_path, encoding="utf-8")
        res = True
    except Exception as ex:
        logging.getLogger("logger").exception(f"Cannot read %s config file: {ex}", config_ini_file_path)
        time.sleep(5)

    return res, config
