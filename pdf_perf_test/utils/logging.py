"""
Centralized logging configuration for the PDF performance testing tool.
"""

import logging
import os
from pathlib import Path
from datetime import datetime
import sys


class LogManager:
    """
    Centralized logging manager that handles configuration and creation of loggers.
    """

    _instance = None
    _initialized = False
    _loggers = {}

    def __new__(cls):
        """Singleton pattern implementation"""
        if cls._instance is None:
            cls._instance = super(LogManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        """Initialize the log manager if not already initialized"""
        if not LogManager._initialized:
            self.log_dir = None
            self.log_level = logging.INFO
            self.handlers = {}
            self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            self.main_file_handler = None
            LogManager._initialized = True

    def setup(self, log_dir=None, log_level=logging.INFO, console_output=True):
        """
        Set up the logging system with the specified configuration.

        Args:
            log_dir (str, optional): Directory to store log files. If None, logs are only shown in console.
            log_level (int, optional): Logging level to use. Defaults to logging.INFO.
            console_output (bool, optional): Whether to output logs to console. Defaults to True.
        """
        self.log_level = log_level

        # Set up log directory
        if log_dir:
            self.log_dir = Path(log_dir)
            if not self.log_dir.exists():
                self.log_dir.mkdir(parents=True, exist_ok=True)

            # Create a single main log file for all components
            main_log_file = self.log_dir / f"test_{self.timestamp}.log"
            self.main_file_handler = logging.FileHandler(main_log_file)
            self.main_file_handler.setLevel(self.log_level)
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            self.main_file_handler.setFormatter(formatter)
            self.handlers["main_file"] = self.main_file_handler

        # Set up console handler if requested
        if console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            # Set console level to WARNING if quiet mode, otherwise use log_level
            console_handler.setLevel(
                logging.WARNING if not console_output else self.log_level
            )
            formatter = logging.Formatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
            console_handler.setFormatter(formatter)
            self.handlers["console"] = console_handler

    def get_logger(self, name):
        """
        Get a logger with the specified name.

        Args:
            name (str): Name of the logger.

        Returns:
            logging.Logger: Configured logger.
        """
        if name in self._loggers:
            return self._loggers[name]

        logger = logging.getLogger(name)
        logger.setLevel(self.log_level)
        logger.handlers = []  # Clear any existing handlers

        # Add all handlers
        for handler in self.handlers.values():
            logger.addHandler(handler)

        # We no longer create separate log files for each component
        # Instead, we use a single main log file with component names in the log format

        self._loggers[name] = logger
        return logger


# Singleton instance
log_manager = LogManager()


def setup_logging(log_dir=None, log_level=logging.INFO, console_output=True):
    """
    Initialize the logging system.

    Args:
        log_dir (str, optional): Directory to store log files.
        log_level (int, optional): Logging level to use.
        console_output (bool, optional): Whether to output logs to console.
    """
    log_manager.setup(log_dir, log_level, console_output)


def get_logger(name):
    """
    Get a configured logger.

    Args:
        name (str): Name of the logger.

    Returns:
        logging.Logger: Configured logger.
    """
    return log_manager.get_logger(name)
