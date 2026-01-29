import logging
import os
import sys
from logging.handlers import TimedRotatingFileHandler

class BaseLogger:
    def __init__(self, 
                 name="vnet", 
                 level="INFO", 
                 log_to_file=False, 
                 log_file_path="logs/app.log", 
                 log_prefix=None,
                 max_days=7):
        """
        Initializes the logger.

        Args:
            name (str): The name of the logger (e.g. module name).
            level (str): Logging level ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL').
            log_to_file (bool): If True, writes logs to the specified file.
            log_file_path (str): The file path for the log file.
            log_prefix (str): A prefix string added to the log format (e.g. "[API]").
            max_days (int): Maximum number of days to keep log files (log rotation).
        """
        self.logger = logging.getLogger(name)
        self.logger.setLevel(self._get_logging_level(level))
        self.logger.propagate = False
        
        # Clear existing handlers to prevent duplicate logs if re-initialized
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        # Define Formatter
        # If prefix is provided, add it to the format
        prefix_fmt = f"[{log_prefix}] " if log_prefix else ""
        fmt_str = f'%(asctime)s - %(name)s - %(levelname)s - {prefix_fmt}%(message)s'
        formatter = logging.Formatter(fmt_str)

        # 1. Console Handler (StreamHandler)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        self.logger.addHandler(console_handler)

        # 2. File Handler (TimedRotatingFileHandler)
        if log_to_file and log_file_path:
            self._setup_file_handler(log_file_path, max_days, formatter)

    def _get_logging_level(self, level_str):
        level_map = {
            "DEBUG": logging.DEBUG,
            "INFO": logging.INFO,
            "WARNING": logging.WARNING,
            "ERROR": logging.ERROR,
            "CRITICAL": logging.CRITICAL
        }
        return level_map.get(str(level_str).upper(), logging.INFO)

    def _setup_file_handler(self, file_path, max_days, formatter):
        try:
            # Ensure the directory exists
            log_dir = os.path.dirname(file_path)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)

            # Create handler: rotate daily, keep 'max_days' backups
            file_handler = TimedRotatingFileHandler(
                filename=file_path,
                when="D",
                interval=1,
                backupCount=max_days,
                encoding="utf-8"
            )
            file_handler.setFormatter(formatter)
            self.logger.addHandler(file_handler)
        except Exception as e:
            # If file logging setup fails, print to stderr but don't crash
            sys.stderr.write(f"Error setting up file logging: {e}\n")

    def debug(self, msg, *args, **kwargs):
        self.logger.debug(msg, *args, **kwargs)

    def info(self, msg, *args, **kwargs):
        self.logger.info(msg, *args, **kwargs)

    def warning(self, msg, *args, **kwargs):
        self.logger.warning(msg, *args, **kwargs)

    def error(self, msg, *args, **kwargs):
        self.logger.error(msg, *args, **kwargs)

    def critical(self, msg, *args, **kwargs):
        self.logger.critical(msg, *args, **kwargs)
        
    def exception(self, msg, *args, **kwargs):
        self.logger.exception(msg, *args, **kwargs)
