import logging
import logging.handlers
import os

from config.constants import LOG_DIR


def setup_logger(log_level: int = logging.INFO):
    log_dir = LOG_DIR
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
    
    
    console_handler = logging.StreamHandler()

    file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "bot.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    datefmt = "%Y-%m-%d %H:%M:%S"
    formatter = logging.Formatter(
        "[{asctime}] [{levelname:<8}] {name}: {message}",
        datefmt=datefmt,
        style="{",
    )
    console_handler.setFormatter(formatter)
    file_handler.setFormatter(formatter)

    logging.basicConfig(level=log_level, handlers=[console_handler, file_handler])

    noisy_loggers = ["discord", "discord.http", "discord.gateway", "urllib3", "asyncio"]
    for logger_name in noisy_loggers:
        logging.getLogger(logger_name).setLevel(logging.INFO)


    db_logger = logging.getLogger("sqlalchemy.engine")
    db_logger.setLevel(logging.WARNING)
    db_file_handler = logging.handlers.TimedRotatingFileHandler(
        filename=os.path.join(log_dir, "sqlalchemy.log"),
        when="midnight",
        interval=1,
        backupCount=7,
        encoding="utf-8",
    )
    db_file_handler.setFormatter(formatter)
    if not db_logger.hasHandlers():
        db_logger.addHandler(db_file_handler)
