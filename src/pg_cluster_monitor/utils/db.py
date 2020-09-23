import logging
import psycopg2


def try_fetch_one(connection_string, sql):
    """Executes SQL and returns first value if it exists, otherwise returns None."""
    conn = None
    res, err = None, True
    try:
        conn = psycopg2.connect(dsn=connection_string)
        cursor = conn.cursor()
        cursor.execute(sql)
        data = cursor.fetchone()
        res = data[0] if data is not None else data
        err = False
        cursor.close()
        return res, err
    except Exception as ex:
        logging.getLogger("logger").error(f"Cannot execute {sql}: {ex}")
    finally:
        if conn is not None:
            conn.close()
    return res, err


def execute(connection_string, sql):
    """Executes SQL."""
    conn = None
    res = False
    try:
        conn = psycopg2.connect(dsn=connection_string)
        cursor = conn.cursor()
        cursor.execute(sql)
        conn.commit()
        cursor.close()
        res = True
    except Exception as ex:
        logging.getLogger("logger").error(f"Cannot execute {sql}: {ex}")
    finally:
        if conn is not None:
            conn.close()
    return res


def alter_postgre_sql_config(connection_string, config_name, val):
    """Update PostgreSQL config value using ALTER SYSTEM SET ... TO ... command."""
    conn = None
    sql = ''
    try:
        conn = psycopg2.connect(dsn=connection_string)
        conn.set_isolation_level(0)

        cursor = conn.cursor()
        sql = 'ALTER SYSTEM SET ' + config_name + ' TO \'' + val + '\''
        logging.getLogger("logger").debug(f"Execute: {sql}")
        cursor.execute(sql)
        conn.commit()
        cursor.close()

        cursor = conn.cursor()
        sql = 'SELECT pg_reload_conf()'
        logging.getLogger("logger").debug(f"Execute: {sql}")
        cursor.execute(sql)
        fetch_result = cursor.fetchone()
        logging.getLogger("logger").debug(f"Result: {fetch_result}")
        cursor.close()

        if not fetch_result:
            logging.getLogger("logger").warning(f"{sql} returns False")

        return fetch_result
    except Exception as ex:
        logging.getLogger("logger").error(f"Cannot execute {sql}: {ex}")
        return False
    finally:
        if conn is not None:
            conn.close()
