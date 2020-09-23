import sys
import socket
import servicemanager
import win32event
import win32service
import win32serviceutil
from utils import shell
from utils import logger
from monitor.cluster_monitor import DbClusterMonitor


class PgClusterMonitorWindowsService(win32serviceutil.ServiceFramework):
    _svc_name_ = 'PgClusterMonitor'
    _svc_display_name_ = 'PgClusterMonitor'
    _svc_description_ = 'The service manages a cluster of PostgreSQL DB with WAL streaming replication.'

    def __init__(self, args):
        """Constructor of the winservice."""
        win32serviceutil.ServiceFramework.__init__(self, args)
        self.hWaitStop = win32event.CreateEvent(None, 0, 0, None)
        socket.setdefaulttimeout(60)

        logger.init_logging()
        self.app = None

    @classmethod
    def parse_command_line(cls):
        win32serviceutil.HandleCommandLine(cls)

    def SvcStop(self):
        """Called when the service is asked to stop."""
        if self.app is not None:
            self.app.stop()

        self.ReportServiceStatus(win32service.SERVICE_STOP_PENDING)
        win32event.SetEvent(self.hWaitStop)

    def SvcDoRun(self):
        """Called when the service is asked to start."""
        servicemanager.LogMsg(servicemanager.EVENTLOG_INFORMATION_TYPE,
                              servicemanager.PYS_SERVICE_STARTED,
                              (self._svc_name_, ''))
        self.main()

    def main(self):
        config_loaded = False
        config = {}
        while not config_loaded:
            config_loaded, config = shell.load_config_ini()
        self.app = DbClusterMonitor(config)

        self.app.start()


if __name__ == '__main__':
    if len(sys.argv) == 1:
        servicemanager.Initialize()
        servicemanager.PrepareToHostSingle(PgClusterMonitorWindowsService)
        servicemanager.StartServiceCtrlDispatcher()
    else:
        win32serviceutil.HandleCommandLine(PgClusterMonitorWindowsService)
