import logging
import sys
import bpy

# Centralized logger name
LOGGER_NAME = "ComputeNodes"

def get_logger() -> logging.Logger:
    """Get the standard logger for Compute Nodes."""
    return logging.getLogger(LOGGER_NAME)

def setup_logger(level=logging.INFO):
    """
    Configure the Compute Nodes logger.
    
    Args:
        level: Logging level (default: INFO)
    """
    logger = logging.getLogger(LOGGER_NAME)
    logger.setLevel(level)
    
    # Remove existing handlers to prevent duplicates
    if logger.handlers:
        logger.handlers.clear()
        
    # Create console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(level)
    
    # Create formatter
    # Format: [ComputeNodes] [Level] Message
    formatter = logging.Formatter(f'[{LOGGER_NAME}] [%(levelname)s] %(message)s')
    ch.setFormatter(formatter)
    
    # Add handler
    logger.addHandler(ch)
    
    return logger

def log_info(msg: str):
    get_logger().info(msg)

def log_warning(msg: str):
    get_logger().warning(msg)

def log_error(msg: str):
    get_logger().error(msg)

def log_debug(msg: str):
    get_logger().debug(msg)
