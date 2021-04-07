import logging
import coloredlogs

success_level = 25
log_level = "INFO"

log = logging.getLogger("nestscript")
logging.addLevelName(success_level, "SUCCESS")
def success(self, message, *args, **kws):
    self._log(success_level, message, args, **kws)
logging.Logger.success = success
coloredlogs.DEFAULT_LEVEL_STYLES["debug"] = {"color": "blue"}
coloredlogs.install(level=log_level, logger=log, fmt="%(message)s")
